"""Organizações receptoras REAIS: IPEA/Mapa das OSCs e MDS/RBBA. RAW -> BRONZE -> SILVER.

Minimização (LGPD): CNPJ, razão social e nome fantasia NÃO são levados ao BRONZE/SILVER
(só `id_osc`, município/UF, natureza jurídica, ano de fundação e flags de área).
Pseudonimização: `ong_id` = hash determinístico (identificador da fonte + sal de projeto); usado
para ligar tabelas SIMULADAS à ONG real sem expor o nome/CNPJ junto a atributos simulados.
"""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import pandas as pd

from ..common import BRONZE, RAW, SILVER, get_logger, norm_text, now_utc, register, register_layer, trace_columns
from ..geo import geo_quality_from_distance, haversine_km, location_precision

log = get_logger("organizations")
SALT = os.environ.get("ONG_ID_SALT", "rede-alimenta-ia-v1")  # pseudonimização; NÃO é segredo criptográfico
AREA_MAP = {
    "Habitação": "area_habitacao", "Saúde": "area_saude", "Cultura e recreação": "area_cultura_recreacao",
    "Educação e pesquisa": "area_educacao_pesquisa", "Assistência social": "area_assistencia_social",
    "Religião": "area_religiao",
    "Associações patronais, profissionais e de produtores rurais": "area_assoc_patronais",
    "Meio ambiente e proteção animal": "area_meio_ambiente", "Desenvolvimento e defesa de direitos": "area_desenv_direitos",
    "Outros": "area_outros", "Outras atividades associativas": "area_outras_associativas",
}
IPEA_URL = "https://dados.gov.br/dados/conjuntos-dados/mapaosc"
RBBA_URL = "https://alimentacidades.digital/rbba/api/resumo"


def pseudo_id(source: str, native_id) -> str:
    return "ONG-" + hashlib.sha256(f"{SALT}|{source}|{native_id}".encode()).hexdigest()[:12]


def run_ipea() -> pd.DataFrame:
    ts = now_utc()
    usecols = ["id_osc", "cd_natureza_juridica_osc", "edmu_cd_municipio", "eduf_sg_uf", "dt_fundacao_osc", *AREA_MAP]
    parts = []
    for ch in pd.read_csv(RAW / "ipea_osc/area_subarea.csv", sep=";", usecols=usecols, chunksize=250_000, low_memory=False):
        ch = ch.rename(columns=AREA_MAP)
        for c in AREA_MAP.values():
            ch[c] = ch[c].fillna(0).astype("int8")
        ch["edmu_cd_municipio"] = ch["edmu_cd_municipio"].astype("Int64")
        ch["ano_fundacao"] = pd.to_datetime(ch["dt_fundacao_osc"], errors="coerce").dt.year.astype("Int16")
        ch = ch.drop(columns=["dt_fundacao_osc"])
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    df = df.rename(columns={"edmu_cd_municipio": "municipio_ibge", "eduf_sg_uf": "uf", "cd_natureza_juridica_osc": "natureza_juridica"})
    n_raw = len(df)
    df = trace_columns(df, "ipea_osc_area", "IPEA", IPEA_URL, "Mapa das OSCs: área/subárea", "não verificável", ts)
    p = BRONZE / "ipea_osc.parquet"; df.to_parquet(p, index=False); register_layer("ipea_osc_area", "bronze", p, n_raw)
    # ---- SILVER
    mun = pd.read_parquet(SILVER / "municipios.parquet", columns=["codigo_ibge", "uf"]).rename(columns={"uf": "uf_ibge"})
    s = df.merge(mun, left_on="municipio_ibge", right_on="codigo_ibge", how="left").drop(columns=["codigo_ibge"])
    s["municipio_valido"] = s["uf_ibge"].notna()
    s["uf"] = s["uf"].fillna(s["uf_ibge"])
    s["ong_tipo"] = "OSC_ASSISTENCIA"
    s["elegivel_proxy"] = s["area_assistencia_social"] == 1  # PROXY: não há flag de segurança alimentar
    s["has_municipality"] = s["municipio_valido"]
    s["location_precision"] = np.where(s["has_municipality"], "MUNICIPALITY_CENTROID", "NONE")
    s["geo_quality"] = "NAO_APLICAVEL"
    s["ong_id"] = [pseudo_id("ipea_osc", v) for v in s["id_osc"]]
    s = s.drop(columns=["uf_ibge", "has_municipality"])
    p = SILVER / "osc.parquet"; s.to_parquet(p, index=False); register_layer("ipea_osc_area", "silver", p, len(s))
    register("ipea_osc_area", source_name="IPEA", source_url=IPEA_URL, n_records_raw=n_raw,
             elegiveis_proxy=int(s["elegivel_proxy"].sum()), sem_municipio=int((~s["municipio_valido"]).sum()),
             pii_minimizacao="CNPJ, razão social e nome fantasia não ingeridos")
    log.info("OSC: %d linhas; elegíveis proxy=%d; sem município válido=%d", len(s), s.elegivel_proxy.sum(), (~s.municipio_valido).sum())
    return s


def run_rbba() -> pd.DataFrame:
    ts = now_utc()
    d = json.loads((RAW / "rbba/rbba_resumo.json").read_text(encoding="utf-8"))
    rows = []
    for f in d["pontos"]["features"]:
        lon, lat = f["geometry"]["coordinates"]; q = f["properties"]
        rows.append({"rbba_id": q["identificador"], "nome": q["nome"], "cidade": q["cidade"], "uf": q["uf"],
                     "modalidade": q["modalidade"], "lat_raw": lat, "lon_raw": lon})
    b = trace_columns(pd.DataFrame(rows), "rbba_resumo", "MDS/Alimenta Cidades", RBBA_URL, "RBBA resumo 2025", "2025", ts)
    p = BRONZE / "rbba_pontos.parquet"; b.to_parquet(p, index=False); register_layer("rbba_resumo", "bronze", p, len(b))
    # tabelas de referência agregadas (KPIs/mensal/origens/NOVA) -> BRONZE (json estruturado)
    ref = {"ano": d["ano"], "kpis": d["kpis"], "mensal": d["graficos"]["mensal"], "origens": d["graficos"]["origens"],
           "classificacao_nova": d["graficos"]["classificacao"], "modalidades": d["graficos"]["modalidades"],
           "perdas_momento": d["graficos"]["perdas_momento"], "data_origin": "PUBLIC", "source_id": "rbba_resumo"}
    (BRONZE / "rbba_referencia.json").write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
    # ---- SILVER: casa com município IBGE por nome+UF, geo_quality e location_precision
    mun = pd.read_parquet(SILVER / "municipios.parquet")
    key = mun.assign(k=list(zip(mun.nome_norm, mun.uf))).set_index("k")
    s = b.copy()
    keys = list(zip(s["cidade"].map(norm_text), s["uf"]))
    s["municipio_ibge"] = [int(key["codigo_ibge"].get(k)) if k in key.index else pd.NA for k in keys]
    s["municipio_ibge"] = s["municipio_ibge"].astype("Int64")
    lat_c = np.array([key["latitude"].get(k, np.nan) for k in keys]); lon_c = np.array([key["longitude"].get(k, np.nan) for k in keys])
    s["dist_ponto_centroide_km"] = haversine_km(s["lat_raw"].values, s["lon_raw"].values, lat_c, lon_c)
    s["geo_quality"] = [geo_quality_from_distance(x) for x in s["dist_ponto_centroide_km"]]
    s["location_precision"] = [location_precision(True, g, pd.notna(m)) for g, m in zip(s["geo_quality"], s["municipio_ibge"])]
    use_centroid = s["location_precision"] != "EXACT"
    s["lat"] = np.where(use_centroid, lat_c, s["lat_raw"]); s["lon"] = np.where(use_centroid, lon_c, s["lon_raw"])  # RAW preservado em *_raw
    s["ong_tipo"] = "BANCO_ALIMENTOS_RBBA"; s["elegivel_proxy"] = True
    s["ong_id"] = [pseudo_id("rbba", v) for v in s["rbba_id"]]
    p = SILVER / "rbba.parquet"; s.to_parquet(p, index=False); register_layer("rbba_resumo", "silver", p, len(s))
    register("rbba_resumo", source_name="MDS/Alimenta Cidades", source_url=RBBA_URL, n_records_raw=len(b),
             geo_quality=s["geo_quality"].value_counts().to_dict(), location_precision=s["location_precision"].value_counts().to_dict())
    log.info("RBBA: %d pontos; geo_quality=%s", len(s), s["geo_quality"].value_counts().to_dict())
    return s


def run() -> dict:
    o = run_ipea(); r = run_rbba()
    return {"osc": len(o), "rbba": len(r)}


if __name__ == "__main__":
    run()
