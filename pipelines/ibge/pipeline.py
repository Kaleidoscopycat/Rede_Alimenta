"""IBGE: municípios, população 2026 e coordenadas (PROXY de terceiros). RAW -> BRONZE -> SILVER."""
from __future__ import annotations

import json

import pandas as pd

from ..common import BRONZE, RAW, SILVER, get_logger, norm_text, register, register_layer, trace_columns, now_utc

log = get_logger("ibge")
SID = "ibge_municipios"


def _uf(m: dict) -> tuple[str, str]:
    node = m["microrregiao"]["mesorregiao"]["UF"] if m.get("microrregiao") else m["regiao-imediata"]["regiao-intermediaria"]["UF"]
    return node["sigla"], node["regiao"]["sigla"]


def run() -> dict:
    ts = now_utc()
    BRONZE.mkdir(parents=True, exist_ok=True)
    SILVER.mkdir(parents=True, exist_ok=True)
    # ---------- BRONZE: municípios
    mj = json.loads((RAW / "ibge/ibge_municipios.json").read_text(encoding="utf-8"))
    rows = []
    for m in mj:
        uf, reg = _uf(m)
        rows.append({"codigo_ibge": int(m["id"]), "nome": m["nome"], "uf": uf, "regiao": reg})
    mun = pd.DataFrame(rows)
    mun = trace_columns(mun, "ibge_municipios", "IBGE", "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
                        "Municípios (API Localidades)", "não verificável", ts)
    p = BRONZE / "ibge_municipios.parquet"; mun.to_parquet(p, index=False); register_layer("ibge_municipios", "bronze", p, len(mun))
    # ---------- BRONZE: população
    pj = json.loads((RAW / "ibge/ibge_populacao_municipios_2026.json").read_text(encoding="utf-8"))
    series = pj[0]["resultados"][0]["series"]
    pop = pd.DataFrame([{"codigo_ibge": int(s["localidade"]["id"]), "populacao_2026": int(s["serie"]["2026"])}
                        for s in series if str(s["serie"].get("2026", "")).isdigit()])
    pop = trace_columns(pop, "ibge_populacao", "IBGE/SIDRA", "https://servicodados.ibge.gov.br/api/v3/agregados/6579",
                        "População estimada 2026", "2026", ts)
    p = BRONZE / "ibge_populacao.parquet"; pop.to_parquet(p, index=False); register_layer("ibge_populacao", "bronze", p, len(pop))
    # ---------- BRONZE: coordenadas (PROXY)
    co = pd.read_csv(RAW / "ibge_coords/kelvins_municipios.csv", usecols=["codigo_ibge", "latitude", "longitude"])
    co = trace_columns(co, "ibge_coords", "kelvins/municipios-brasileiros (terceiros, MIT)",
                       "https://github.com/kelvins/municipios-brasileiros", "Coordenadas de municípios", "commit 2025-12-10", ts)
    p = BRONZE / "ibge_coords.parquet"; co.to_parquet(p, index=False); register_layer("ibge_coords", "bronze", p, len(co))
    # ---------- SILVER: tabela de municípios (única fonte de verdade territorial)
    s = mun[["codigo_ibge", "nome", "uf", "regiao"]].merge(pop[["codigo_ibge", "populacao_2026"]], on="codigo_ibge", how="left", validate="1:1")
    s = s.merge(co[["codigo_ibge", "latitude", "longitude"]], on="codigo_ibge", how="left", validate="1:1")
    s["nome_norm"] = s["nome"].map(norm_text)
    s["codigo_ibge6"] = s["codigo_ibge"] // 10
    s["location_precision"] = "MUNICIPALITY_CENTROID"
    s["coord_origin"] = "PROXY_TERCEIROS_MIT"
    s["data_origin"] = "PUBLIC"
    s["pipeline_version"] = mun["pipeline_version"].iloc[0]
    p = SILVER / "municipios.parquet"; s.to_parquet(p, index=False); register_layer("ibge_municipios", "silver", p, len(s))
    for sid, df in (("ibge_populacao", pop), ("ibge_coords", co)):
        register(sid, source_name=df["source_name"].iloc[0], source_url=df["source_url"].iloc[0], n_records_raw=int(len(df)))
    register("ibge_municipios", n_records_raw=int(len(mun)))
    log.info("silver municípios: %d (sem população: %d; sem coordenada: %d)", len(s), s.populacao_2026.isna().sum(), s.latitude.isna().sum())
    return {"municipios": len(s)}


if __name__ == "__main__":
    run()
