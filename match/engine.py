"""Motor de match DOADOR → ONG (híbrido): elegibilidade eliminatória → candidatas geográficas → ML + regras + distância → ranking explicado.

Pipeline (seção 3.1 do prompt): (1) filtro de elegibilidade; (2) candidatas geográficas (BallTree haversine); (3) ML_SCORE + BUSINESS_RULE_SCORE + DISTANCE_SCORE → FINAL_SCORE.
Tudo em memória; a latência de cada etapa é medida por requisição. Distância é LINHA RETA (haversine), nunca rota."""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from api.service import DETOUR, Ranker
from core.settings import SETTINGS, TZ, MatchSettings
from pipelines.geo import EARTH_RADIUS_KM
from .eligibility import RULE_ORDER, RULES, DonationCtx, evaluate, reasons_for
from .index import OrgIndex
from .scoring import business_rule_score, distance_score, final_score

log = logging.getLogger("match.engine")
SCORE_LABELS = {
    "ML_SCORE": "probabilidade estimada de aceite e coleta dentro da validade (modelo da Fase 1 treinado em dados SIMULADOS; não é desempenho real)",
    "BUSINESS_RULE_SCORE": "regras brandas observáveis: folga de capacidade, cadeia fria, tipo da organização, contexto regional (pesos são PREMISSAS)",
    "DISTANCE_SCORE": "proximidade em linha reta e folga entre deslocamento estimado e validade (NÃO é rota)",
    "FINAL_SCORE": "combinação linear ponderada dos três scores acima",
}


def mask_to_days(mask: int) -> list[int]:
    return [d for d in range(7) if (mask >> d) & 1]


def _f(x: Any, nd: int = 4) -> float:
    return round(float(x), nd)


class MatchEngine:
    def __init__(self, ranker: Ranker, index: OrgIndex, cfg: MatchSettings = SETTINGS):
        self.ranker, self.index, self.cfg = ranker, index, cfg
        self.orgs = ranker.orgs  # mesmo DataFrame/ordem da BallTree
        self.model_version = ranker.meta["model_version"]
        self._pos = {u: i for i, u in enumerate(self.orgs["org_uuid"])}

    # ---------------------------------------------------------------- utilitários
    def lote_dict(self, ctx: DonationCtx, now_local: dt.datetime) -> dict[str, Any]:
        return {"categoria": ctx.categoria, "quantidade_kg": ctx.quantity_kg, "horas_ate_validade": max(ctx.hours_to_expiry, 0.01), "exige_refrigeracao": ctx.needs_cold,
                "contem_alergenico": ctx.allergen, "janela_retirada_inicio_h": ctx.pickup_start_h, "janela_retirada_fim_h": ctx.pickup_end_h, "tempo_carga_min": ctx.load_minutes,
                "dias_retirada": mask_to_days(ctx.pickup_days_mask), "municipio_ibge": ctx.municipio_ibge, "location_precision": ctx.location_precision,
                "agora": now_local.replace(tzinfo=None)}

    def _remaining(self, sub: pd.DataFrame, reserved_kg: dict[str, float]) -> np.ndarray:
        cap = sub["capacidade_declarada_faixa_max_kg_dia"].to_numpy(float)
        res = sub["org_uuid"].map(lambda u: reserved_kg.get(u, 0.0)).to_numpy(float)
        return np.maximum(cap - res, 0.0)

    # ---------------------------------------------------------------- ranking
    def rank(self, ctx: DonationCtx, now: dt.datetime, reserved_kg: dict[str, float] | None = None, top_n: int | None = None) -> dict[str, Any]:
        reserved_kg = reserved_kg or {}
        now_local = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
        T: dict[str, float] = {}
        t0 = time.perf_counter()
        # (2a) vizinhança geográfica dentro do raio viável (índice espacial)
        ind, d = self.ranker.tree.query_radius(np.radians([[ctx.lat, ctx.lon]]), r=self.cfg.radius_km / EARTH_RADIUS_KM, return_distance=True)
        ind, d = ind[0], d[0] * EARTH_RADIUS_KM
        T["busca_espacial_ms"] = (time.perf_counter() - t0) * 1000
        base = {"engine_version": self.cfg.engine_version, "model_version": self.model_version, "weights": self.weights(), "score_definitions": SCORE_LABELS,
                "rules_catalog": RULES, "radius_km": self.cfg.radius_km, "distance_method": "Haversine (linha reta, raio médio 6371,0088 km); NÃO é distância viária",
                "n_unranked_no_location": self.index.n_no_location, "n_unranked_no_profile": self.index.n_no_profile}
        if len(ind) == 0:
            T["total_ms"] = (time.perf_counter() - t0) * 1000
            return {**base, "ranking": [], "eligibility": {"n_in_radius": 0, "n_eligible": 0, "por_regra": {}, "amostra_ineligiveis": []}, "latency_ms": {k: _f(v, 2) for k, v in T.items()},
                    "alertas": [f"nenhuma ONG ranqueável a até {self.cfg.radius_km:.0f} km"]}
        # (1) elegibilidade eliminatória sobre TODAS as ONGs do raio
        t1 = time.perf_counter()
        sub = self.orgs.iloc[ind].reset_index(drop=True)
        rem = self._remaining(sub, reserved_kg)
        res = evaluate(ctx, sub, d, rem, now_local)
        elig = res["eligible"]
        por_regra = {k: int(res["fail"][k].sum()) for k in RULE_ORDER}
        near_inel = [i for i in np.argsort(d, kind="stable") if not elig[i]][:10]
        sample = [{"ong_id": str(sub.loc[i, "ong_id"]), "dist_km": _f(d[i], 2), "regras_reprovadas": reasons_for(res, i)} for i in near_inel]
        T["elegibilidade_ms"] = (time.perf_counter() - t1) * 1000
        elig_info = {"n_in_radius": int(len(ind)), "n_eligible": int(elig.sum()), "por_regra": por_regra, "amostra_ineligiveis": sample,
                     "nota": "contagens por regra NÃO são exclusivas: uma ONG pode reprovar em mais de uma regra"}
        if not elig.any():
            T["total_ms"] = (time.perf_counter() - t0) * 1000
            return {**base, "ranking": [], "eligibility": elig_info, "latency_ms": {k: _f(v, 2) for k, v in T.items()}, "alertas": ["nenhuma ONG elegível pelas regras eliminatórias"]}
        # (2b) candidatas: K mais próximas entre as ELEGÍVEIS (desempate: regras brandas, depois id) — evita empate arbitrário em cidades com muitas ONGs no mesmo centroide
        t2 = time.perf_counter()
        ei = np.flatnonzero(elig)
        br_all, _ = business_rule_score(sub.iloc[ei], ctx.quantity_kg, rem[ei], ctx.needs_cold, self.cfg)
        ids_e = sub["ong_id"].to_numpy(dtype="U32")[ei]
        order = np.lexsort((ids_e, -br_all, np.round(d[ei], 1)))[: self.cfg.k_candidates]
        sel = ei[order]
        T["candidatas_ms"] = (time.perf_counter() - t2) * 1000
        # (3a) ML_SCORE
        t3 = time.perf_counter()
        lote = self.lote_dict(ctx, now_local)
        X = self.ranker._features(lote, ind[sel], d[sel])
        ml = self.ranker.model.predict_proba(X)[:, 1]
        T["ml_ms"] = (time.perf_counter() - t3) * 1000
        # (3b) regras brandas, distância e FINAL
        t4 = time.perf_counter()
        ssub = sub.iloc[sel].reset_index(drop=True)
        srem, sd, swait, strav = rem[sel], d[sel], res["wait_h"][sel], res["travel_h"][sel]
        slack = ctx.hours_to_expiry - swait - strav
        br, comp = business_rule_score(ssub, ctx.quantity_kg, srem, ctx.needs_cold, self.cfg)
        ds = distance_score(sd, slack, ctx.hours_to_expiry, self.cfg)
        fs = final_score(ml, br, ds, self.cfg)
        ordr = sorted(range(len(sel)), key=lambda k: (-float(fs[k]), str(ssub.loc[k, "ong_id"])))
        rows = []
        for pos, k in enumerate(ordr, start=1):
            prec = str(ssub.loc[k, "location_precision"])
            approx = prec != "EXACT" or ctx.location_precision != "EXACT"
            expl = [
                f"Distância em linha reta: {sd[k]:.1f} km"
                + (" — APROXIMADA: usa centroide de município (ONG: %s; doador: %s)" % (prec, ctx.location_precision) if approx else " (pontos exatos)")
                + f"; deslocamento estimado {strav[k] * 60:.0f} min (desvio {DETOUR}×, velocidade média; não é rota)",
                f"Espera até a janela de coleta: {swait[k]:.1f} h; folga até a validade: {slack[k]:.1f} h",
                f"ML_SCORE {ml[k]:.3f}: probabilidade estimada de aceite e coleta dentro da validade — modelo treinado em dados SIMULADOS",
                f"BUSINESS_RULE_SCORE {br[k]:.3f}: capacidade {comp['capacidade'][k]:.2f}, refrigeração {comp['refrigeracao'][k]:.2f}, tipo {comp['tipo_organizacao'][k]:.2f}, contexto regional {comp['contexto_regional'][k]:.2f}",
                f"DISTANCE_SCORE {ds[k]:.3f}; FINAL_SCORE {fs[k]:.3f} = {self.cfg.w_ml}·ML + {self.cfg.w_rule}·REGRAS + {self.cfg.w_dist}·DISTÂNCIA",
                f"Regras eliminatórias aprovadas ({len(RULE_ORDER)}): " + ", ".join(RULE_ORDER),
            ]
            if str(ssub.loc[k, "profile_origin"]) == "SIMULATED":
                expl.append("Capacidade, horários, categorias e refrigeração da ONG são DECLARADOS SIMULADOS (sem cadastro real).")
            rows.append({
                "posicao": pos, "org_id": str(ssub.loc[k, "org_uuid"]), "ong_id": str(ssub.loc[k, "ong_id"]), "ong_tipo": str(ssub.loc[k, "ong_tipo"]), "uf": ssub.loc[k, "uf"],
                "municipio_ibge": int(ssub.loc[k, "municipio_ibge"]), "dist_km": _f(sd[k], 2), "location_precision": prec, "distancia_aproximada": bool(approx),
                "tempo_deslocamento_est_h": _f(strav[k], 3), "espera_janela_h": _f(swait[k], 3), "folga_validade_h": _f(slack[k], 3),
                "ML_SCORE": _f(ml[k]), "BUSINESS_RULE_SCORE": _f(br[k]), "DISTANCE_SCORE": _f(ds[k]), "FINAL_SCORE": _f(fs[k]),
                "business_rule_components": {a: _f(b[k]) for a, b in comp.items()}, "capacidade_restante_kg": _f(srem[k], 1), "regras_aprovadas": RULE_ORDER,
                "platform_status": str(ssub.loc[k, "platform_status"]), "profile_origin": str(ssub.loc[k, "profile_origin"]), "explicacao": expl})
        T["scores_ms"] = (time.perf_counter() - t4) * 1000
        T["total_ms"] = (time.perf_counter() - t0) * 1000
        alertas = []
        if any(r["distancia_aproximada"] for r in rows):
            alertas.append("Distâncias aproximadas: centroide de município em um dos extremos (location_precision exibido por ONG).")
        if rows and rows[0]["ML_SCORE"] < float(self.ranker.meta["threshold_val"]):
            alertas.append("ML_SCORE da melhor ONG abaixo do limiar de decisão da validação simulada; considerar acionar mais de uma organização")
        out = {**base, "ranking": rows[: top_n] if top_n else rows, "eligibility": elig_info, "latency_ms": {k: _f(v, 2) for k, v in T.items()}, "alertas": alertas}
        log.info("ranking: raio=%d elegíveis=%d candidatas=%d total=%.1fms (ml=%.1fms)", len(ind), int(elig.sum()), len(rows), T["total_ms"], T["ml_ms"])
        return out

    def weights(self) -> dict[str, Any]:
        c = self.cfg
        return {"ML": c.w_ml, "BUSINESS_RULE": c.w_rule, "DISTANCE": c.w_dist, "br_componentes": {"capacidade": c.br_capacity, "refrigeracao": c.br_refrigeration,
                "tipo_organizacao": c.br_org_type, "contexto_regional": c.br_regional}, "dist_d0_km": c.dist_d0_km, "dist_alpha": c.dist_alpha, "k_candidatas": c.k_candidates,
                "natureza": "PREMISSAS do projeto, não calibradas com dados reais"}

    # ---------------------------------------------------------------- reavaliação de UMA candidata (no momento da proposta)
    def recheck(self, ctx: DonationCtx, candidate: dict[str, Any], now: dt.datetime, remaining_kg: float) -> tuple[bool, list[str], dict[str, float]]:
        """Reaplica as regras eliminatórias à candidata com o relógio atual (o tempo passou entre o ranking e a proposta)."""
        now_local = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
        i = self._pos.get(candidate["org_id"])
        if i is None:
            return False, ["E_LOCALIZACAO_AUSENTE"], {}
        sub = self.orgs.iloc[[i]].reset_index(drop=True)
        res = evaluate(ctx, sub, np.array([float(candidate["dist_km"])]), np.array([remaining_kg]), now_local)
        return bool(res["eligible"][0]), reasons_for(res, 0), {"espera_h": float(res["wait_h"][0]) if not np.isnan(res["wait_h"][0]) else float("nan"), "deslocamento_h": float(res["travel_h"][0])}
