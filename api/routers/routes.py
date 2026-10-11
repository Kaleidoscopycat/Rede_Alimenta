"""Rotas de coleta (Fase 2 Parte 2): POST /api/v1/routes/plan · GET /api/v1/routes/{id}.
Perfis: ORG (somente doações aceitas pela própria ONG) e ADMIN. Resultado rotulado como SIMULAÇÃO quando as entradas são SIMULATED (distâncias/tempos são estimativas, não rota viária)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.auth import audit, forbid, get_db, require_roles
from database import models as m
from routing import service as svc

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])


class RoutePlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    donation_ids: list[uuid.UUID] = Field(min_length=1, max_length=12, description="Doações já ACEITAS pela ONG de destino (match ACCEPTED)")
    vehicle_id: Optional[uuid.UUID] = Field(default=None, description="Veículo cadastrado; padrão: veículo da própria ONG de destino")
    departure_at: Optional[dt.datetime] = Field(default=None, description="Partida da base (padrão: agora)")
    safety_margin_h: Optional[float] = Field(default=None, ge=0, le=48, description="Margem de segurança antes da validade (padrão: ROUTE_SAFETY_MARGIN_H)")


@router.post("/plan", status_code=201, summary="Planeja a rota de coleta (baseline vizinho mais próximo × solver OR-Tools) e persiste ambas")
def plan_route(body: RoutePlanIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ORG", "ADMIN"))):
    try:
        out = svc.plan_and_persist(db, user, body.donation_ids, body.vehicle_id, body.departure_at, body.safety_margin_h)
    except svc.RouteError as e:
        db.rollback()
        audit("route.plan", "DENIED", request, user, "route", None, e.status_code, detail={"codigo": e.code})
        if e.status_code == 403:
            raise forbid(request, user, "route", None) from e
        raise HTTPException(e.status_code, {"mensagem": str(e), "codigo": e.code}) from e
    audit("route.plan", "OK", request, user, "route", out["primary"]["id"], 201,
          detail={"n_stops": out["primary"]["n_stops"], "algoritmo": out["primary"]["algorithm"], "data_origin": out["primary"]["data_origin"]}, session=db)
    db.commit()
    return out


@router.get("/{route_id}", summary="Consulta uma rota persistida (paradas, horários planejados, parâmetros e comparação com o baseline)")
def get_route(route_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ORG", "ADMIN"))):
    r = db.get(m.Route, route_id)
    if r is None:
        raise HTTPException(404, "rota não encontrada")
    if user.role == "ORG" and r.organization_id != user.organization_id:
        raise forbid(request, user, "route", route_id)
    return svc.route_view(db, r)
