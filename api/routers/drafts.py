"""Rascunho de doação e itens (Fase 3 Parte 1, seção 2): a doação é o CABEÇALHO e os itens são a fonte da verdade; peso, validade e refrigeração do lote são AGREGADOS (api/aggregation.py).

Fluxo: POST /donations/drafts → POST/PATCH/DELETE /donations/{id}/items (ou texto livre → itens SUGERIDOS a confirmar) → POST /donations/{id}/finalize → READY → POST /matches.
Nada é gravado como doação a partir de texto sem passar pelo rascunho; sugestões do texto ficam com `pending_fields` até o doador confirmar."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import items as svc
from api.auth import audit, forbid, get_db, require_roles
from api.item_parser import REVIEW, parse_items
from api.parsing import AVISO_PARSER
from api.routers import donations as dn
from api.schemas_items import DraftIn, DraftPatch, ItemIn, ItemPatch, TextIn
from api.schemas_views import DonationView, ItemAdminView, ItemDonorView
from api.state import STATE
from core.settings import DONATION, TZ
from database import models as m

router = APIRouter(prefix="/api/v1/donations", tags=["rascunho e itens"])
FIELD_OF = {"quantity": "quantidade", "unit_weight": "peso_por_unidade", "unit_weight_unit": "peso_por_unidade", "categoria": "categoria", "exige_refrigeracao": "exige_refrigeracao"}


class ParseItemsOut(BaseModel):
    items: list[dict[str, Any]]
    alerts: list[str]
    parser_version: str
    confidence_threshold: float
    threshold_note: str
    training_data_origin: str
    aviso: str


def _units():
    return STATE.unit_mass, STATE.cat_perecibilidade


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))


def _parse(text: str, today) -> dict[str, Any]:
    if STATE.parser is None:
        raise HTTPException(503, "parser indisponível")
    return parse_items(STATE.parser, text, today, STATE.unit_mass, STATE.cat_perecibilidade, DONATION.max_items)


def _load_editable(db: Session, request: Request, user: m.User, donation_id: uuid.UUID) -> m.Donation:
    d = dn._load_owned(db, request, user, donation_id, lock=True)
    if not svc.is_item_managed(d):
        raise HTTPException(409, "esta doação não usa itens detalhados (fluxo de texto único ou histórica)")
    if d.status not in svc.EDITABLE:
        raise HTTPException(409, f"doação em estado {d.status}: itens não podem mais ser alterados")
    return d


def _touch(db: Session, d: m.Donation, now) -> None:
    """Após qualquer mudança nos itens: reagrega e volta a DRAFT (precisa ser finalizada de novo)."""
    try:
        svc.refresh_donation(db, d, now)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from None
    d.status, d.block_reason, d.confirmed_at, d.confirmed_by = "DRAFT", None, None, None


def _view(db: Session, d: m.Donation, user: m.User):
    db.refresh(d)
    return dn.view(db, d, user)


def _add_suggested(db: Session, d: m.Donation, texto: str, user: m.User, now, today) -> dict[str, Any]:
    res = _parse(texto, today)
    n = db.scalar(select(func.count()).select_from(m.DonationItem).where(m.DonationItem.donation_id == d.id)) or 0
    if n + len(res["items"]) > DONATION.max_items:
        raise HTTPException(422, f"limite de {DONATION.max_items} itens por doação")
    um, cp = _units()
    for s in res["items"]:
        vals = {k: s[k] for k in ("produto", "categoria", "quantity", "unit", "unit_weight", "unit_weight_unit", "exige_refrigeracao", "expires_at", "validity_precision", "validity_source")}
        try:
            it = svc.new_item(d, vals, now, um, cp, "TEXTO_SUGERIDO", list(s["pending_fields"]), _jsonable(s))
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        db.add(it)
    db.add(m.MlPrediction(kind="PARSER", donation_id=d.id, model_name="semantic-parser", model_version=STATE.parser.version, output=_jsonable(res), confidence=None,
                          training_data_origin="SIMULATED", subject_data_origin=d.data_origin, created_by=user.id))
    return res


@router.post("/items/parse-preview", response_model=ParseItemsOut, summary="Pré-visualiza a divisão do texto em itens (não grava nada)")
def parse_preview(body: TextIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    donor = dn.resolve_donor(db, request, user, body.donor_id)
    res = _parse(body.texto, dn._now().astimezone(TZ).date())
    db.add(m.MlPrediction(kind="PARSER", donation_id=None, model_name="semantic-parser", model_version=STATE.parser.version, output=_jsonable(res), confidence=None,
                          training_data_origin="SIMULATED", subject_data_origin=donor.data_origin, created_by=user.id))
    audit("donation.parse_items", "OK", request, user, "donor", donor.id, 200, detail={"n_items": len(res["items"])}, session=db)
    db.commit()
    return ParseItemsOut(**{k: res[k] for k in ("items", "alerts", "parser_version", "confidence_threshold", "threshold_note", "training_data_origin")}, aviso=AVISO_PARSER)


@router.post("/drafts", response_model=DonationView, status_code=201, summary="Cria o rascunho de doação (cabeçalho); itens vêm depois ou do texto livre")
def create_draft(body: DraftIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    donor = dn.resolve_donor(db, request, user, body.donor_id)
    now = dn._now()
    today = now.astimezone(TZ).date()
    pick_days = sum(1 << x for x in set(body.dias_retirada)) if body.dias_retirada else donor.pickup_days_mask
    d = m.Donation(donor_id=donor.id, data_origin=donor.data_origin, status="DRAFT", entry_channel="API", raw_text=body.texto, contem_alergenico=body.contem_alergenico,
                   pickup_days_mask=pick_days, pickup_start_h=body.janela_retirada_inicio_h if body.janela_retirada_inicio_h is not None else donor.pickup_start_h,
                   pickup_end_h=body.janela_retirada_fim_h if body.janela_retirada_fim_h is not None else donor.pickup_end_h,
                   load_minutes=body.tempo_carga_min if body.tempo_carga_min is not None else donor.load_minutes, fields={}, created_by=user.id, created_at=now, aggregated_at=now,
                   updated_at=now, generator_version=donor.generator_version, seed=donor.seed, dataset_version=donor.dataset_version)
    if d.pickup_end_h <= d.pickup_start_h:
        raise HTTPException(422, "janela de retirada inválida")
    db.add(d)
    db.flush()
    if body.texto:
        _add_suggested(db, d, body.texto, user, now, today)
        d.parser_version = STATE.parser.version
    _touch(db, d, now)
    audit("donation.draft_create", "OK", request, user, "donation", d.id, 201, detail={"com_texto": bool(body.texto)}, session=db)
    db.commit()
    return _view(db, d, user)


@router.patch("/{donation_id}/draft", response_model=DonationView, summary="Altera janela de retirada/alergênicos do rascunho")
def patch_draft(donation_id: uuid.UUID, body: DraftPatch, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_editable(db, request, user, donation_id)
    now = dn._now()
    if body.contem_alergenico is not None:
        d.contem_alergenico = body.contem_alergenico
    if body.janela_retirada_inicio_h is not None:
        d.pickup_start_h = body.janela_retirada_inicio_h
    if body.janela_retirada_fim_h is not None:
        d.pickup_end_h = body.janela_retirada_fim_h
    if body.tempo_carga_min is not None:
        d.load_minutes = body.tempo_carga_min
    if body.dias_retirada is not None:
        d.pickup_days_mask = sum(1 << x for x in set(body.dias_retirada))
    if d.pickup_end_h <= d.pickup_start_h:
        db.rollback()
        raise HTTPException(422, "janela de retirada inválida")
    _touch(db, d, now)
    audit("donation.draft_patch", "OK", request, user, "donation", d.id, 200, session=db)
    db.commit()
    return _view(db, d, user)


@router.post("/{donation_id}/items/from-text", response_model=DonationView, status_code=201, summary="Adiciona itens SUGERIDOS a partir de texto livre (precisam ser confirmados)")
def items_from_text(donation_id: uuid.UUID, body: TextIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_editable(db, request, user, donation_id)
    now = dn._now()
    res = _add_suggested(db, d, body.texto, user, now, now.astimezone(TZ).date())
    d.raw_text = ((d.raw_text + "\n") if d.raw_text else "") + body.texto
    d.parser_version = STATE.parser.version
    _touch(db, d, now)
    audit("donation.items_from_text", "OK", request, user, "donation", d.id, 201, detail={"n_items": len(res["items"])}, session=db)
    db.commit()
    return _view(db, d, user)


def _values(body: ItemIn) -> dict[str, Any]:
    v = body.model_dump(exclude={"validade_data", "validade_mes_ano"})
    try:
        exp, prec, src = svc.validity_from_input(body.validade_data, body.validade_mes_ano)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    v.update(expires_at=exp, validity_precision=prec, validity_source=src)
    return v


@router.post("/{donation_id}/items", response_model=DonationView, status_code=201, summary="Adiciona um item (entrada manual do doador)")
def add_item(donation_id: uuid.UUID, body: ItemIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_editable(db, request, user, donation_id)
    now = dn._now()
    n = db.scalar(select(func.count()).select_from(m.DonationItem).where(m.DonationItem.donation_id == d.id)) or 0
    if n >= DONATION.max_items:
        raise HTTPException(422, f"limite de {DONATION.max_items} itens por doação")
    um, cp = _units()
    try:
        it = svc.new_item(d, _values(body), now, um, cp, "MANUAL")
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    db.add(it)
    _touch(db, d, now)
    audit("donation.item_add", "OK", request, user, "donation", d.id, 201, session=db)
    db.commit()
    return _view(db, d, user)


def _get_item(db: Session, d: m.Donation, item_id: int) -> m.DonationItem:
    it = db.get(m.DonationItem, item_id)
    if it is None or it.donation_id != d.id:
        raise HTTPException(404, "item não encontrado nesta doação")
    return it


@router.patch("/{donation_id}/items/{item_id}", response_model=DonationView, summary="Corrige/confirma campos de um item")
def patch_item(donation_id: uuid.UUID, item_id: int, body: ItemPatch, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_editable(db, request, user, donation_id)
    it = _get_item(db, d, item_id)
    now = dn._now()
    data = body.model_dump(exclude_none=True)
    accept, confirm = data.pop("accept_fields", []), data.pop("confirm_item", False)
    vd, vm = data.pop("validade_data", None), data.pop("validade_mes_ano", None)
    touched: set[str] = set()
    for k, v in data.items():
        setattr(it, k, v)
        if k in FIELD_OF:
            touched.add(FIELD_OF[k])
    if vd is not None or vm is not None:
        try:
            it.expires_at, it.validity_precision, it.validity_source = svc.validity_from_input(vd, vm)
        except ValueError as e:
            db.rollback()
            raise HTTPException(422, str(e)) from None
        touched.add("validade")
    if (it.unit_weight is None) != (it.unit_weight_unit is None):
        db.rollback()
        raise HTTPException(422, "informe `unit_weight` e `unit_weight_unit` juntos")
    have = {"categoria": it.categoria, "quantidade": it.quantity, "peso_por_unidade": it.unit_weight, "validade": it.expires_at, "exige_refrigeracao": it.exige_refrigeracao}
    for a in accept:
        if have.get(a) is None:
            db.rollback()
            raise HTTPException(422, f"não é possível aceitar '{a}': sem valor sugerido (informe o valor)")
        touched.add(a)
    um, cp = _units()
    try:
        svc.recompute_item(it, now, um, cp)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from None
    svc.clear_pending(it, sorted(touched))
    if confirm:
        others = [x for x in svc.item_missing(it) if x != REVIEW]
        if others:
            db.rollback()
            raise HTTPException(422, "item ainda tem campos pendentes: " + ", ".join(others))
        svc.clear_pending(it, [REVIEW])
    _touch(db, d, now)
    audit("donation.item_patch", "OK", request, user, "donation", d.id, 200, detail={"item_id": item_id, "campos": sorted(touched), "confirm": bool(confirm)}, session=db)
    db.commit()
    return _view(db, d, user)


@router.delete("/{donation_id}/items/{item_id}", response_model=DonationView, summary="Remove um item do rascunho")
def delete_item(donation_id: uuid.UUID, item_id: int, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_editable(db, request, user, donation_id)
    it = _get_item(db, d, item_id)
    db.delete(it)
    _touch(db, d, dn._now())
    audit("donation.item_delete", "OK", request, user, "donation", d.id, 200, detail={"item_id": item_id}, session=db)
    db.commit()
    return _view(db, d, user)


@router.get("/{donation_id}/items", response_model=list[ItemAdminView | ItemDonorView], summary="Lista os itens da doação (DONOR: seus itens; ADMIN: detalhe técnico)")
def list_items(donation_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    from api import views
    d = dn._load_owned(db, request, user, donation_id)
    its = views._items(db, d)
    return [views.item_admin(i) if user.role == "ADMIN" else views.item_donor(i) for i in its]


@router.post("/{donation_id}/finalize", response_model=DonationView, summary="Finaliza o rascunho: valida os itens e, se tudo confirmado, deixa a doação READY")
def finalize(donation_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_editable(db, request, user, donation_id)
    now = dn._now()
    from api import views
    its = views._items(db, d)
    if not its:
        raise HTTPException(422, "adicione ao menos um item antes de finalizar")
    try:
        svc.refresh_donation(db, d, now)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    ev = svc.evaluate_items(its, now)
    d.status, d.block_reason = ev["status"], ev["block_reason"]
    if ev["status"] == "READY":
        d.confirmed_at, d.confirmed_by = now, user.id
    audit("donation.finalize", "OK", request, user, "donation", d.id, 200, detail={"status": ev["status"], "n_items": len(its), "misto": bool(d.is_mixed_batch)}, session=db)
    db.commit()
    return _view(db, d, user)


__all__ = ["router", "forbid"]
