"""Regras ELIMINATÓRIAS de elegibilidade — explícitas, testáveis, registradas na resposta. Usa só atributos DECLARADOS da ONG (nunca latentes do simulador)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from api.service import DETOUR, SERVICE_MIN, SPEED_LONG, SPEED_SHORT
from pipelines.geo import estimated_travel_hours
from .schedule import pickup_wait_hours

# código -> descrição (PT-BR)
RULES: dict[str, str] = {
    "E_LOCALIZACAO_AUSENTE": "organização sem posição conhecida: não ranqueável por distância",
    "E_NAO_CADASTRADA": "organização é apenas registro de fonte pública e ainda não se cadastrou/aceitou a plataforma (obrigatório para doações reais)",
    "E_CATEGORIA_NAO_ACEITA": "alguma categoria do lote não consta entre as aceitas declaradas pela ONG (lote misto: a ONG precisa aceitar todas)",
    "E_CAPACIDADE": "quantidade acima da capacidade de recebimento restante declarada (capacidade diária − reservas do dia)",
    "E_REFRIGERACAO": "alimento exige refrigeração e a ONG não declara câmara fria nem frota refrigerada",
    "E_HORARIO": "não há horário comum entre a janela de coleta do doador e o funcionamento da ONG nos próximos 7 dias",
    "E_PRAZO_VALIDADE": "espera pela janela + tempo de deslocamento estimado ≥ tempo restante até a validade",
}
RULE_ORDER = list(RULES)


@dataclass
class DonationCtx:
    """Entrada do motor: tudo já confirmado/validado (a doação só chega aqui no estado READY)."""
    categoria: str
    quantity_kg: float
    hours_to_expiry: float
    needs_cold: bool
    pickup_days_mask: int
    pickup_start_h: float
    pickup_end_h: float
    load_minutes: float
    lat: float
    lon: float
    municipio_ibge: int
    location_precision: str
    allergen: bool
    data_origin: str
    categorias: tuple[str, ...] = ()  # Fase 3 P1: todas as categorias do lote (lote misto); vazio ⇒ só `categoria`


def travel_hours(dist_km: np.ndarray) -> np.ndarray:
    """Tempo estimado de deslocamento = dist × desvio ÷ velocidade + serviço (premissas da Fase 1; NÃO é rota)."""
    d = np.asarray(dist_km, dtype=float)
    speed = np.where(d <= 15, SPEED_SHORT, SPEED_LONG)
    return estimated_travel_hours(d, DETOUR, speed, SERVICE_MIN)


def evaluate(ctx: DonationCtx, orgs: pd.DataFrame, dist_km: np.ndarray, remaining_cap_kg: np.ndarray, now_local: dt.datetime) -> dict[str, Any]:
    """Aplica TODAS as regras a cada organização de `orgs`. Retorna máscaras por regra, tempos e `eligible`.

    `orgs` deve conter: has_location(bool), platform_status, aceita_<CAT>_declarado, camara_fria_declarada, tem_frota, refrigerado,
    dias_funcionamento_declarados_mask, horario_abertura_declarado_h, horario_fechamento_declarado_h.
    """
    n = len(orgs)
    fail: dict[str, np.ndarray] = {}
    fail["E_LOCALIZACAO_AUSENTE"] = ~orgs["has_location"].to_numpy(bool)
    fail["E_NAO_CADASTRADA"] = (orgs["platform_status"].to_numpy() != "REGISTERED") if ctx.data_origin != "SIMULATED" else np.zeros(n, bool)
    cats = tuple(dict.fromkeys((ctx.categoria, *ctx.categorias)))  # a ONG precisa aceitar TODAS as categorias do lote
    accepts_all = np.ones(n, bool)
    for c in cats:
        accepts_all &= orgs[f"aceita_{c}_declarado"].to_numpy(bool)
    fail["E_CATEGORIA_NAO_ACEITA"] = ~accepts_all
    fail["E_CAPACIDADE"] = ctx.quantity_kg > np.asarray(remaining_cap_kg, dtype=float)
    cold_ok = orgs["camara_fria_declarada"].to_numpy(bool) | (orgs["tem_frota"].fillna(False).to_numpy(bool) & orgs["refrigerado"].fillna(False).to_numpy(bool))
    fail["E_REFRIGERACAO"] = (~cold_ok) if ctx.needs_cold else np.zeros(n, bool)
    wait = pickup_wait_hours(now_local, ctx.pickup_days_mask, ctx.pickup_start_h, ctx.pickup_end_h, ctx.load_minutes,
                             orgs["dias_funcionamento_declarados_mask"].to_numpy(int), orgs["horario_abertura_declarado_h"].to_numpy(float),
                             orgs["horario_fechamento_declarado_h"].to_numpy(float))
    fail["E_HORARIO"] = np.isnan(wait)
    dist = np.asarray(dist_km, dtype=float)
    trav = travel_hours(np.nan_to_num(dist, nan=0.0))
    fail["E_PRAZO_VALIDADE"] = np.isnan(wait) | ((np.nan_to_num(wait) + trav) >= ctx.hours_to_expiry) | np.isnan(dist)
    # E_PRAZO só conta quando o horário existe (evita dupla contagem do mesmo motivo)
    fail["E_PRAZO_VALIDADE"] &= ~fail["E_HORARIO"]
    elig = ~np.any(np.vstack([fail[k] for k in RULE_ORDER]), axis=0)
    return {"fail": fail, "wait_h": wait, "travel_h": trav, "eligible": elig, "dist_km": dist}


def reasons_for(res: dict[str, Any], i: int) -> list[str]:
    return [k for k in RULE_ORDER if bool(res["fail"][k][i])]
