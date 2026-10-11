"""Camada GOLD (dados REAIS): organizações candidatas e território. Dados SIMULADOS NÃO entram aqui;
eles se juntam aos reais apenas em gold/pairs (ml/dataset.py), preservando `data_origin`."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import GOLD, SILVER, get_logger, register_layer

log = get_logger("gold")


def run() -> dict:
    GOLD.mkdir(parents=True, exist_ok=True)
    mun = pd.read_parquet(SILVER / "municipios.parquet")
    osc = pd.read_parquet(SILVER / "osc.parquet")
    rbba = pd.read_parquet(SILVER / "rbba.parquet")
    paa = pd.read_parquet(SILVER / "paa_compra_doacao.parquet")
    adesao = pd.read_parquet(SILVER / "paa_municipios.parquet")

    cand = osc[osc["elegivel_proxy"] & osc["municipio_valido"]].copy()
    n_cand_mun = cand.groupby("municipio_ibge").size().rename("n_osc_assistencia_municipio")
    rb_mun = rbba.dropna(subset=["municipio_ibge"]).groupby("municipio_ibge").size().rename("n_banco_rbba_municipio")
    paa_kg = paa.groupby("codigo_ibge")["kg_adquiridos"].sum().rename("paa_kg_historico_municipio")  # PROXY (cobertura instável)
    last = adesao["anomes_s"].max()
    paa_ades = adesao[adesao["anomes_s"] == last].set_index("codigo_ibge")["adesao"].rename("paa_adesao")

    terr = mun.drop(columns=["nome_norm", "codigo_ibge6"]).set_index("codigo_ibge")
    terr = terr.join([n_cand_mun, rb_mun, paa_kg, paa_ades])
    terr[["n_osc_assistencia_municipio", "n_banco_rbba_municipio"]] = terr[["n_osc_assistencia_municipio", "n_banco_rbba_municipio"]].fillna(0).astype(int)
    terr["tem_banco_rbba_municipio"] = terr["n_banco_rbba_municipio"] > 0
    terr["paa_kg_historico_municipio"] = terr["paa_kg_historico_municipio"].fillna(0.0)
    terr["paa_adesao"] = terr["paa_adesao"].fillna(0).astype(int)
    terr = terr.reset_index(); terr["data_origin"] = "PUBLIC"
    p = GOLD / "territory.parquet"; terr.to_parquet(p, index=False); register_layer("gold_territory", "gold", p, len(terr))

    coords = mun.set_index("codigo_ibge")[["latitude", "longitude"]]
    c = cand.join(coords, on="municipio_ibge").rename(columns={"latitude": "lat", "longitude": "lon"})
    c = c[["ong_id", "ong_tipo", "id_osc", "municipio_ibge", "uf", "lat", "lon", "location_precision", "geo_quality",
           "natureza_juridica", "ano_fundacao", "area_assistencia_social", "area_desenv_direitos", "area_saude", "area_educacao_pesquisa",
           "area_religiao", "source_id", "pipeline_version", "data_origin"]].rename(columns={"id_osc": "native_id"})
    c["native_id"] = c["native_id"].astype(str); c["modalidade_rbba"] = None
    r = rbba.rename(columns={"rbba_id": "native_id", "modalidade": "modalidade_rbba"})
    r = r[["ong_id", "ong_tipo", "native_id", "municipio_ibge", "uf", "lat", "lon", "location_precision", "geo_quality",
           "modalidade_rbba", "source_id", "pipeline_version", "data_origin"]]
    orgs = pd.concat([c, r], ignore_index=True)
    orgs["municipio_ibge"] = orgs["municipio_ibge"].astype("Int64")
    orgs = orgs.merge(terr[["codigo_ibge", "populacao_2026", "n_osc_assistencia_municipio", "tem_banco_rbba_municipio", "paa_adesao",
                            "paa_kg_historico_municipio"]], left_on="municipio_ibge", right_on="codigo_ibge", how="left").drop(columns="codigo_ibge")
    orgs["rankable_by_distance"] = orgs["lat"].notna() & orgs["lon"].notna() & (orgs["location_precision"] != "NONE")
    orgs["ano_fundacao"] = orgs["ano_fundacao"].astype("Int16")
    p = GOLD / "organizations.parquet"; orgs.to_parquet(p, index=False); register_layer("gold_organizations", "gold", p, len(orgs))
    log.info("gold: organizations=%d territory=%d", len(orgs), len(terr))
    return {"organizations": len(orgs), "territory": len(terr)}


if __name__ == "__main__":
    run()
