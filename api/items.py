"""Itens da doação (Fase 3 Parte 1): montagem/validação de cada item, agregação no cabeçalho e finalização do rascunho.
Sem dados inventados: peso, validade e refrigeração só existem se o doador informou (ou confirmou uma sugestão do texto)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import item_rules as rules
from api.aggregation import Aggregate, ItemAgg, aggregate, apply_to_donation
from api.item_parser import REVIEW
from core.settings import DONATION, TZ
from database import models as m

EDITABLE = ("DRAFT", "PENDING_CONFIRMATION", "BLOCKED_EXPIRED", "BLOCKED_NO_VALIDITY", "READY")
ITEM_FIELDS = ("produto", "description", "categoria", "quantity", "unit", "unit_weight", "unit_weight_unit", "exige_refrigeracao")


def is_item_managed(d: m.Donation) -> bool:
    """Doação criada pelo fluxo de rascunho/itens (cabeçalho = agregado dos itens). As do fluxo antigo e as históricas não são."""
    return d.aggregated_at is not None


def validity_from_input(validade_data: dt.date | None, validade_mes_ano: str | None) -> tuple[dt.datetime | None, str | None, str | None]:
    """→ (expires_at, precisão, origem). Mês/ano ⇒ último dia do mês (regra da equipe; validade real pode ser anterior)."""
    if validade_data is not None:
        return rules.end_of_day(validade_data), "DAY", "INFORMADA_PELO_DOADOR"
    if validade_mes_ano:
        d = rules.parse_month_year(validade_mes_ano)
        if d is None:
            raise ValueError("validade_mes_ano deve ser MM/AAAA ou AAAA-MM")
        return rules.end_of_day(d), "MONTH", "INFORMADA_MES_ANO"
    return None, None, None


def recompute_item(item: m.DonationItem, now: dt.datetime, unit_mass: dict[str, dict[str, float]], cat_perec: dict[str, str]) -> None:
    """Deriva perecibilidade (da categoria), peso total em kg e dias até a validade. Levanta ValueError (→ 422) em dados inválidos."""
    item.perecibilidade = cat_perec.get(item.categoria) if item.categoria else None
    w = rules.item_weight(item.quantity, item.unit_weight, item.unit_weight_unit, item.categoria, unit_mass.get(item.categoria or ""))
    item.quantity_kg, item.weight_basis = w.quantity_kg, w.basis
    item.validity_days = None if item.expires_at is None else rules.days_until(item.expires_at.astimezone(TZ).date(), now.astimezone(TZ).date())
    item.updated_at = now


def item_weight_info(item: m.DonationItem, unit_mass: dict[str, dict[str, float]]) -> tuple[bool, str | None]:
    if item.unit_weight is None or item.quantity is None:
        return False, None
    w = rules.item_weight(item.quantity, item.unit_weight, item.unit_weight_unit, item.categoria, unit_mass.get(item.categoria or ""))
    return w.estimated, w.note


def item_missing(item: m.DonationItem) -> list[str]:
    miss = []
    if not item.produto:
        miss.append("produto")
    if not item.categoria:
        miss.append("categoria")
    if item.quantity is None:
        miss.append("quantidade")
    if item.unit_weight is None:
        miss.append("peso_por_unidade")
    if item.expires_at is None:
        miss.append("validade")
    if item.exige_refrigeracao is None:
        miss.append("exige_refrigeracao")
    for p in item.pending_fields or []:
        if p not in miss:
            miss.append(p)
    return miss


def new_item(donation: m.Donation, values: dict[str, Any], now: dt.datetime, unit_mass, cat_perec, source: str = "MANUAL", pending: list[str] | None = None,
             suggestion: dict[str, Any] | None = None) -> m.DonationItem:
    it = m.DonationItem(donation_id=donation.id, data_origin=donation.data_origin, generator_version=donation.generator_version, seed=donation.seed, dataset_version=donation.dataset_version,
                        entry_source=source, pending_fields=pending or [], parser_suggestion=suggestion, created_at=now, updated_at=now,
                        product_name_origin="USER_ENTERED" if donation.data_origin == "USER_ENTERED" else None)
    for k in ITEM_FIELDS:
        if k in values:
            setattr(it, k, values[k])
    for k in ("expires_at", "validity_precision", "validity_source"):
        if k in values:
            setattr(it, k, values[k])
    recompute_item(it, now, unit_mass, cat_perec)
    return it


def refresh_donation(db: Session, donation: m.Donation, now: dt.datetime) -> Aggregate:
    """Recalcula os agregados do cabeçalho a partir dos itens atuais."""
    db.flush()
    items = list(db.scalars(select(m.DonationItem).where(m.DonationItem.donation_id == donation.id).order_by(m.DonationItem.id)))
    agg = aggregate([ItemAgg(i.id, i.categoria, i.produto, i.quantity_kg, i.expires_at, i.exige_refrigeracao, i.perecibilidade) for i in items], now)
    if agg.quantity_kg is not None and agg.quantity_kg > DONATION.max_total_kg:
        raise ValueError(f"peso total do lote acima do limite de {DONATION.max_total_kg:g} kg")
    apply_to_donation(donation, agg, now)
    return agg


def evaluate_items(items: list[m.DonationItem], now: dt.datetime) -> dict[str, Any]:
    """Status da doação a partir dos itens (R-VAL-1/2 por item; pendências)."""
    if not items:
        return {"status": "DRAFT", "block_reason": "adicione ao menos um item", "pending": ["itens"]}
    today = now.astimezone(TZ).date()
    for it in items:
        if it.expires_at is not None and it.expires_at.astimezone(TZ).date() < today:
            return {"status": "BLOCKED_EXPIRED", "block_reason": f"item '{it.produto}' com validade vencida (R-VAL-2): remova ou corrija o item", "pending": []}
    for it in items:
        if it.expires_at is None:
            return {"status": "BLOCKED_NO_VALIDITY", "block_reason": f"item '{it.produto}' sem validade (R-VAL-1): informe a validade", "pending": ["validade"]}
    pend = [f"{it.produto or 'item'}: {', '.join(item_missing(it))}" for it in items if item_missing(it)]
    if pend:
        return {"status": "PENDING_CONFIRMATION", "block_reason": ("campos pendentes de confirmação — " + "; ".join(pend))[:200], "pending": pend}
    return {"status": "READY", "block_reason": None, "pending": []}


def clear_pending(item: m.DonationItem, fields: list[str]) -> None:
    if item.pending_fields:
        item.pending_fields = [p for p in item.pending_fields if p not in fields]


REVIEW_FIELD = REVIEW
