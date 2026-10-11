"""PAA (MDS/SAGI, CC-BY): execução compra c/ doação simultânea, leite e adesão municipal.
Papel: contexto territorial/sazonalidade (PAA NÃO traz produto/categoria). RAW -> BRONZE -> SILVER."""
from __future__ import annotations

import pandas as pd

from ..common import BRONZE, RAW, SILVER, get_logger, now_utc, register, register_layer, trace_columns

log = get_logger("paa")
URL = "https://aplicacoes.mds.gov.br/sagi/servicos/misocial"
DEFS = {
    "paa_compra_doacao": ("paa_execucao_compra_doacao_simultanea.csv", "PAA Compra c/ Doação Simultânea",
                          {"paa_qtd_agricul_familiar_exec_compra_doacao_simul_i": "n_agricultores",
                           "paa_vlr_pago_exec_compra_doacao_simul_d": "valor_pago_rs",
                           "paa_qtd_alim_adquiridos_exec_compra_doacao_simul_d": "kg_adquiridos"}),
    "paa_leite": ("paa_execucao_leite.csv", "PAA Incentivo ao Leite",
                  {"paa_qtd_agricul_familiar_exec_incentivo_leite_i": "n_agricultores",
                   "paa_vlr_pago_exec_incentivo_leite_d": "valor_pago_rs",
                   "paa_qtd_alim_adquiridos_exec_incentivo_leite_i": "qtd_leite"}),
    "paa_municipios": ("paa_municipios_aderidos_2026.csv", "PAA Municípios Aderidos",
                       {"paa_indicador_adesao_municipio_i": "adesao"}),
}


def run() -> dict:
    ts = now_utc()
    BRONZE.mkdir(parents=True, exist_ok=True); SILVER.mkdir(parents=True, exist_ok=True)
    mun = pd.read_parquet(SILVER / "municipios.parquet", columns=["codigo_ibge", "codigo_ibge6"])
    map6 = mun.set_index("codigo_ibge6")["codigo_ibge"]
    out = {}
    for sid, (fname, title, ren) in DEFS.items():
        df = pd.read_csv(RAW / "paa_mds" / fname)
        keep = ["codigo_ibge", "anomes_s"] + list(ren)
        df = df[keep].rename(columns={"codigo_ibge": "codigo_ibge6", **ren})
        df = trace_columns(df, sid, "MDS/SAGI", URL, title, "2026-06 (anomes_s máx.)", ts)
        p = BRONZE / f"{sid}.parquet"; df.to_parquet(p, index=False); register_layer(sid, "bronze", p, len(df))
        # SILVER: chave de 7 dígitos, ano/mês, sem negativos/NaN silenciosos (descartes são CONTADOS)
        s = df.copy()
        s["codigo_ibge"] = s["codigo_ibge6"].map(map6)
        n_sem_mun = int(s["codigo_ibge"].isna().sum())
        num = [c for c in ren.values()]
        n_neg = int((s[num] < 0).any(axis=1).sum())
        s = s.dropna(subset=["codigo_ibge"]); s = s[~(s[num] < 0).any(axis=1)]
        s["codigo_ibge"] = s["codigo_ibge"].astype(int)
        s["ano"] = s["anomes_s"] // 100; s["mes"] = s["anomes_s"] % 100
        p = SILVER / f"{sid}.parquet"; s.to_parquet(p, index=False); register_layer(sid, "silver", p, len(s))
        register(sid, source_name="MDS/SAGI", source_url=URL, n_records_raw=int(len(df)),
                 silver_descartes={"sem_municipio_ibge": n_sem_mun, "valores_negativos": n_neg})
        log.info("%s: raw=%d silver=%d (sem município=%d, negativos=%d)", sid, len(df), len(s), n_sem_mun, n_neg)
        out[sid] = len(s)
    return out


if __name__ == "__main__":
    run()
