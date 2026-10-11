"""Janela de coleta × horário de funcionamento da ONG (vetorizado). Convenção de dias: bit 0 = segunda ... bit 6 = domingo (igual à Fase 1)."""
from __future__ import annotations

import datetime as dt

import numpy as np


def pickup_wait_hours(now_local: dt.datetime, donor_days_mask: int, donor_start_h: float, donor_end_h: float, load_minutes: float,
                      org_days_mask: np.ndarray, org_open_h: np.ndarray, org_close_h: np.ndarray, horizon_days: int = 7) -> np.ndarray:
    """Horas de espera até a primeira retirada viável em cada ONG (NaN se não há horário comum no horizonte).

    Retirada viável no dia d: dia permitido para o doador E para a ONG, e interseção [max(início_doador, abertura_ONG, agora), min(fim_doador, fechamento_ONG)]
    com folga ≥ tempo de carga. É uma regra simples e explícita; não considera feriados nem a duração do transporte até a ONG.
    """
    n = len(org_days_mask)
    wait = np.full(n, np.nan)
    now_h = now_local.hour + now_local.minute / 60 + now_local.second / 3600
    need = load_minutes / 60.0
    org_days_mask = np.asarray(org_days_mask).astype(int)
    org_open_h = np.asarray(org_open_h, dtype=float)
    org_close_h = np.asarray(org_close_h, dtype=float)
    for d in range(horizon_days + 1):
        wd = (now_local.weekday() + d) % 7
        if not (donor_days_mask >> wd) & 1:
            continue
        org_ok = ((org_days_mask >> wd) & 1).astype(bool)
        start = np.maximum(donor_start_h, org_open_h)
        end = np.minimum(donor_end_h, org_close_h)
        if d == 0:
            start = np.maximum(start, now_h)
        ok = org_ok & (start + need <= end) & np.isnan(wait)
        wait[ok] = d * 24.0 + start[ok] - now_h
    return wait
