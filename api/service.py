"""Serviço de predição: candidatas por distância (haversine/BallTree), construção de features e explicação por oclusão.

ATENÇÃO (MVP): atributos DECLARADOS das ONGs (frota, capacidade, horários, categorias) vêm da tabela SIMULADA (`data/simulated/<tag>`),
pois não existe cadastro real. Em produção virão do cadastro da própria ONG."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from ml.dataset import BOOL_FEATURES, CAT_FEATURES, FEATURES, NUM_FEATURES
from pipelines.geo import EARTH_RADIUS_KM, estimated_travel_hours
from ml.semantic.classifier import CAT_PER

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml" / "artifacts" / "ranker"
AVISO = ("Resultado de um MVP treinado em dados SIMULADOS (data_origin=SIMULATED para rótulos e atributos declarados das ONGs). "
         "Probabilidades não representam desempenho real; use como apoio, com confirmação humana.")
# PREMISSAS logísticas (não verificadas): ver docs/data e simulation/params
DETOUR, SPEED_SHORT, SPEED_LONG, SERVICE_MIN = 1.35, 22.0, 55.0, 30.0
K, RADIUS_KM = 15, 150.0

GRUPOS = {
    "Distância e tempo de deslocamento": ["dist_km", "rank_distancia", "tempo_deslocamento_est_h", "razao_deslocamento_validade", "mesmo_municipio", "horas_validade_menos_viagem"],
    "Capacidade declarada vs. quantidade": ["capacidade_declarada_max_kg_dia", "kg_sobre_capacidade", "quantidade_kg"],
    "Frota declarada": ["tem_frota", "frota_capacidade_declarada_kg", "kg_sobre_frota", "frota_refrigerada_declarada"],
    "Refrigeração (câmara fria/frota)": ["camara_fria_declarada", "precisa_frio_sem_frio_declarado"],
    "Categoria aceita pela ONG": ["categoria_aceita_declarada", "n_categorias_aceitas_declaradas"],
    "Horários e dias de funcionamento": ["horario_abertura_declarado_h", "horario_fechamento_declarado_h", "n_dias_funcionamento_declarados", "dia_comum_declarado"],
    "Regras de elegibilidade": ["elegivel_regra"],
    "Tipo/porte da organização e município": ["ong_tipo", "populacao_2026", "n_osc_assistencia_municipio", "paa_kg_historico_municipio", "paa_adesao", "tem_banco_rbba_municipio", "ano_fundacao", "uf"],
}


class Ranker:
    def __init__(self, tag: str | None = None, orgs: pd.DataFrame | None = None, terr: pd.DataFrame | None = None, load_parser: bool = True):
        """Padrão (Fase 1): lê ONGs de data/gold + atributos declarados SIMULADOS de data/simulated/<tag>.
        Fase 2: `orgs`/`terr` vêm do PostgreSQL (match.index.load_org_index), com as MESMAS colunas."""
        self.tag = tag or os.environ.get("RANKER_SIM_TAG", "main")
        self.meta = json.loads((ART / "metadata.json").read_text(encoding="utf-8"))
        mp = ART / "model.joblib"
        if hashlib.sha256(mp.read_bytes()).hexdigest() != self.meta["model_sha256"]:
            raise RuntimeError("hash do artefato do modelo não confere (integridade)")
        self.model = joblib.load(mp)
        self.bg = self.meta["background"]
        if orgs is None:
            sim = ROOT / "data" / "simulated" / self.tag
            org = pd.read_parquet(ROOT / "data" / "gold" / "organizations.parquet")
            dec = pd.read_parquet(sim / "sim_ong_declared.parquet")
            fl = pd.read_parquet(sim / "sim_fleet.parquet", columns=["ong_id", "tem_frota", "capacidade_kg", "refrigerado"])
            self.orgs = org.merge(dec.drop(columns=["data_origin", "generator_version", "seed", "dataset_version", "source_parameters"]), on="ong_id", how="inner").merge(fl, on="ong_id", how="left")
            self.orgs = self.orgs[self.orgs["rankable_by_distance"]].reset_index(drop=True)
        else:
            self.orgs = orgs[orgs["rankable_by_distance"]].reset_index(drop=True)
        self.terr = (terr if terr is not None else pd.read_parquet(ROOT / "data" / "gold" / "territory.parquet")).set_index("codigo_ibge")
        self.tree = BallTree(np.radians(self.orgs[["lat", "lon"]].to_numpy(float)), metric="haversine")
        self.cats = [c[len("aceita_"):-len("_declarado")] for c in self.orgs.columns if c.startswith("aceita_") and c.endswith("_declarado")]
        self.parser = None
        if load_parser:
            try:
                from ml.semantic.classifier import SemanticParser
                self.parser = SemanticParser.load()
            except Exception:  # parser é opcional
                self.parser = None
        self.data_version = f"{self.meta['data_version_simulada']}|real:{self.meta['data_version_real']}"

    # ------------------------------------------------------------------ features
    def _features(self, lote: dict, idx: np.ndarray, dist: np.ndarray) -> pd.DataFrame:
        o = self.orgs.iloc[idx].reset_index(drop=True)
        n = len(o)
        speed = np.where(dist <= 15, SPEED_SHORT, SPEED_LONG)
        t = estimated_travel_hours(dist, DETOUR, speed, SERVICE_MIN)
        cat = lote["categoria"]
        acc = o[f"aceita_{cat}_declarado"].to_numpy().astype(bool)
        cap = o["capacidade_declarada_faixa_max_kg_dia"].to_numpy(float)
        mask_d = o["dias_funcionamento_declarados_mask"].to_numpy().astype(int)
        don_mask = sum(1 << d for d in lote["dias_retirada"])
        has_fleet = o["tem_frota"].fillna(False).to_numpy().astype(bool)
        fcap = np.where(has_fleet, o["capacidade_kg"].fillna(0).to_numpy(float), 0.0)
        fref = (has_fleet & o["refrigerado"].fillna(False).to_numpy().astype(bool))
        cam = o["camara_fria_declarada"].to_numpy().astype(bool)
        kg, h = lote["quantidade_kg"], lote["horas_ate_validade"]
        frio = bool(lote["exige_refrigeracao"])
        r_cat, r_cap = ~acc, kg > cap
        r_frio = frio & ~(cam | fref)
        r_dia = (mask_d & don_mask) == 0
        elig = ~(r_cat | r_cap | r_frio | r_dia)
        ncat = o[[f"aceita_{c}_declarado" for c in self.cats]].to_numpy().astype(bool).sum(1)
        rank = np.argsort(np.argsort(dist, kind="stable"), kind="stable") + 1
        now = lote["agora"]
        X = pd.DataFrame({
            "dist_km": dist, "rank_distancia": rank, "tempo_deslocamento_est_h": t, "razao_deslocamento_validade": t / h,
            "quantidade_kg": kg, "horas_ate_validade": h, "tempo_carga_min": lote["tempo_carga_min"], "janela_retirada_inicio_h": lote["janela_retirada_inicio_h"],
            "janela_retirada_fim_h": lote["janela_retirada_fim_h"], "hora_cadastro": now.hour + now.minute / 60, "dow_cadastro": now.weekday(),
            "frota_capacidade_declarada_kg": fcap, "capacidade_declarada_max_kg_dia": cap, "n_categorias_aceitas_declaradas": ncat,
            "horario_abertura_declarado_h": o["horario_abertura_declarado_h"].to_numpy(float), "horario_fechamento_declarado_h": o["horario_fechamento_declarado_h"].to_numpy(float),
            "n_dias_funcionamento_declarados": [bin(int(m)).count("1") for m in mask_d],
            "populacao_2026": o["populacao_2026"].to_numpy(float), "n_osc_assistencia_municipio": o["n_osc_assistencia_municipio"].to_numpy(float),
            "paa_kg_historico_municipio": o["paa_kg_historico_municipio"].to_numpy(float), "ano_fundacao": o["ano_fundacao"].to_numpy(float),
            "kg_sobre_capacidade": kg / np.where(cap == 0, np.nan, cap), "kg_sobre_frota": kg / np.where(fcap == 0, np.nan, fcap), "horas_validade_menos_viagem": h - t,
            "mesmo_municipio": (o["municipio_ibge"].to_numpy() == lote["municipio_ibge"]).astype(float), "tem_frota": has_fleet.astype(float),
            "frota_refrigerada_declarada": fref.astype(float), "camara_fria_declarada": cam.astype(float), "categoria_aceita_declarada": acc.astype(float),
            "dia_comum_declarado": (~r_dia).astype(float), "elegivel_regra": elig.astype(float), "exige_refrigeracao": float(frio), "contem_alergenico": float(lote["contem_alergenico"]),
            "paa_adesao": o["paa_adesao"].astype(float).to_numpy(), "tem_banco_rbba_municipio": o["tem_banco_rbba_municipio"].astype(float).to_numpy(),
            "precisa_frio_sem_frio_declarado": r_frio.astype(float),
            "ong_tipo": o["ong_tipo"].to_numpy(), "categoria": cat, "perecibilidade": CAT_PER[cat], "location_precision_doador": lote["location_precision"],
            "location_precision_ong": o["location_precision"].to_numpy(), "geo_quality_ong": o["geo_quality"].to_numpy(), "uf": o["uf"].to_numpy(),
        })
        X.attrs["orgs"] = o
        return X[FEATURES]

    def _explain(self, X: pd.DataFrame, p: np.ndarray, top: int = 5) -> list[dict]:
        row = X.iloc[[int(np.argmax(p))]].copy()
        base = float(self.model.predict_proba(row)[:, 1][0])
        out = []
        for nome, cols in GRUPOS.items():
            r = row.copy()
            for c in cols:
                r[c] = self.bg["num_median"][c] if c in self.bg["num_median"] else self.bg["cat_mode"][c]
            d = base - float(self.model.predict_proba(r)[:, 1][0])
            out.append({"fator": nome, "efeito": "aumenta" if d > 0.005 else "reduz" if d < -0.005 else "neutro", "impacto": round(d, 4)})
        out.sort(key=lambda x: -abs(x["impacto"]))
        return out[:top]

    def predict(self, req: dict) -> dict:
        alertas: list[str] = []
        parsed = None
        lote = dict(req)
        if lote.get("descricao_texto") and self.parser is not None:
            parsed = self.parser.parse(lote["descricao_texto"], dt.date.today())
            if lote.get("categoria") is None:
                lote["categoria"] = parsed["categoria"]
            if lote.get("horas_ate_validade") is None and parsed["days_to_expiry"] is not None:
                if parsed["blocked_expired"]:
                    raise ValueError("lote vencido segundo o texto informado")
                lote["horas_ate_validade"] = max(float(parsed["days_to_expiry"]) * 24.0, 1.0)
            if parsed["needs_human_confirmation"]:
                alertas.append("confirmação humana necessária para: " + ", ".join(parsed["needs_human_confirmation"]))
        if lote.get("categoria") is None:
            raise ValueError("categoria não informada e parser semântico indisponível")
        if lote.get("horas_ate_validade") is None:
            raise ValueError("`horas_ate_validade` não informado e não inferido do texto")
        if lote.get("municipio_ibge") is not None and lote["municipio_ibge"] in self.terr.index:
            t = self.terr.loc[lote["municipio_ibge"]]
            lat, lon, prec = float(t["latitude"]), float(t["longitude"]), "MUNICIPALITY_CENTROID"
        elif lote.get("lat") is not None:
            lat, lon, prec = lote["lat"], lote["lon"], "EXACT"
            lote["municipio_ibge"] = lote.get("municipio_ibge") or 0
        else:
            raise ValueError("município não encontrado na base IBGE")
        lote["location_precision"] = prec
        lote["agora"] = dt.datetime.now()
        ind, d = self.tree.query_radius(np.radians([[lat, lon]]), r=RADIUS_KM / EARTH_RADIUS_KM, return_distance=True)
        ind, d = ind[0], d[0] * EARTH_RADIUS_KM
        if len(ind) == 0:
            return {"ranking": [], "prediction": None, "confidence": 0.0, "factors": [], "alertas": ["nenhuma ONG a até 150 km"], "parsed": parsed}
        sel = np.argsort(d, kind="stable")[:K]
        ind, d = ind[sel], d[sel]
        X = self._features(lote, ind, d)
        p = self.model.predict_proba(X)[:, 1]
        o = self.orgs.iloc[ind].reset_index(drop=True)
        order = np.argsort(-p, kind="stable")[: lote["top_n"]]
        rank = [{"posicao": i + 1, "ong_id": str(o.loc[j, "ong_id"]), "ong_tipo": str(o.loc[j, "ong_tipo"]), "uf": o.loc[j, "uf"], "municipio_ibge": int(o.loc[j, "municipio_ibge"]),
                 "dist_km": round(float(d[j]), 2), "probabilidade": round(float(p[j]), 4), "elegivel_regra": bool(X["elegivel_regra"].iloc[j]), "location_precision": str(o.loc[j, "location_precision"])}
                for i, j in enumerate(order)]
        thr = float(self.meta["threshold_val"])
        best = float(p[order[0]])
        if best < thr:
            alertas.append("probabilidade da melhor ONG abaixo do limiar de decisão; considerar acionar mais de uma organização")
        return {"ranking": rank, "prediction": {"ong_id": rank[0]["ong_id"], "probabilidade": best, "recomendado": best >= thr, "limiar_decisao": thr},
                "confidence": best, "factors": self._explain(X, p), "alertas": alertas, "parsed": parsed}
