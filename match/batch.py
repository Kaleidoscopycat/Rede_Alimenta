"""Lotes pendentes na mesma janela: escolha GULOSA (um lote por vez, ordem de chegada) × atribuição ÓTIMA em lote (scipy.optimize.linear_sum_assignment).

Simplificações DOCUMENTADAS: (i) cada ONG recebe no máximo UM lote por rodada de lotes; (ii) só as K candidatas elegíveis de cada lote (ranking do motor) participam;
(iii) o objetivo é a soma de FINAL_SCORE (que combina ML SIMULADO + regras + distância). A diferença é registrada em batch_assignment_runs.
Resultado obtido com premissas simuladas ⇒ rotulado como simulação; NÃO é ganho real."""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import TZ
from database import models as m
from .engine import MatchEngine
from .lifecycle import LifecycleError, build_ctx, reserved_on

log = logging.getLogger("match.batch")


def greedy_assign(lots: list[dict[str, Any]]) -> dict[str, tuple[str, float]]:
    """lots: [{id, ranking:[{org_id, FINAL_SCORE}]}] em ordem de chegada. Cada lote pega a melhor ONG ainda livre."""
    taken: set[str] = set()
    out: dict[str, tuple[str, float]] = {}
    for lot in lots:
        for c in sorted(lot["ranking"], key=lambda r: -r["FINAL_SCORE"]):
            if c["org_id"] not in taken:
                taken.add(c["org_id"])
                out[lot["id"]] = (c["org_id"], float(c["FINAL_SCORE"]))
                break
    return out


def optimal_assign(lots: list[dict[str, Any]]) -> dict[str, tuple[str, float]]:
    orgs = sorted({c["org_id"] for lot in lots for c in lot["ranking"]})
    if not lots or not orgs:
        return {}
    col = {o: j for j, o in enumerate(orgs)}
    NEG = -1e6
    S = np.full((len(lots), len(orgs)), NEG)
    for i, lot in enumerate(lots):
        for c in lot["ranking"]:
            S[i, col[c["org_id"]]] = float(c["FINAL_SCORE"])
    r, c = linear_sum_assignment(-S)
    return {lots[i]["id"]: (orgs[j], float(S[i, j])) for i, j in zip(r, c) if S[i, j] > NEG / 2}


def compare(lots: list[dict[str, Any]]) -> dict[str, Any]:
    g, o = greedy_assign(lots), optimal_assign(lots)
    tg, to = sum(v[1] for v in g.values()), sum(v[1] for v in o.values())
    return {"n_lots": len(lots), "n_assigned_greedy": len(g), "n_assigned_optimal": len(o), "total_score_greedy": round(tg, 6), "total_score_optimal": round(to, 6),
            "difference": round(to - tg, 6), "n_lots_different_choice": sum(1 for k in o if k in g and g[k][0] != o[k][0]) + len(set(o) ^ set(g)),
            "greedy": {k: {"org_id": v[0], "FINAL_SCORE": round(v[1], 6)} for k, v in g.items()}, "optimal": {k: {"org_id": v[0], "FINAL_SCORE": round(v[1], 6)} for k, v in o.items()}}


def run_batch_comparison(session: Session, engine: MatchEngine, donation_ids: list[uuid.UUID], at: dt.datetime, actor: m.User | None) -> m.BatchAssignmentRun:
    """`at` é o relógio da rodada (para lotes SIMULADOS históricos usa-se o relógio simulado; ver docs). Lotes já vencidos em `at` são ignorados e contados."""
    donations = list(session.scalars(select(m.Donation).where(m.Donation.id.in_(donation_ids)).order_by(m.Donation.created_at)))
    if len(donations) != len(set(donation_ids)):
        raise LifecycleError("alguma doação informada não existe", 404, "NOT_FOUND")
    origins = {d.data_origin for d in donations}
    if len(origins) != 1:
        raise LifecycleError("não misture origens de dados (SIMULATED/USER_ENTERED) na mesma rodada", 422, "MIXED_ORIGIN")
    reserved = reserved_on(session, at.astimezone(TZ).date())
    lots, skipped = [], 0
    for d in donations:
        try:
            ctx = build_ctx(session, d, at)
        except LifecycleError:
            skipped += 1
            continue
        if ctx.hours_to_expiry <= 0:
            skipped += 1
            continue
        res = engine.rank(ctx, at, reserved)
        lots.append({"id": str(d.id), "ranking": res["ranking"]})
    cmp = compare(lots)
    run = m.BatchAssignmentRun(created_by=actor.id if actor else None, data_origin=origins.pop(), n_lots=cmp["n_lots"], n_assigned_greedy=cmp["n_assigned_greedy"],
                               n_assigned_optimal=cmp["n_assigned_optimal"], total_score_greedy=cmp["total_score_greedy"], total_score_optimal=cmp["total_score_optimal"],
                               difference=cmp["difference"], details={**{k: cmp[k] for k in ("n_lots_different_choice", "greedy", "optimal")}, "lots_ignorados_vencidos_ou_sem_contexto": skipped,
                                                                       "relogio": at.isoformat(), "simplificacoes": "1 lote por ONG por rodada; só candidatas elegíveis (top-K); objetivo = soma de FINAL_SCORE",
                                                                       "rotulo": "resultado de SIMULAÇÃO; não é ganho real"})
    session.add(run)
    session.commit()
    return run
