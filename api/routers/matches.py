"""Matches: ranking explicado, ciclo PROPOSED → ACCEPTED|DECLINED|EXPIRED → próxima candidata → COLLECTED|FAILED, eventos e métricas de tempo."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import audit, forbid, get_db, require_roles
from api.schemas_v2 import BatchIn, MatchIn, OutcomeIn, RespondIn
from api.state import STATE
from database import models as m
from match import lifecycle
from match.batch import run_batch_comparison
from match.engine import SCORE_LABELS
from match.metrics import match_time_metrics

router = APIRouter(prefix="/api/v1", tags=["matches"])
AVISO_MATCH = ("Ranking de apoio: ML_SCORE vem de modelo treinado em dados SIMULADOS; capacidade/horários/refrigeração das ONGs são DECLARADOS SIMULADOS; distâncias são em linha reta "
               "(haversine), aproximadas quando há centroide de município; pesos do FINAL_SCORE são premissas. Requer confirmação humana; a plataforma não atesta a segurança do alimento.")


def _http(e: lifecycle.LifecycleError) -> HTTPException:
    return HTTPException(e.status_code, {"mensagem": str(e), "codigo": e.code})


def _donation_brief(d: m.Donation, donor: m.Donor | None) -> dict[str, Any]:
    return {"donation_id": str(d.id), "data_origin": d.data_origin, "categoria": d.categoria, "perecibilidade": d.perecibilidade, "exige_refrigeracao": d.exige_refrigeracao,
            "quantity_kg": d.quantity_kg, "refeicoes_equivalentes": round(d.quantity_kg / 0.4, 1) if d.quantity_kg else None, "premissa_kg_por_refeicao": 0.4,
            "expires_at": d.expires_at, "validity_source": d.validity_source, "contem_alergenico": d.contem_alergenico,
            "janela_retirada": {"inicio_h": d.pickup_start_h, "fim_h": d.pickup_end_h, "dias_mask": d.pickup_days_mask, "tempo_carga_min": d.load_minutes},
            "doador": {"tipo": donor.donor_type if donor else None, "porte": donor.donor_size if donor else None, "municipio_ibge": donor.municipio_ibge if donor else None},
            "aviso": "A plataforma não afirma que o alimento é próprio para consumo; confirme as condições na coleta."}


def _org_label(db: Session, org_id: uuid.UUID | None) -> str | None:
    if not org_id:
        return None
    o = db.get(m.Organization, org_id)
    return o.ong_id if o else None


def match_view(db: Session, mt: m.Match, user: m.User, top_n: int | None = None) -> dict[str, Any]:
    d = db.get(m.Donation, mt.donation_id)
    donor = db.get(m.Donor, d.donor_id)
    base = {"id": str(mt.id), "donation_id": str(mt.donation_id), "data_origin": mt.data_origin, "status": mt.status, "engine_version": mt.engine_version, "model_version": mt.model_version,
            "current_org": _org_label(db, mt.current_org_id), "current_position": mt.current_position, "proposal_expires_at": mt.proposal_expires_at, "latency_ms": mt.latency_ms,
            "created_at": mt.created_at, "updated_at": mt.updated_at, "closed_at": mt.closed_at, "donation": _donation_brief(d, donor), "score_definitions": SCORE_LABELS, "aviso": AVISO_MATCH}
    if user.role == "ORG":  # ONG vê apenas a própria proposta (sem as demais candidatas)
        mine = next((r for r in mt.ranking if r["org_id"] == str(user.organization_id)), None)
        base["my_candidacy"] = mine
        base["awaiting_my_response"] = mt.status == "PROPOSED" and mt.current_org_id == user.organization_id
        return base
    ranking = mt.ranking if top_n is None else mt.ranking[:top_n]
    base.update(ranking=ranking, n_candidates=len(mt.ranking), eligibility=mt.eligibility, weights=mt.weights)
    return base


def _can_view(db: Session, mt: m.Match, user: m.User) -> bool:
    if user.role == "ADMIN":
        return True
    if user.role == "DONOR":
        d = db.get(m.Donation, mt.donation_id)
        return d.donor_id == user.donor_id
    if mt.current_org_id == user.organization_id:
        return True
    return db.scalar(select(m.MatchEvent.id).where(m.MatchEvent.match_id == mt.id, m.MatchEvent.organization_id == user.organization_id, m.MatchEvent.event_type == "PROPOSED").limit(1)) is not None


@router.post("/matches", status_code=201, summary="Gera o ranking explicado para uma doação confirmada e propõe à ONG mais bem ranqueada")
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
    return match_view(db, mt, user, body.top_n)


@router.get("/matches", summary="Lista matches do usuário (DONOR: suas doações; ORG: propostas dirigidas a ela; ADMIN: todos)")
def list_matches(status: str | None = None, limit: int = 20, offset: int = 0, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN"))):
    q = select(m.Match).order_by(m.Match.created_at.desc()).limit(min(max(limit, 1), 100)).offset(max(offset, 0))
    if user.role == "DONOR":
        q = q.join(m.Donation, m.Donation.id == m.Match.donation_id).where(m.Donation.donor_id == user.donor_id)
    elif user.role == "ORG":
        q = q.where(m.Match.current_org_id == user.organization_id)
    if status:
        q = q.where(m.Match.status == status)
    return [match_view(db, x, user, 3) for x in db.scalars(q)]


@router.get("/matches/{match_id}")
def get_match(match_id: uuid.UUID, request: Request, top_n: int | None = None, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN"))):
    mt = db.get(m.Match, match_id)
    if mt is None:
        raise HTTPException(404, "match não encontrado")
    if not _can_view(db, mt, user):
        raise forbid(request, user, "match", match_id)
    return match_view(db, mt, user, top_n)


@router.post("/matches/{match_id}/respond", summary="ONG aceita ou recusa a proposta (recusa/ausência aciona a próxima candidata)")
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
    return match_view(db, mt, user)


@router.post("/matches/{match_id}/outcome", summary="Registra o resultado da coleta (COLLECTED | FAILED) após o aceite")
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
    return match_view(db, mt, user)


@router.get("/matches/{match_id}/events", summary="Histórico de estados e tempos (match_events)")
def events(match_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN"))):
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
        out.append({"id": e.id, "event_type": e.event_type, "from_status": e.from_status, "to_status": e.to_status, "ong_id": orgs.get(e.organization_id), "rank_position": e.rank_position,
                    "at": e.at, "seconds_since_previous": round((e.at - prev).total_seconds(), 3) if prev else None, "actor_type": e.actor_type, "detail": e.detail, "data_origin": e.data_origin})
        prev = e.at
    return {"match_id": str(match_id), "data_origin": mt.data_origin, "events": out}


@router.post("/matches/batch-compare", status_code=201, summary="ADMIN: compara escolha gulosa × atribuição ótima em lote (SIMULAÇÃO) e registra a diferença")
def batch_compare(body: BatchIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN"))):
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
def match_times(db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN"))):
    return match_time_metrics(db)
