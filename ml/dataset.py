"""Montagem do dataset de pares (lote, ONG) para o modelo de ranking.

Junta atributos REAIS (gold/organizations: ONG, município, PAA) com SIMULADOS (lote, doador, frota, declarado, desfecho).
`data_origin` por coluna é preservado em FEATURE_ORIGIN. Latentes (aptidão, afinidade, capacidade efetiva...) NUNCA entram como feature."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

NUM_FEATURES = [
    # par (SIMULADO, derivado de coordenadas REAIS/PROXY)
    "dist_km", "rank_distancia", "tempo_deslocamento_est_h", "razao_deslocamento_validade",
    # lote (SIMULADO)
    "quantidade_kg", "horas_ate_validade", "tempo_carga_min", "janela_retirada_inicio_h", "janela_retirada_fim_h", "hora_cadastro", "dow_cadastro",
    # ONG declarada (SIMULADO, com ruído)
    "frota_capacidade_declarada_kg", "capacidade_declarada_max_kg_dia", "n_categorias_aceitas_declaradas",
    "horario_abertura_declarado_h", "horario_fechamento_declarado_h", "n_dias_funcionamento_declarados",
    # ONG/município (REAL)
    "populacao_2026", "n_osc_assistencia_municipio", "paa_kg_historico_municipio", "ano_fundacao",
    # derivadas (SIMULADO)
    "kg_sobre_capacidade", "kg_sobre_frota", "horas_validade_menos_viagem",
]
BOOL_FEATURES = [
    "mesmo_municipio", "tem_frota", "frota_refrigerada_declarada", "camara_fria_declarada", "categoria_aceita_declarada", "dia_comum_declarado",
    "elegivel_regra", "exige_refrigeracao", "contem_alergenico", "paa_adesao", "tem_banco_rbba_municipio",
    "precisa_frio_sem_frio_declarado",
]
CAT_FEATURES = ["ong_tipo", "categoria", "perecibilidade", "location_precision_doador", "location_precision_ong", "geo_quality_ong", "uf"]
FEATURES = NUM_FEATURES + BOOL_FEATURES + CAT_FEATURES

FEATURE_ORIGIN = {}
for c in ["populacao_2026", "n_osc_assistencia_municipio", "paa_kg_historico_municipio", "ano_fundacao", "paa_adesao", "tem_banco_rbba_municipio", "uf", "ong_tipo"]:
    FEATURE_ORIGIN[c] = "PUBLIC (REAL)"
for c in ["dist_km", "rank_distancia", "tempo_deslocamento_est_h", "mesmo_municipio", "location_precision_doador", "location_precision_ong", "geo_quality_ong"]:
    FEATURE_ORIGIN[c] = "DERIVADO de coordenadas PUBLIC/PROXY + doador SIMULATED"
for c in FEATURES:
    FEATURE_ORIGIN.setdefault(c, "SIMULATED")

FORBIDDEN = {"resposta", "coletou", "coletou_dentro_validade", "target", "horas_resposta", "horas_ate_coleta", "proposta_em", "resposta_em", "coleta_em", "motivos_exclusao"}
assert not (set(FEATURES) & FORBIDDEN)


def build_pairs(tag: str = "main") -> pd.DataFrame:
    s = ROOT / "data" / "simulated" / tag
    pairs = pd.read_parquet(s / "sim_pair_outcome.parquet")
    lot = pd.read_parquet(s / "sim_lot.parquet", columns=["lot_id", "created_at", "categoria", "perecibilidade", "quantidade_kg", "horas_ate_validade", "exige_refrigeracao",
                                                           "tempo_carga_min", "janela_retirada_inicio_h", "janela_retirada_fim_h", "contem_alergenico"])
    org = pd.read_parquet(ROOT / "data" / "gold" / "organizations.parquet",
                          columns=["ong_id", "uf", "populacao_2026", "n_osc_assistencia_municipio", "paa_kg_historico_municipio", "ano_fundacao", "paa_adesao", "tem_banco_rbba_municipio"])
    df = pairs.merge(lot, on="lot_id", how="left", validate="m:1").merge(org, on="ong_id", how="left", validate="m:1")
    ts = pd.to_datetime(df["created_at"])
    df["hora_cadastro"] = ts.dt.hour + ts.dt.minute / 60
    df["dow_cadastro"] = ts.dt.dayofweek
    cap = df["capacidade_declarada_max_kg_dia"].replace(0, np.nan)
    df["kg_sobre_capacidade"] = df["quantidade_kg"] / cap
    df["kg_sobre_frota"] = df["quantidade_kg"] / df["frota_capacidade_declarada_kg"].replace(0, np.nan)
    df["horas_validade_menos_viagem"] = df["horas_ate_validade"] - df["tempo_deslocamento_est_h"]
    df["precisa_frio_sem_frio_declarado"] = df["exige_refrigeracao"].astype(bool) & ~(df["camara_fria_declarada"].astype(bool) | df["frota_refrigerada_declarada"].astype(bool))
    for c in BOOL_FEATURES:
        df[c] = df[c].astype("float")
    df["created_at"] = ts
    df["target"] = df["target"].astype(int)
    return df


def temporal_split(df: pd.DataFrame, frac=(0.70, 0.15, 0.15)) -> pd.DataFrame:
    """Divisão temporal por LOTE: todos os pares de um lote ficam no mesmo conjunto (sem vazamento entre pares do mesmo lote)."""
    lots = df.groupby("lot_id")["created_at"].min().sort_values(kind="stable")
    n = len(lots); a, b = int(n * frac[0]), int(n * (frac[0] + frac[1]))
    split = pd.Series("test", index=lots.index); split.iloc[:a] = "train"; split.iloc[a:b] = "val"
    out = df.copy(); out["split"] = out["lot_id"].map(split)
    return out
