"""Agregação dos itens no lote (Fase 3 Parte 1, seção 2.2) — funções PURAS, usadas pelo match.

Regras (critério conservador):
  quantity_kg        = soma dos kg de todos os itens (None se nenhum item tem peso; `incomplete` indica itens sem peso);
  validade do lote   = a MAIS PRÓXIMA entre os itens (o lote inteiro só pode ser entregue antes dela);
  exige_refrigeracao = verdadeiro se QUALQUER item exigir (None se nenhum exige e algum é desconhecido);
  perecibilidade     = a MAIS RESTRITIVA (maior risco) entre os itens;
  categoria          = a de MAIOR PESO (empate: a mais perecível, depois ordem alfabética); `categories` guarda todas, da de maior para a de menor peso;
  lote misto         = mais de uma categoria. Nenhuma categoria nova é criada na taxonomia.
LIMITAÇÃO: o ranker foi treinado e avaliado SÓ com lotes SIMULADOS de uma única categoria; em lote misto o desempenho é DESCONHECIDO (ver docs/DONATION_ITEMS.md)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from core.settings import DONATION, TZ

# ordem crescente de risco (mesma de ml.semantic.classifier.PERECIB; repetida aqui para o módulo ser puro e sem dependência de modelo)
PERECIB_RANK = {"NAO_PERECIVEL": 0, "PERECIVEL_BAIXO_RISCO": 1, "PERECIVEL_REFRIGERADO_CONGELADO": 2, "PRONTO_ALTO_RISCO": 3}

MIXED_BATCH_LIMITATION = ("Lote misto: o modelo de ranking foi treinado e avaliado somente com lotes SIMULADOS de uma única categoria; "
                          "o desempenho em lotes de várias categorias é DESCONHECIDO. O ML_SCORE usa a categoria predominante (maior peso); "
                          "a elegibilidade exige que a ONG aceite TODAS as categorias do lote.")
SPREAD_ADVICE = ("A validade mais próxima define o prazo de todo o lote. Considere separar os itens de validade curta em outra doação.")


@dataclass
class ItemAgg:
    id: int | None
    categoria: str | None
    produto: str | None
    quantity_kg: float | None
    expires_at: dt.datetime | None
    exige_refrigeracao: bool | None
    perecibilidade: str | None


@dataclass
class Aggregate:
    n_items: int = 0
    quantity_kg: float | None = None
    incomplete_weight: bool = False
    expires_at: dt.datetime | None = None
    validity_days: int | None = None
    exige_refrigeracao: bool | None = None
    perecibilidade: str | None = None
    categoria: str | None = None
    categories: list[str] = field(default_factory=list)
    is_mixed_batch: bool = False
    spread_days: int | None = None
    spread_warning: bool = False
    short_validity_item_ids: list[int] = field(default_factory=list)
    nearest_item_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def aggregate(items: list[ItemAgg], now: dt.datetime, spread_warn_days: int | None = None) -> Aggregate:
    warn = DONATION.validity_spread_warn_days if spread_warn_days is None else spread_warn_days
    agg = Aggregate(n_items=len(items))
    if not items:
        return agg
    kgs = [i.quantity_kg for i in items if i.quantity_kg is not None]
    agg.quantity_kg = round(sum(kgs), 6) if kgs else None
    agg.incomplete_weight = len(kgs) < len(items)
    exp = [i for i in items if i.expires_at is not None]
    if exp:
        nearest = min(i.expires_at for i in exp)
        farthest = max(i.expires_at for i in exp)
        agg.expires_at = nearest
        agg.validity_days = (nearest.astimezone(TZ).date() - now.astimezone(TZ).date()).days
        agg.nearest_item_ids = [i.id for i in exp if i.expires_at == nearest and i.id is not None]
        agg.spread_days = (farthest.astimezone(TZ).date() - nearest.astimezone(TZ).date()).days
        agg.spread_warning = agg.spread_days > warn
        if agg.spread_warning:
            # itens "de validade curta": os que vencem até `warn` dias depois da validade mais próxima
            cut = nearest + dt.timedelta(days=warn)
            agg.short_validity_item_ids = [i.id for i in exp if i.expires_at <= cut and i.id is not None]
    flags = [i.exige_refrigeracao for i in items]
    agg.exige_refrigeracao = True if any(f is True for f in flags) else (None if any(f is None for f in flags) else False)
    pers = [i.perecibilidade for i in items if i.perecibilidade in PERECIB_RANK]
    agg.perecibilidade = max(pers, key=lambda p: PERECIB_RANK[p]) if pers else None
    weight: dict[str, float] = {}
    per_of: dict[str, str | None] = {}
    for i in items:
        if i.categoria:
            weight[i.categoria] = weight.get(i.categoria, 0.0) + float(i.quantity_kg or 0.0)
            per_of.setdefault(i.categoria, i.perecibilidade)
    ordered = sorted(weight, key=lambda c: (-weight[c], -PERECIB_RANK.get(per_of.get(c) or "", -1), c))
    agg.categories = ordered
    agg.categoria = ordered[0] if ordered else None
    agg.is_mixed_batch = len(ordered) > 1
    return agg


def apply_to_donation(donation: Any, agg: Aggregate, now: dt.datetime) -> None:
    """Grava os agregados no cabeçalho (Donation). Só para doações com itens detalhados (nunca para históricas do simulador)."""
    donation.quantity_kg = agg.quantity_kg
    donation.expires_at = agg.expires_at
    donation.validity_days = agg.validity_days
    donation.exige_refrigeracao = agg.exige_refrigeracao
    donation.perecibilidade = agg.perecibilidade
    donation.categoria = agg.categoria
    donation.categories = agg.categories or None
    donation.is_mixed_batch = agg.is_mixed_batch
    donation.aggregated_at = now
    donation.updated_at = now
