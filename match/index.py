"""Índice em memória das ONGs (features + BallTree haversine), carregado do PostgreSQL.

Colunas idênticas às da Fase 1 (api/service.py) para reutilizar o ranker sem alterar o modelo. Organizações sem coordenada ficam em `no_location`
(NÃO ranqueáveis por distância — contadas e informadas, nunca com coordenada inventada); sem perfil declarado ficam em `no_profile`."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger("match.index")

SQL_ORGS = """
SELECT o.id AS org_uuid, o.ong_id, o.ong_tipo, o.municipio_ibge, o.uf, o.ano_fundacao, o.platform_status, o.source, o.source_record_id,
       l.lat, l.lon, l.location_precision, l.geo_quality, l.rankable_by_distance,
       p.capacity_min_kg_day, p.capacity_max_kg_day, p.cold_chamber, p.open_hour, p.open_hour AS _o, p.close_hour, p.open_days_mask, p.accepted_categories,
       p.has_fleet, p.fleet_capacity_kg, p.fleet_refrigerated, p.data_origin AS profile_origin,
       ind.populacao_2026, ind.n_osc_assistencia_municipio, ind.paa_kg_historico_municipio, ind.paa_adesao, ind.n_banco_rbba_municipio
FROM organizations o
JOIN organization_locations l ON l.organization_id = o.id
LEFT JOIN organization_profiles p ON p.organization_id = o.id
LEFT JOIN (SELECT municipio_ibge,
                  max(value) FILTER (WHERE code='populacao_2026') AS populacao_2026,
                  max(value) FILTER (WHERE code='n_osc_assistencia_municipio') AS n_osc_assistencia_municipio,
                  max(value) FILTER (WHERE code='paa_kg_historico_municipio') AS paa_kg_historico_municipio,
                  max(value) FILTER (WHERE code='paa_adesao') AS paa_adesao,
                  max(value) FILTER (WHERE code='n_banco_rbba_municipio') AS n_banco_rbba_municipio
           FROM public_indicators GROUP BY municipio_ibge) ind ON ind.municipio_ibge = o.municipio_ibge
"""


@dataclass
class OrgIndex:
    orgs: pd.DataFrame                     # ranqueáveis (com coordenada e perfil), colunas no formato da Fase 1
    terr: pd.DataFrame                     # municípios: codigo_ibge, latitude, longitude, location_precision
    categories: list[str]
    n_total: int
    n_no_location: int
    n_no_profile: int
    loaded_at: float = field(default_factory=time.time)
    load_seconds: float = 0.0


def load_org_index(engine: Engine, categories: list[str] | None = None) -> OrgIndex:
    t0 = time.perf_counter()
    with engine.connect() as c:
        df = pd.read_sql(text(SQL_ORGS), c)
        terr = pd.read_sql(text("SELECT ibge_code AS codigo_ibge, name AS nome, uf, lat AS latitude, lon AS longitude, location_precision FROM municipalities"), c)
        cats = categories or [r[0] for r in c.execute(text("SELECT code FROM food_categories ORDER BY code"))]
    n_total = len(df)
    df = df.loc[:, ~df.columns.duplicated()].drop(columns=["_o"], errors="ignore")
    has_loc = df["rankable_by_distance"].fillna(False).to_numpy(bool) & df["lat"].notna().to_numpy() & df["lon"].notna().to_numpy()
    has_prof = df["capacity_max_kg_day"].notna().to_numpy()
    n_no_loc, n_no_prof = int((~has_loc).sum()), int((has_loc & ~has_prof).sum())
    df = df[has_loc & has_prof].reset_index(drop=True)
    acc = df["accepted_categories"].apply(lambda x: set(x or []))
    out = pd.DataFrame({
        "org_uuid": df["org_uuid"].astype(str), "ong_id": df["ong_id"], "ong_tipo": df["ong_tipo"], "municipio_ibge": df["municipio_ibge"].astype("Int64").fillna(0).astype(int),
        "uf": df["uf"], "ano_fundacao": df["ano_fundacao"].astype(float), "platform_status": df["platform_status"], "profile_origin": df["profile_origin"],
        "lat": df["lat"].astype(float), "lon": df["lon"].astype(float), "location_precision": df["location_precision"], "geo_quality": df["geo_quality"].fillna("NAO_APLICAVEL"),
        "rankable_by_distance": True, "has_location": True,
        "capacidade_declarada_faixa_max_kg_dia": df["capacity_max_kg_day"].astype(float), "camara_fria_declarada": df["cold_chamber"].astype(bool),
        "horario_abertura_declarado_h": df["open_hour"].astype(float), "horario_fechamento_declarado_h": df["close_hour"].astype(float),
        "dias_funcionamento_declarados_mask": df["open_days_mask"].astype(int), "tem_frota": df["has_fleet"].fillna(False).astype(bool),
        "capacidade_kg": df["fleet_capacity_kg"].astype(float), "refrigerado": df["fleet_refrigerated"].fillna(False).astype(bool),
        "populacao_2026": df["populacao_2026"].fillna(0).astype(float), "n_osc_assistencia_municipio": df["n_osc_assistencia_municipio"].fillna(0).astype(float),
        "paa_kg_historico_municipio": df["paa_kg_historico_municipio"].fillna(0).astype(float), "paa_adesao": df["paa_adesao"].fillna(0).astype(int),
        "tem_banco_rbba_municipio": (df["n_banco_rbba_municipio"].fillna(0) > 0),
    })
    for cat in cats:
        out[f"aceita_{cat}_declarado"] = acc.apply(lambda s, c=cat: c in s).to_numpy(bool)
    res = OrgIndex(orgs=out, terr=terr, categories=cats, n_total=n_total, n_no_location=n_no_loc, n_no_profile=n_no_prof)
    res.load_seconds = round(time.perf_counter() - t0, 2)
    log.info("índice de ONGs: %d ranqueáveis de %d (sem localização: %d; sem perfil declarado: %d) em %.2fs", len(out), n_total, n_no_loc, n_no_prof, res.load_seconds)
    return res
