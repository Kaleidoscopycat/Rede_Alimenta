"""Scores SEPARADOS: ML_SCORE, BUSINESS_RULE_SCORE, DISTANCE_SCORE e FINAL_SCORE. Nenhuma regra fica escondida no modelo; pesos em core/settings.py (PREMISSAS)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.settings import MatchSettings


def business_rule_score(orgs: pd.DataFrame, quantity_kg: float, remaining_cap_kg: np.ndarray, needs_cold: bool, cfg: MatchSettings) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Regras brandas (0–1), todas observáveis: folga de capacidade, adequação da cadeia fria, tipo da organização, contexto regional.
    Capacidade: 1 − 0,5·(kg/capacidade restante) limitado a [0,5; 1]. Frio: 1,0 se câmara fria E frota refrigerada; 0,8 se só uma (quando exigido).
    Tipo: banco de alimentos RBBA 1,0; demais 0,7 (PREMISSA: especialização logística). Regional: média de {banco RBBA no município, adesão ao PAA} (contexto, não beneficiários)."""
    rem = np.maximum(np.asarray(remaining_cap_kg, dtype=float), 1e-9)
    cap = np.clip(1.0 - 0.5 * (quantity_kg / rem), 0.5, 1.0)
    cam = orgs["camara_fria_declarada"].to_numpy(bool)
    fref = orgs["tem_frota"].fillna(False).to_numpy(bool) & orgs["refrigerado"].fillna(False).to_numpy(bool)
    if needs_cold:
        frio = np.where(cam & fref, 1.0, 0.8)
    else:
        frio = np.ones(len(orgs))
    tipo = np.where(orgs["ong_tipo"].to_numpy() == "BANCO_ALIMENTOS_RBBA", 1.0, 0.7)
    reg = 0.5 * orgs["tem_banco_rbba_municipio"].astype(float).to_numpy() + 0.5 * orgs["paa_adesao"].astype(float).clip(0, 1).to_numpy()
    comp = {"capacidade": cap, "refrigeracao": frio, "tipo_organizacao": tipo, "contexto_regional": reg}
    score = cfg.br_capacity * cap + cfg.br_refrigeration * frio + cfg.br_org_type * tipo + cfg.br_regional * reg
    return np.clip(score, 0, 1), comp


def distance_score(dist_km: np.ndarray, slack_h: np.ndarray, hours_to_expiry: float, cfg: MatchSettings) -> np.ndarray:
    """α·exp(−dist/d0) + (1−α)·folga/validade, com folga = tempo até a validade − espera − deslocamento (limitada a [0,1])."""
    prox = np.exp(-np.asarray(dist_km, dtype=float) / cfg.dist_d0_km)
    folga = np.clip(np.asarray(slack_h, dtype=float) / max(hours_to_expiry, 1e-9), 0, 1)
    return np.clip(cfg.dist_alpha * prox + (1 - cfg.dist_alpha) * folga, 0, 1)


def final_score(ml: np.ndarray, br: np.ndarray, dist: np.ndarray, cfg: MatchSettings) -> np.ndarray:
    return cfg.w_ml * np.asarray(ml) + cfg.w_rule * np.asarray(br) + cfg.w_dist * np.asarray(dist)
