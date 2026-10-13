"""Comparação de estratégias de logística DOADOR → ONG (SIMULAÇÃO reprodutível, usada na tela de logística do ADMIN).

Estratégias (todas sobre o MESMO conjunto de lotes SIMULADOS e o MESMO relógio de referência):
  A. ONG mais próxima — destino = ONG mais próxima em linha reta; as regras eliminatórias são reaplicadas e os destinos inelegíveis são INFORMADOS (lote não entregue).
  B. Ranking híbrido — destino = 1ª colocada do motor de match (elegibilidade + ML SIMULADO + regras + distância), com reserva de capacidade entre os lotes da rodada.
  C. Ranking híbrido com rota — mesmos destinos de B, mas os lotes que vão para a mesma ONG são agrupados numa rota (baseline vizinho-mais-próximo + OR-Tools, ambos verificados).
Em A e B cada lote é uma viagem própria (ONG → doador → ONG). Distâncias/tempos são estimativas (linha reta × desvio ÷ velocidade), NÃO rota viária.
Os resultados dependem de doadores, lotes, frota e perfis SIMULADOS e de pesos PREMISSA: NÃO representam desempenho real."""
from __future__ import annotations

import datetime as dt
import math
import random
from collections import defaultdict
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import ROUTE, TZ
from database import models as m
from match.eligibility import DonationCtx
from pipelines.geo import haversine_km
from routing import core

# Relógio de referência FIXO (terça-feira 08:00 local), igual ao benchmark de roteirização: o resultado depende só da semente.
REF_CLOCK = dt.datetime(2026, 10, 13, 8, 0, tzinfo=TZ)
SHELF_H = 48.0
ROTULO = ("SIMULAÇÃO: doadores, lotes, frota e perfis de ONG SIMULADOS; ONGs e municípios são registros públicos reais; distâncias e tempos são estimativas "
          "(linha reta × desvio ÷ velocidade), não rota viária. NÃO representa desempenho no mundo real.")


class StrategyError(Exception):
    """Cenário impossível de montar (sem doadores/lotes simulados suficientes)."""


def _lots(db: Session, rng: random.Random, n_lots: int, radius_km: float) -> tuple[list[dict[str, Any]], str]:
    dv = db.scalar(select(m.Donor.dataset_version).where(m.Donor.data_origin == "SIMULATED").limit(1))
    if dv is None:
        raise StrategyError("não há doadores SIMULADOS no banco para montar o cenário")
    rows = db.execute(select(m.Donor.id, m.Donor.external_id, m.Donor.municipio_ibge, m.Donor.pickup_start_h, m.Donor.pickup_end_h, m.Donor.load_minutes,
                             m.DonorLocation.lat, m.DonorLocation.lon, m.DonorLocation.location_precision)
                      .join(m.DonorLocation, m.DonorLocation.donor_id == m.Donor.id).where(m.Donor.dataset_version == dv, m.Donor.data_origin == "SIMULATED")).all()
    rows = [r for r in rows if r[6] is not None and r[7] is not None]
    if len(rows) < n_lots:
        raise StrategyError("doadores SIMULADOS com localização insuficientes para o cenário")
    donors = {r[0]: r for r in rows}
    don = db.execute(select(m.Donation.donor_id, m.Donation.categoria, m.Donation.quantity_kg, m.Donation.exige_refrigeracao, m.Donation.contem_alergenico)
                     .where(m.Donation.dataset_version == dv, m.Donation.data_origin == "SIMULATED", m.Donation.quantity_kg.is_not(None), m.Donation.categoria.is_not(None),
                            m.Donation.exige_refrigeracao.is_not(None))).all()
    first: dict[Any, tuple] = {}
    for r in don:
        first.setdefault(r[0], r)
    cand = [d for d in donors if d in first]
    if len(cand) < n_lots:
        raise StrategyError("lotes SIMULADOS insuficientes para o cenário")
    rng.shuffle(cand)
    for anchor in cand[:200]:  # âncora determinística pela semente: precisa de n_lots doadores com lote num raio
        a = donors[anchor]
        near = [d for d in cand if haversine_km(a[6], a[7], donors[d][6], donors[d][7]) <= radius_km]
        if len(near) >= n_lots:
            near.sort(key=lambda d: (haversine_km(a[6], a[7], donors[d][6], donors[d][7]), str(d)))
            pick = near[:n_lots]
            out = []
            for d in pick:
                r, l = donors[d], first[d]
                out.append({"donor_ext": str(r[1]), "lat": float(r[6]), "lon": float(r[7]), "mun": int(r[2]), "prec": str(r[8]), "start_h": float(r[3]), "end_h": float(r[4]),
                            "load_min": float(r[5]), "categoria": str(l[1]), "kg": float(l[2]), "cold": bool(l[3]), "allergen": bool(l[4])})
            return out, str(dv)
    raise StrategyError(f"não foi possível reunir {n_lots} lotes SIMULADOS num raio de {radius_km:g} km; reduza o número de lotes ou aumente o raio")


def _ctx(lot: dict[str, Any], margin_h: float) -> DonationCtx:
    return DonationCtx(categoria=lot["categoria"], quantity_kg=lot["kg"], hours_to_expiry=SHELF_H - margin_h, needs_cold=lot["cold"], pickup_days_mask=127,
                       pickup_start_h=lot["start_h"], pickup_end_h=lot["end_h"], load_minutes=lot["load_min"], lat=lot["lat"], lon=lot["lon"], municipio_ibge=lot["mun"],
                       location_precision=lot["prec"], allergen=lot["allergen"], data_origin="SIMULATED", categorias=(lot["categoria"],))


def _trip(lot: dict[str, Any], org_lat: float, org_lon: float) -> tuple[float, float]:
    d = float(haversine_km(org_lat, org_lon, lot["lat"], lot["lon"]))
    km = 2.0 * d * ROUTE.detour
    speed = ROUTE.speed_short_kmh if d <= ROUTE.short_threshold_km else ROUTE.speed_long_kmh
    minutes = km / speed * 60.0 + lot["load_min"] + ROUTE.unload_min
    return km, minutes


def _summ(nome: str, desc: str, rows: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ok = [r for r in rows if r["entregue"]]
    return {"id": nome, "descricao": desc, "lotes": len(rows), "lotes_entregues_no_prazo": len(ok), "lotes_nao_entregues": len(rows) - len(ok),
            "kg_entregue": round(sum(r["kg"] for r in ok), 1), "km_total_estimado": round(sum(r["km"] for r in rows if r["entregue"]), 1),
            "minutos_total_estimado": round(sum(r["min"] for r in rows if r["entregue"])), "ongs_distintas": len({r["ong"] for r in ok if r["ong"]}),
            "motivos_nao_entrega": _count([r["motivo"] for r in rows if not r["entregue"]]), **(extra or {})}


def _count(xs: list[str]) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for x in xs:
        d[x] += 1
    return dict(d)


def compare_strategies(db: Session, engine, n_lots: int = 8, seed: int = 20261011, radius_km: float = 40.0, time_limit_s: int = 2) -> dict[str, Any]:
    rng = random.Random(seed)  # nosec B311  # noqa: S311 — amostragem reprodutível por semente (sem uso criptográfico)
    lots, dv = _lots(db, rng, n_lots, radius_km)
    margin = ROUTE.safety_margin_h
    orgs = engine.orgs
    olat, olon = orgs["lat"].to_numpy(float), orgs["lon"].to_numpy(float)
    # ---------------- A: ONG mais próxima
    A = []
    for lot in lots:
        d = haversine_km(lot["lat"], lot["lon"], olat, olon)
        i = int(np.nanargmin(np.where(np.isnan(d), np.inf, d)))
        row = orgs.iloc[i]
        cap = float(row["capacidade_declarada_faixa_max_kg_dia"]) if "capacidade_declarada_faixa_max_kg_dia" in orgs.columns else 0.0
        ok, why, _ = engine.recheck(_ctx(lot, margin), {"org_id": str(row["org_uuid"]), "dist_km": float(d[i])}, REF_CLOCK, cap)
        km, mi = _trip(lot, float(row["lat"]), float(row["lon"]))
        A.append({"lote": lot["donor_ext"], "kg": lot["kg"], "ong": str(row["ong_id"]), "dist_km": round(float(d[i]), 2), "entregue": bool(ok), "km": km, "min": mi,
                  "motivo": "" if ok else (why[0] if why else "INELEGIVEL")})
    # ---------------- B: ranking híbrido (top-1, com reserva de capacidade)
    B, reserved, dest = [], {}, {}
    for lot in lots:
        res = engine.rank(_ctx(lot, margin), REF_CLOCK, reserved)
        if not res["ranking"]:
            B.append({"lote": lot["donor_ext"], "kg": lot["kg"], "ong": "", "dist_km": None, "entregue": False, "km": 0.0, "min": 0.0, "motivo": "SEM_ONG_ELEGIVEL"})
            continue
        top = res["ranking"][0]
        reserved[top["org_id"]] = reserved.get(top["org_id"], 0.0) + lot["kg"]
        km, mi = _trip(lot, float(orgs.iloc[engine._pos[top["org_id"]]]["lat"]), float(orgs.iloc[engine._pos[top["org_id"]]]["lon"]))
        B.append({"lote": lot["donor_ext"], "kg": lot["kg"], "ong": top["ong_id"], "dist_km": top["dist_km"], "entregue": True, "km": km, "min": mi, "motivo": ""})
        dest.setdefault(top["org_id"], []).append(lot)
    # ---------------- C: híbrido + rota
    a = core.Assumptions(ROUTE.detour, ROUTE.speed_short_kmh, ROUTE.speed_long_kmh, ROUTE.short_threshold_km, ROUTE.unload_min)
    C, rotas = [], []
    for org_uuid, group in dest.items():
        row = orgs.iloc[engine._pos[org_uuid]]
        cap_v = float(row.get("fleet_capacity_kg") or 0.0) if "fleet_capacity_kg" in orgs.columns else 0.0
        if not bool(row.get("has_fleet", False)) or cap_v <= 0:
            for lot in group:  # sem frota SIMULADA: cada lote segue como viagem isolada (igual a B)
                km, mi = _trip(lot, float(row["lat"]), float(row["lon"]))
                C.append({"lote": lot["donor_ext"], "kg": lot["kg"], "ong": str(row["ong_id"]), "entregue": True, "km": km, "min": mi, "motivo": ""})
            continue
        stops = tuple(core.Stop(key=lot["donor_ext"], lat=lot["lat"], lon=lot["lon"], kg=lot["kg"], service_min=int(lot["load_min"]), win_start=max(0, int((lot["start_h"] - 8.0) * 60)),
                                win_end=int((lot["end_h"] - 8.0) * 60), deadline=int(SHELF_H * 60 - margin * 60), cold=lot["cold"]) for lot in group)
        prob = core.Problem(depot=(float(row["lat"]), float(row["lon"])), dest=(float(row["lat"]), float(row["lon"])), dest_open=max(0, int((float(row["open_hour"]) - 8.0) * 60)),
                            dest_close=int((float(row["close_hour"]) - 8.0) * 60), vehicle_cap_kg=cap_v, org_cap_kg=float(row["capacidade_declarada_faixa_max_kg_dia"]),
                            refrigerated=bool(row.get("fleet_refrigerated", False)), stops=stops, assumptions=a, horizon_min=int(ROUTE.horizon_h * 60))
        out = core.plan(prob, max(1, int(time_limit_s)))
        sol = out["solver"]
        served = {stops[j].key for j in sol.order}
        n_ok = max(len(sol.order), 1)
        for lot in group:
            ok = lot["donor_ext"] in served
            C.append({"lote": lot["donor_ext"], "kg": lot["kg"], "ong": str(row["ong_id"]), "entregue": ok, "km": sol.evaluation.km / n_ok if ok else 0.0,
                      "min": sol.evaluation.minutes / n_ok if ok else 0.0, "motivo": "" if ok else next((u["reason"] for u in sol.unassigned if u["key"] == lot["donor_ext"]), "NAO_COUBE_NA_ROTA")})
        rotas.append({"ong": str(row["ong_id"]), "lotes_na_rota": len(sol.order), "lotes_do_grupo": len(group), "km": round(sol.evaluation.km, 1), "minutos": round(sol.evaluation.minutes),
                      "viavel": bool(sol.evaluation.feasible), "algoritmo": sol.algorithm})
    for lot in lots:  # lotes sem ONG elegível em B aparecem como não entregues em C
        if lot["donor_ext"] not in {r["lote"] for r in C}:
            C.append({"lote": lot["donor_ext"], "kg": lot["kg"], "ong": "", "entregue": False, "km": 0.0, "min": 0.0, "motivo": "SEM_ONG_ELEGIVEL"})
    estrategias = [
        _summ("A_ong_mais_proxima", "Destino = ONG mais próxima em linha reta; regras eliminatórias reaplicadas; uma viagem por lote", A),
        _summ("B_ranking_hibrido", "Destino = 1ª do ranking híbrido (elegibilidade + ML simulado + regras + distância), com reserva de capacidade; uma viagem por lote", B),
        _summ("C_hibrido_com_rota", "Destinos de B; lotes da mesma ONG agrupados em rota (vizinho mais próximo + OR-Tools, verificados)", C, {"rotas": rotas}),
    ]
    return {"rotulo": ROTULO, "tipo": "SIMULACAO", "parametros": {"n_lotes": n_lots, "seed": seed, "raio_km": radius_km, "tempo_solver_s": time_limit_s, "relogio_referencia": REF_CLOCK.isoformat(),
                                                                "validade_h": SHELF_H, "margem_seguranca_h": margin, "desvio": ROUTE.detour, "dataset_version": dv},
            "estrategias": estrategias,
            "leitura": ["Distância e tempo são estimativas em linha reta com desvio fixo; ONGs vizinhas no mesmo centroide municipal têm distância aproximada.",
                        "A comparação depende de lotes, frota e perfis SIMULADOS e de pesos PREMISSA do motor; mudar a semente muda o cenário.",
                        "Circularidade: o ranker foi treinado em desfechos simulados pela mesma lógica; o ganho de B sobre A não prova ganho no mundo real."],
            "lotes": {"A": A, "B": B, "C": C}, "nan_guard": not any(math.isnan(r["km"]) for r in A + B + C)}
