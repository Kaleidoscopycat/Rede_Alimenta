"""Matches: ranking explicado, ciclo PROPOSED → ACCEPTED|DECLINED|EXPIRED → próxima candidata → COLLECTED|FAILED, eventos e métricas de tempo."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import audit, forbid, get_db, require_roles
from api import views
from api.schemas_v2 import BatchIn, MatchIn, OutcomeIn, RespondIn
from api.schemas_views import AdminMatchView, MatchView
from api.state import STATE
from database import models as m
from match import lifecycle
from match.batch import run_batch_comparison
from match.metrics import match_time_metrics

router = APIRouter(prefix="/api/v1", tags=["matches"])


def _http(e: lifecycle.LifecycleError) -> HTTPException:
    return HTTPException(e.status_code, {"mensagem": str(e), "codigo": e.code})


def _org_label(db: Session, org_id: uuid.UUID | None) -> str | None:
    return views.org_label(db, org_id)


def _can_view(db: Session, mt: m.Match, user: m.User) -> bool:
    if user.role == "ADMIN":
        return True
    if user.role == "DONOR":
        d = db.get(m.Donation, mt.donation_id)
        return d.donor_id == user.donor_id
    if mt.current_org_id == user.organization_id:
        return True
    return db.scalar(select(m.MatchEvent.id).where(m.MatchEvent.match_id == mt.id, m.MatchEvent.organization_id == user.organization_id, m.MatchEvent.event_type == "PROPOSED").limit(1)) is not None


@router.post("/matches", status_code=201, response_model=MatchView, summary="Gera o ranking explicado para uma doação confirmada e propõe à ONG mais bem ranqueada")
def create_match(body: MatchIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    d = db.get(m.Donation, body.donation_id)
    if d is None:
        raise HTTPException(404, "doação não encontrada")
    if user.role == "DONOR" and d.donor_id != user.donor_id:
        raise forbid(request, user, "donation", body.donation_id)
    if STATE.engine is None:
        raise HTTPException(503, "motor de match indisponível")
    try:
        mt = lifecycle.create_match(db, STATE.engine, body.donation_id, user)
    except lifecycle.LifecycleError as e:
        db.rollback()
        audit("match.create", "DENIED", request, user, "donation", body.donation_id, e.status_code, detail={"codigo": e.code})
        raise _http(e) from e
    audit("match.create", "OK", request, user, "match", mt.id, 201, detail={"status": mt.status, "latency_ms": mt.latency_ms.get("total_ms")}, session=db)
    db.commit()
    return views.match_view(db, mt, user, body.top_n if user.role == "ADMIN" else None)


@router.get("/matches", response_model=list[MatchView], summary="Lista matches do usuário (DONOR: suas doações; ORG: propostas dirigidas a ela; ADMIN: todos)")
def list_matches(status: str | None = None, limit: int = 20, offset: int = 0, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN", audit_admin="matches"))):
    q = select(m.Match).order_by(m.Match.created_at.desc()).limit(min(max(limit, 1), 100)).offset(max(offset, 0))
    if user.role == "DONOR":
        q = q.join(m.Donation, m.Donation.id == m.Match.donation_id).where(m.Donation.donor_id == user.donor_id)
    elif user.role == "ORG":
        q = q.where(m.Match.current_org_id == user.organization_id)
    if status:
        q = q.where(m.Match.status == status)
    return [views.match_view(db, x, user, 3 if user.role == "ADMIN" else None) for x in db.scalars(q)]


@router.get("/matches/{match_id}", response_model=MatchView)
def get_match(match_id: uuid.UUID, request: Request, top_n: int | None = None, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN", audit_admin="match"))):
    mt = db.get(m.Match, match_id)
    if mt is None:
        raise HTTPException(404, "match não encontrado")
    if not _can_view(db, mt, user):
        raise forbid(request, user, "match", match_id)
    return views.match_view(db, mt, user, top_n if user.role == "ADMIN" else None)


@router.post("/matches/{match_id}/respond", response_model=MatchView, summary="ONG aceita ou recusa a proposta (recusa/ausência aciona a próxima candidata)")
def respond(match_id: uuid.UUID, body: RespondIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ORG", "ADMIN"))):
    mt = db.get(m.Match, match_id)
    if mt is None:
        raise HTTPException(404, "match não encontrado")
    if user.role == "ORG" and mt.current_org_id != user.organization_id:
        raise forbid(request, user, "match", match_id, "proposta dirigida a outra organização")
    try:
        mt = lifecycle.respond(db, STATE.engine, match_id, user, body.accept, body.note)
    except lifecycle.LifecycleError as e:
        db.rollback()
        audit("match.respond", "DENIED", request, user, "match", match_id, e.status_code, detail={"codigo": e.code})
        raise _http(e) from e
    audit("match.respond", "OK", request, user, "match", match_id, 200, detail={"accept": body.accept, "status": mt.status}, session=db)
    db.commit()
    return views.match_view(db, mt, user)


@router.post("/matches/{match_id}/outcome", response_model=MatchView, summary="Registra o resultado da coleta (COLLECTED | FAILED) após o aceite")
def outcome(match_id: uuid.UUID, body: OutcomeIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ORG", "ADMIN"))):
    mt = db.get(m.Match, match_id)
    if mt is None:
        raise HTTPException(404, "match não encontrado")
    if user.role == "ORG" and mt.current_org_id != user.organization_id:
        raise forbid(request, user, "match", match_id)
    try:
        mt = lifecycle.record_outcome(db, match_id, user, body.result, body.note)
    except lifecycle.LifecycleError as e:
        db.rollback()
        audit("match.outcome", "DENIED", request, user, "match", match_id, e.status_code, detail={"codigo": e.code})
        raise _http(e) from e
    audit("match.outcome", "OK", request, user, "match", match_id, 200, detail={"result": body.result}, session=db)
    db.commit()
    return views.match_view(db, mt, user)


@router.get("/matches/{match_id}/ranking", response_model=AdminMatchView, summary="ADMIN: ranking completo com scores, elegibilidade e pesos (acesso auditado)")
def ranking(match_id: uuid.UUID, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN", audit_admin="match.ranking"))):
    mt = db.get(m.Match, match_id)
    if mt is None:
        raise HTTPException(404, "match não encontrado")
    return views.match_admin(db, mt)


@router.get("/matches/{match_id}/events", summary="Histórico de estados e tempos (match_events)")
def events(match_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN", audit_admin="match.events"))):
    mt = db.get(m.Match, match_id)
    if mt is None:
        raise HTTPException(404, "match não encontrado")
    if not _can_view(db, mt, user):
        raise forbid(request, user, "match", match_id)
    q = select(m.MatchEvent).where(m.MatchEvent.match_id == match_id).order_by(m.MatchEvent.id)
    if user.role == "ORG":
        q = q.where(m.MatchEvent.organization_id == user.organization_id)
    evs = db.scalars(q).all()
    orgs = {e.organization_id: _org_label(db, e.organization_id) for e in evs if e.organization_id}
    out, prev = [], None
    for e in evs:
        row = {"id": e.id, "event_type": e.event_type, "from_status": e.from_status, "to_status": e.to_status, "at": e.at,
               "seconds_since_previous": round((e.at - prev).total_seconds(), 3) if prev else None, "actor_type": e.actor_type, "data_origin": e.data_origin}
        if user.role == "ADMIN":
            row.update(ong_id=orgs.get(e.organization_id), rank_position=e.rank_position, detail=e.detail)
        elif user.role == "ORG":  # a ONG vê só os próprios eventos e apenas notas/prazos (nunca scores ou posição)
            row["detail"] = {k: v for k, v in (e.detail or {}).items() if k in ("nota", "prazo_resposta", "prazo")}
        out.append(row)
        prev = e.at
    return {"match_id": str(match_id), "data_origin": mt.data_origin, "events": out}


@router.post("/matches/batch-compare", status_code=201, summary="ADMIN: compara escolha gulosa × atribuição ótima em lote (SIMULAÇÃO) e registra a diferença")
def batch_compare(body: BatchIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN", audit_admin="batch_compare"))):
    at = body.at or dt.datetime.now(dt.timezone.utc)
    try:
        run = run_batch_comparison(db, STATE.engine, body.donation_ids, at, user)
    except lifecycle.LifecycleError as e:
        db.rollback()
        raise _http(e) from e
    audit("match.batch_compare", "OK", request, user, "batch_run", run.id, 201, session=db)
    db.commit()
    return {"id": run.id, "data_origin": run.data_origin, "n_lots": run.n_lots, "n_assigned_greedy": run.n_assigned_greedy, "n_assigned_optimal": run.n_assigned_optimal,
            "total_score_greedy": run.total_score_greedy, "total_score_optimal": run.total_score_optimal, "difference": run.difference, "details": run.details}


@router.get("/metrics/match-times", summary="ADMIN: tempo médio de match a partir de match_events, separado por origem")
def match_times(db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN", audit_admin="metrics"))):
    return match_time_metrics(db)
