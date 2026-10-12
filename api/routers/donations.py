"""Doações: análise semântica do texto livre (parse), cadastro (com pendências), confirmação/correção pelo doador."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import donation_rules as rules
from api import views
from api.items import is_item_managed
from api.auth import audit, forbid, get_db, require_roles
from api.parsing import build_parse_response
from api.schemas_v2 import ConfirmIn, DonationIn, ParseIn, ParseOut
from api.schemas_views import DonationView
from api.state import STATE
from core.settings import TZ
from database import models as m

router = APIRouter(prefix="/api/v1/donations", tags=["doações"])


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def resolve_donor(db: Session, request: Request, user: m.User, donor_id: uuid.UUID | None) -> m.Donor:
    if user.role == "DONOR":
        if donor_id and donor_id != user.donor_id:
            raise forbid(request, user, "donor", donor_id)
        did = user.donor_id
    else:
        if donor_id is None:
            raise HTTPException(422, "ADMIN deve informar donor_id")
        did = donor_id
    d = db.get(m.Donor, did)
    if d is None:
        raise HTTPException(404, "doador não encontrado")
    return d


def view(db: Session, d: m.Donation, user: m.User):
    """Visão da doação conforme o perfil (DONOR → DonorDonationView; ADMIN → AdminDonationView)."""
    return views.donation_view(db, d, user, _now())


def _apply(d: m.Donation, ev: dict[str, Any]) -> None:
    d.status, d.block_reason, d.expires_at, d.validity_days = ev["status"], ev["block_reason"], ev["expires_at"], ev["validity_days"]
    d.validity_source = ev["validity_source"]
    d.categoria, d.perecibilidade, d.exige_refrigeracao, d.quantity_kg = ev["categoria"], ev["perecibilidade"], ev["exige_refrigeracao"], ev["quantity_kg"]


@router.post("/parse", response_model=ParseOut, summary="Análise semântica do texto livre do lote (não cria doação)")
def parse(body: ParseIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    if user.role == "DONOR":  # AJUSTE B0: a saída crua do parser (valor, confiança, limiar) é informação da IA; este fluxo (lote único) é DESCONTINUADO para DONOR
        raise HTTPException(410, "Esta análise foi descontinuada para o doador. Monte a doação item a item (POST /api/v1/donations/drafts) "
                                 "ou use POST /api/v1/donations/items/parse-preview para sugestões a conferir.")
    donor = resolve_donor(db, request, user, body.donor_id)
    if STATE.parser is None:
        raise HTTPException(503, "parser indisponível")
    today = _now().astimezone(TZ).date()
    resp, raw = build_parse_response(STATE.parser, body.texto, today, STATE.unit_mass)
    db.add(m.MlPrediction(kind="PARSER", donation_id=None, model_name="semantic-parser", model_version=STATE.parser.version, output={"resposta": resp, "bruto": _jsonable(raw)},
                          confidence=raw["parse_confidence"], training_data_origin="SIMULATED", subject_data_origin=donor.data_origin, created_by=user.id))
    audit("donation.parse", "OK", request, user, "donor", donor.id, 200, session=db)
    db.commit()
    return resp


def _jsonable(x: Any) -> Any:
    import numpy as np
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return x


@router.post("", response_model=DonationView, status_code=201, summary="Cadastra doação (texto livre e/ou campos estruturados)")
def create_donation(body: DonationIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    donor = resolve_donor(db, request, user, body.donor_id)
    now = _now()
    today = now.astimezone(TZ).date()
    resp = raw = None
    if body.texto:
        if STATE.parser is None:
            raise HTTPException(503, "parser indisponível")
        resp, raw = build_parse_response(STATE.parser, body.texto, today, STATE.unit_mass)  # nunca confia em parse feito pelo cliente
    fields = rules.fields_from_parse(resp, raw)
    overrides = {"categoria": body.categoria, "exige_refrigeracao": body.exige_refrigeracao, "dias_ate_validade": body.dias_ate_validade, "validade_data": body.validade_data,
                 "quantidade_kg": body.quantidade_kg}
    rules.apply_donor_decisions(fields, overrides, [], user.id, now, today, STATE.cat_perecibilidade)
    if body.categoria and not body.texto and fields["exige_refrigeracao"]["final"] is None:
        pass  # sem texto, refrigeração fica MISSING até o doador informar (não é inventada)
    ev = rules.evaluate(fields, now)
    pick_days = sum(1 << x for x in set(body.dias_retirada)) if body.dias_retirada else donor.pickup_days_mask
    don = m.Donation(donor_id=donor.id, data_origin=donor.data_origin, status=ev["status"], entry_channel="API", raw_text=body.texto, contem_alergenico=body.contem_alergenico,
                     pickup_days_mask=pick_days, pickup_start_h=body.janela_retirada_inicio_h if body.janela_retirada_inicio_h is not None else donor.pickup_start_h,
                     pickup_end_h=body.janela_retirada_fim_h if body.janela_retirada_fim_h is not None else donor.pickup_end_h,
                     load_minutes=body.tempo_carga_min if body.tempo_carga_min is not None else donor.load_minutes, fields=fields, parser_version=STATE.parser.version if resp else None,
                     created_by=user.id, created_at=now, generator_version=donor.generator_version, seed=donor.seed, dataset_version=donor.dataset_version)
    if don.pickup_end_h <= don.pickup_start_h:
        raise HTTPException(422, "janela de retirada inválida")
    _apply(don, ev)
    db.add(don)
    db.flush()
    if ev["categoria"]:
        db.add(m.DonationItem(donation_id=don.id, categoria=ev["categoria"], quantity=(raw or {}).get("quantidade"), unit=(raw or {}).get("unidade"), quantity_kg=ev["quantity_kg"],
                              data_origin=donor.data_origin, generator_version=donor.generator_version, seed=donor.seed, dataset_version=donor.dataset_version))
    if resp:
        db.add(m.MlPrediction(kind="PARSER", donation_id=don.id, model_name="semantic-parser", model_version=STATE.parser.version, output={"resposta": resp, "bruto": _jsonable(raw)},
                              confidence=raw["parse_confidence"], training_data_origin="SIMULATED", subject_data_origin=donor.data_origin, created_by=user.id))
    audit("donation.create", "OK", request, user, "donation", don.id, 201, detail={"status": ev["status"], "pendentes": ev["pending"]}, session=db)
    db.commit()
    return view(db, don, user)


def _load_owned(db: Session, request: Request, user: m.User, donation_id: uuid.UUID, lock: bool = False) -> m.Donation:
    q = select(m.Donation).where(m.Donation.id == donation_id)
    d = db.execute(q.with_for_update() if lock else q).scalar_one_or_none()
    if d is None:
        raise HTTPException(404, "doação não encontrada")
    if user.role == "DONOR" and d.donor_id != user.donor_id:
        raise forbid(request, user, "donation", donation_id)
    return d


@router.get("", response_model=list[DonationView], summary="Lista doações do doador autenticado (ADMIN: todas, paginado)")
def list_donations(request: Request, limit: int = 20, offset: int = 0, status: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN", audit_admin="donations"))):
    q = select(m.Donation).where(m.Donation.entry_channel == "API").order_by(m.Donation.created_at.desc()).limit(min(max(limit, 1), 100)).offset(max(offset, 0))
    if user.role == "DONOR":
        q = q.where(m.Donation.donor_id == user.donor_id)
    if status:
        q = q.where(m.Donation.status == status)
    return [view(db, d, user) for d in db.scalars(q)]


@router.get("/{donation_id}", response_model=DonationView)
def get_donation(donation_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN", audit_admin="donations"))):
    return view(db, _load_owned(db, request, user, donation_id), user)


@router.patch("/{donation_id}/confirm", response_model=DonationView, summary="Doador confirma/corrige campos; só então o match pode ser gerado")
def confirm(donation_id: uuid.UUID, body: ConfirmIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = _load_owned(db, request, user, donation_id, lock=True)
    if is_item_managed(d):
        raise HTTPException(409, "esta doação usa itens detalhados: use PATCH /donations/{id}/items/{item_id} e POST /donations/{id}/finalize")
    if d.status in ("MATCHING", "MATCHED", "HISTORICAL") or d.entry_channel != "API":
        raise HTTPException(409, f"doação em estado {d.status}: campos não podem mais ser alterados")
    now = _now()
    today = now.astimezone(TZ).date()
    fields = {k: dict(v) if isinstance(v, dict) else v for k, v in (d.fields or {}).items()}
    over = body.model_dump(exclude={"accept_fields"}, exclude_none=True)
    contem = over.pop("contem_alergenico", None)
    try:
        changed = rules.apply_donor_decisions(fields, over, list(body.accept_fields), user.id, now, today, STATE.cat_perecibilidade)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    if contem is not None:
        d.contem_alergenico = contem
        changed.append("contem_alergenico")
    ev = rules.evaluate(fields, now)
    d.fields = fields
    _apply(d, ev)
    if ev["status"] == "READY":
        d.confirmed_at, d.confirmed_by = now, user.id
    if ev["categoria"]:
        item = db.scalar(select(m.DonationItem).where(m.DonationItem.donation_id == d.id))
        if item is not None:
            item.categoria, item.quantity_kg = ev["categoria"], ev["quantity_kg"]
        else:
            db.add(m.DonationItem(donation_id=d.id, categoria=ev["categoria"], quantity_kg=ev["quantity_kg"], data_origin=d.data_origin, generator_version=d.generator_version,
                                  seed=d.seed, dataset_version=d.dataset_version))
    audit("donation.confirm", "OK", request, user, "donation", d.id, 200, detail={"campos_alterados": sorted(set(changed)), "status": ev["status"]}, session=db)
    db.commit()
    return view(db, d, user)
