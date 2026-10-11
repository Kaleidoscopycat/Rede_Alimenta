"""Ciclo operacional do match (máquina de estados registrada em match_events, com timestamp de cada transição).

PROPOSED → ACCEPTED | DECLINED | EXPIRED → (próxima candidata: SKIPPED/PROPOSED) → COLLECTED | FAILED;  sem candidata restante → EXHAUSTED.
Reserva de capacidade: dentro de transação, com SELECT ... FOR UPDATE no perfil da ONG, para que doações simultâneas não ocupem a mesma capacidade.
Sem filas externas: a expiração é varrida por tarefa em segundo plano do FastAPI (`expire_overdue`)."""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.settings import SETTINGS, TZ
from database import models as m
from .eligibility import DonationCtx
from .engine import MatchEngine

log = logging.getLogger("match.lifecycle")
RESERVING = ("ACTIVE", "CONSUMED")


class LifecycleError(Exception):
    status_code = 409

    def __init__(self, message: str, status_code: int | None = None, code: str = "STATE"):
        super().__init__(message)
        self.code = code
        if status_code:
            self.status_code = status_code


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _emit(session: Session, match: m.Match, etype: str, frm: str | None, to: str | None, now: dt.datetime, org_id: uuid.UUID | None = None, pos: int | None = None,
          actor: m.User | None = None, actor_type: str = "SYSTEM", detail: dict | None = None) -> m.MatchEvent:
    ev = m.MatchEvent(match_id=match.id, event_type=etype, from_status=frm, to_status=to, organization_id=org_id, rank_position=pos, at=now,
                      actor_user_id=actor.id if actor else None, actor_type=actor_type, detail=detail or {}, data_origin=match.data_origin)
    session.add(ev)
    return ev


def reserved_on(session: Session, day: dt.date) -> dict[str, float]:
    rows = session.execute(select(m.CapacityReservation.organization_id, func.sum(m.CapacityReservation.reserved_kg))
                           .where(m.CapacityReservation.reservation_date == day, m.CapacityReservation.status.in_(RESERVING)).group_by(m.CapacityReservation.organization_id))
    return {str(o): float(k) for o, k in rows}


def build_ctx(session: Session, donation: m.Donation, now: dt.datetime) -> DonationCtx:
    loc = session.scalars(select(m.DonorLocation).where(m.DonorLocation.donor_id == donation.donor_id).order_by(m.DonorLocation.id.desc())).first()
    donor = session.get(m.Donor, donation.donor_id)
    if loc is None or donor is None:
        raise LifecycleError("doador sem localização conhecida: não é possível calcular distâncias", 422, "DONOR_NO_LOCATION")
    if donation.expires_at is None or donation.quantity_kg is None or donation.categoria is None or donation.exige_refrigeracao is None:
        raise LifecycleError("doação incompleta (categoria, quantidade, validade e refrigeração são obrigatórias)", 409, "DONATION_INCOMPLETE")
    hours = (donation.expires_at - now).total_seconds() / 3600.0
    return DonationCtx(categoria=donation.categoria, quantity_kg=float(donation.quantity_kg), hours_to_expiry=hours, needs_cold=bool(donation.exige_refrigeracao),
                       pickup_days_mask=int(donation.pickup_days_mask), pickup_start_h=float(donation.pickup_start_h), pickup_end_h=float(donation.pickup_end_h),
                       load_minutes=float(donation.load_minutes), lat=loc.lat, lon=loc.lon, municipio_ibge=int(donor.municipio_ibge), location_precision=loc.location_precision,
                       allergen=bool(donation.contem_alergenico), data_origin=donation.data_origin)


# ---------------------------------------------------------------------------------------------------- criação
def create_match(session: Session, engine: MatchEngine, donation_id: uuid.UUID, actor: m.User | None, now: dt.datetime | None = None) -> m.Match:
    now = now or utcnow()
    donation = session.execute(select(m.Donation).where(m.Donation.id == donation_id).with_for_update()).scalar_one_or_none()
    if donation is None:
        raise LifecycleError("doação não encontrada", 404, "NOT_FOUND")
    if donation.status not in ("READY", "NO_MATCH"):
        raise LifecycleError(f"doação em estado {donation.status}: o match só é gerado após a confirmação do doador (READY)", 409, "DONATION_NOT_READY")
    active = session.scalar(select(m.Match.id).where(m.Match.donation_id == donation.id, m.Match.status.in_(("PROPOSED", "ACCEPTED"))))
    if active:
        raise LifecycleError("já existe match em andamento para esta doação", 409, "MATCH_ACTIVE")
    ctx = build_ctx(session, donation, now)
    if ctx.hours_to_expiry <= 0:  # regra explícita e testável: validade vencida bloqueia o match
        donation.status, donation.block_reason = "BLOCKED_EXPIRED", "validade vencida no momento do match"
        session.commit()
        raise LifecycleError("validade vencida: match bloqueado", 409, "EXPIRED")
    day = now.astimezone(TZ).date()
    result = engine.rank(ctx, now, reserved_on(session, day))
    match = m.Match(id=uuid.uuid4(), donation_id=donation.id, data_origin=donation.data_origin, status="PROPOSED", engine_version=result["engine_version"], model_version=result["model_version"],
                    weights=result["weights"], ranking=result["ranking"], eligibility={**result["eligibility"], "alertas": result.get("alertas", []), "rules_catalog": result["rules_catalog"],
                    "distance_method": result["distance_method"], "n_unranked_no_location": result["n_unranked_no_location"]},
                    current_position=0, latency_ms=result["latency_ms"], simulated_clock=False, created_by=actor.id if actor else None, created_at=now, updated_at=now,
                    generator_version=donation.generator_version, seed=donation.seed, dataset_version=donation.dataset_version)
    session.add(match)
    session.flush()
    session.add(m.MlPrediction(kind="RANKER", donation_id=donation.id, match_id=match.id, model_name="ranker+match-engine", model_version=f"{result['model_version']}|{result['engine_version']}",
                               output={"n_candidatas": len(result["ranking"]), "top": [{k: r[k] for k in ("ong_id", "ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE")} for r in result["ranking"][:5]]},
                               confidence=result["ranking"][0]["ML_SCORE"] if result["ranking"] else None, training_data_origin="SIMULATED", subject_data_origin=donation.data_origin,
                               latency_ms=result["latency_ms"]["total_ms"], created_by=actor.id if actor else None, created_at=now))
    _emit(session, match, "RANKED", None, "PROPOSED", now, actor=actor, actor_type=_actor_type(actor),
          detail={"n_candidatas": len(result["ranking"]), "n_elegiveis": result["eligibility"]["n_eligible"], "n_no_raio": result["eligibility"]["n_in_radius"], "latency_ms": result["latency_ms"]})
    donation.status = "MATCHING"
    propose_next(session, engine, match, donation, ctx, now)
    session.commit()
    return match


def _actor_type(u: m.User | None) -> str:
    return u.role if u else "SYSTEM"


# ---------------------------------------------------------------------------------------------------- proposta (com reserva de capacidade)
def propose_next(session: Session, engine: MatchEngine, match: m.Match, donation: m.Donation, ctx: DonationCtx, now: dt.datetime) -> bool:
    day = now.astimezone(TZ).date()
    for cand in match.ranking:
        pos = int(cand["posicao"])
        if pos <= (match.current_position or 0):
            continue
        org_id = uuid.UUID(cand["org_id"])
        prof = session.execute(select(m.OrganizationProfile).where(m.OrganizationProfile.organization_id == org_id).with_for_update()).scalar_one_or_none()
        match.current_position = pos
        if prof is None:
            _emit(session, match, "SKIPPED", match.status, match.status, now, org_id, pos, detail={"regras_reprovadas": ["E_CAPACIDADE"], "motivo": "ONG sem perfil declarado"})
            continue
        reserved = session.scalar(select(func.coalesce(func.sum(m.CapacityReservation.reserved_kg), 0.0)).where(
            m.CapacityReservation.organization_id == org_id, m.CapacityReservation.reservation_date == day, m.CapacityReservation.status.in_(RESERVING)))
        remaining = float(prof.capacity_max_kg_day) - float(reserved)
        ctx_now = DonationCtx(**{**ctx.__dict__, "hours_to_expiry": (donation.expires_at - now).total_seconds() / 3600.0})
        ok, reasons, times = engine.recheck(ctx_now, cand, now, remaining)
        if not ok:
            _emit(session, match, "SKIPPED", match.status, match.status, now, org_id, pos, detail={"regras_reprovadas": reasons, "capacidade_restante_kg": round(remaining, 1),
                                                                                                  "motivo": "reavaliação das regras eliminatórias no momento da proposta"})
            continue
        session.add(m.CapacityReservation(match_id=match.id, organization_id=org_id, reserved_kg=float(donation.quantity_kg), reservation_date=day, status="ACTIVE", created_at=now,
                                          data_origin=match.data_origin))
        prev = match.status
        match.current_org_id, match.status = org_id, "PROPOSED"
        match.proposal_expires_at = now + dt.timedelta(minutes=SETTINGS.proposal_ttl_minutes)
        match.updated_at = now
        _emit(session, match, "PROPOSED", prev, "PROPOSED", now, org_id, pos, detail={"prazo_resposta": match.proposal_expires_at.isoformat(), "capacidade_reservada_kg": float(donation.quantity_kg),
                                                                                       "capacidade_restante_antes_kg": round(remaining, 1), "FINAL_SCORE": cand["FINAL_SCORE"]})
        return True
    prev = match.status
    match.status, match.current_org_id, match.proposal_expires_at, match.closed_at, match.updated_at = "EXHAUSTED", None, None, now, now
    donation.status = "NO_MATCH"
    _emit(session, match, "EXHAUSTED", prev, "EXHAUSTED", now, detail={"motivo": "nenhuma candidata restante (recusa, expiração ou reprovação nas regras no momento da proposta)"})
    return False


def _release(session: Session, match: m.Match, org_id: uuid.UUID, now: dt.datetime, new_status: str = "RELEASED") -> None:
    for r in session.scalars(select(m.CapacityReservation).where(m.CapacityReservation.match_id == match.id, m.CapacityReservation.organization_id == org_id,
                                                                  m.CapacityReservation.status == "ACTIVE").with_for_update()):
        r.status, r.released_at = new_status, now


def _lock_match(session: Session, match_id: uuid.UUID) -> tuple[m.Match, m.Donation]:
    match = session.execute(select(m.Match).where(m.Match.id == match_id).with_for_update()).scalar_one_or_none()
    if match is None:
        raise LifecycleError("match não encontrado", 404, "NOT_FOUND")
    donation = session.execute(select(m.Donation).where(m.Donation.id == match.donation_id).with_for_update()).scalar_one()
    return match, donation


# ---------------------------------------------------------------------------------------------------- respostas da ONG
def _expire_locked(session: Session, engine: MatchEngine, match: m.Match, donation: m.Donation, now: dt.datetime) -> None:
    org = match.current_org_id
    _emit(session, match, "EXPIRED", "PROPOSED", "PROPOSED", now, org, match.current_position, detail={"prazo": match.proposal_expires_at.isoformat() if match.proposal_expires_at else None})
    _release(session, match, org, now)
    propose_next(session, engine, match, donation, build_ctx(session, donation, now), now)


def respond(session: Session, engine: MatchEngine, match_id: uuid.UUID, user: m.User, accept: bool, note: str | None = None, now: dt.datetime | None = None) -> m.Match:
    now = now or utcnow()
    match, donation = _lock_match(session, match_id)
    if match.status != "PROPOSED" or match.current_org_id is None:
        raise LifecycleError(f"match em estado {match.status}: não aguarda resposta", 409, "NOT_AWAITING_RESPONSE")
    if user.role == "ORG" and match.current_org_id != user.organization_id:
        raise LifecycleError("a proposta não está dirigida a esta organização", 403, "NOT_YOUR_PROPOSAL")
    if match.proposal_expires_at and now > match.proposal_expires_at:
        _expire_locked(session, engine, match, donation, now)
        session.commit()
        raise LifecycleError("prazo de resposta expirado: a proposta passou à próxima candidata", 409, "PROPOSAL_EXPIRED")
    org = match.current_org_id
    if accept:
        match.status, match.proposal_expires_at, match.updated_at = "ACCEPTED", None, now
        donation.status = "MATCHED"
        _emit(session, match, "ACCEPTED", "PROPOSED", "ACCEPTED", now, org, match.current_position, user, user.role, {"nota": note})
    else:
        _emit(session, match, "DECLINED", "PROPOSED", "PROPOSED", now, org, match.current_position, user, user.role, {"nota": note})
        _release(session, match, org, now)
        propose_next(session, engine, match, donation, build_ctx(session, donation, now), now)
    session.commit()
    return match


def expire_overdue(session: Session, engine: MatchEngine, now: dt.datetime | None = None, limit: int = 50) -> int:
    """Varredura da tarefa em segundo plano: propostas sem resposta no prazo → EXPIRED → próxima candidata."""
    now = now or utcnow()
    ids = [r for r in session.scalars(select(m.Match.id).where(m.Match.status == "PROPOSED", m.Match.proposal_expires_at <= now)
                                      .order_by(m.Match.proposal_expires_at).limit(limit).with_for_update(skip_locked=True))]
    n = 0
    for mid in ids:
        match, donation = _lock_match(session, mid)
        if match.status == "PROPOSED" and match.proposal_expires_at and match.proposal_expires_at <= now:
            _expire_locked(session, engine, match, donation, now)
            n += 1
        session.commit()
    return n


def record_outcome(session: Session, match_id: uuid.UUID, user: m.User, result: str, note: str | None = None, now: dt.datetime | None = None) -> m.Match:
    now = now or utcnow()
    if result not in ("COLLECTED", "FAILED"):
        raise LifecycleError("resultado inválido", 422, "BAD_RESULT")
    match, donation = _lock_match(session, match_id)
    if match.status != "ACCEPTED":
        raise LifecycleError(f"match em estado {match.status}: só se registra coleta após o aceite", 409, "NOT_ACCEPTED")
    if user.role == "ORG" and match.current_org_id != user.organization_id:
        raise LifecycleError("match não pertence a esta organização", 403, "NOT_YOUR_MATCH")
    org = match.current_org_id
    _emit(session, match, result, "ACCEPTED", result, now, org, match.current_position, user, user.role, {"nota": note})
    match.status, match.closed_at, match.updated_at = result, now, now
    if result == "COLLECTED":
        _release(session, match, org, now, "CONSUMED")  # capacidade do dia permanece ocupada
    else:
        _release(session, match, org, now)
        donation.status = "READY"  # o doador pode solicitar novo match (validade será reavaliada)
    session.commit()
    return match
