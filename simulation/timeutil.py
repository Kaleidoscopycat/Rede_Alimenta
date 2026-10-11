"""Aritmética de horário comercial vetorizada (segundos desde 1970-01-01, tratado como horário local sem fuso).

Cada ONG/doador tem janela [open_s, close_s) em segundos do dia e uma máscara de dias (bit0 = segunda ... bit6 = domingo).
"""
from __future__ import annotations

import numpy as np

DAY = 86400


def dow(t: np.ndarray) -> np.ndarray:
    return ((t // DAY) + 3) % 7  # 1970-01-01 foi quinta (3)


def day_open(t, mask):
    return ((mask >> dow(t)) & 1).astype(bool)


def next_open_start(t, open_s, close_s, mask, min_len_s=0):
    """Menor instante >= t em que a janela está aberta e ainda restam >= min_len_s segundos até fechar."""
    t = np.array(t, dtype=np.int64, copy=True)
    for _ in range(16):
        sod = t % DAY
        ok_day = day_open(t, mask)
        too_early = sod < open_s
        too_late = sod > (close_s - np.maximum(min_len_s, 0))
        bad = ~ok_day | too_late
        # antes de abrir em dia aberto: sobe para a abertura
        fix_early = ok_day & too_early & ~too_late
        t = np.where(fix_early, (t // DAY) * DAY + open_s, t)
        if not bad.any():
            break
        t = np.where(bad, ((t // DAY) + 1) * DAY, t)
    # garantia final: alinhar abertura
    sod = t % DAY
    t = np.where(day_open(t, mask) & (sod < open_s), (t // DAY) * DAY + open_s, t)
    return t


def advance_business(t, minutes, open_s, close_s, mask):
    """Soma `minutes` de horário comercial a t (pausa fora da janela/dia fechado). Retorna instante final (nunca fora da janela)."""
    t = np.array(t, dtype=np.int64, copy=True)
    rem = np.asarray(minutes, dtype=np.float64) * 60.0
    rem = np.broadcast_to(rem, t.shape).copy()
    open_s = np.broadcast_to(open_s, t.shape); close_s = np.broadcast_to(close_s, t.shape); mask = np.broadcast_to(mask, t.shape)
    for _ in range(40):
        t = next_open_start(t, open_s, close_s, mask)
        avail = (close_s - (t % DAY)).astype(np.float64)
        done = rem <= avail
        t = np.where(done, t + np.round(rem).astype(np.int64), t)
        rem = np.where(done, 0.0, rem - avail)
        if (rem <= 0).all():
            break
        t = np.where(rem > 0, ((t // DAY) + 1) * DAY, t)
    return t
