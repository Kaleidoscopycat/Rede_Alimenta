from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from api.auth import audit, current_user, forbid, get_db, require_roles
from typing import Annotated, Union

from pydantic import Field

from api.schemas_v2 import LocationOut, OrganizationOut, OrganizationPublicView, ProfileIn, ProfileOut
from api.state import STATE
from database import models as m

router = APIRouter(prefix="/api/v1/organizations", tags=["organizações"])
AVISO_ORG = ("Registro proveniente de fonte pública (licença em revisão: NEEDS_REVIEW). NÃO é cliente da Rede Alimenta até cadastro/aceite (platform_status=REGISTERED). "
             "Capacidade, horários, categorias e refrigeração são DECLARADOS SIMULADOS enquanto não houver cadastro real (profile.data_origin).")


OrgView = Annotated[Union[OrganizationOut, OrganizationPublicView], Field(discriminator="perfil")]


def visible(o: m.Organization, user: m.User) -> OrganizationOut | OrganizationPublicView:
    """ADMIN e a própria ORG veem o registro completo; os demais, só a identificação pública mínima (sem perfil, coordenadas ou capacidade)."""
    if user.role == "ADMIN" or (user.role == "ORG" and user.organization_id == o.id):
        return to_out(o)
    return OrganizationPublicView(ong_id=o.ong_id, ong_tipo=o.ong_tipo, uf=o.uf, municipio_ibge=o.municipio_ibge, platform_status=o.platform_status, aviso=AVISO_ORG)


def to_out(o: m.Organization) -> OrganizationOut:
    loc = o.location
    approx = "Localização por centroide de município (aproximada); distâncias derivadas são aproximadas." if loc.location_precision == "MUNICIPALITY_CENTROID" else (
        "Organização sem posição conhecida: não ranqueável por distância." if loc.location_precision == "NONE" else None)
    prof = None
    if o.profile is not None:
        p = o.profile
        prof = ProfileOut(data_origin=p.data_origin, capacity_max_kg_day=p.capacity_max_kg_day, cold_chamber=p.cold_chamber, open_hour=p.open_hour, close_hour=p.close_hour,
                          open_days_mask=p.open_days_mask, accepted_categories=list(p.accepted_categories), has_fleet=p.has_fleet, fleet_refrigerated=p.fleet_refrigerated,
                          aviso="declarado SIMULADO (sem cadastro real)" if p.data_origin == "SIMULATED" else None)
    return OrganizationOut(id=o.id, ong_id=o.ong_id, ong_tipo=o.ong_tipo, uf=o.uf, municipio_ibge=o.municipio_ibge, source=o.source, source_record_id=o.source_record_id,
                           source_url=o.source_url, last_verified_at=o.last_verified_at, data_origin=o.data_origin, platform_status=o.platform_status,
                           license_review_status=o.license_review_status,
                           location=LocationOut(lat=loc.lat, lon=loc.lon, location_precision=loc.location_precision, geo_quality=loc.geo_quality,
                                                rankable_by_distance=loc.rankable_by_distance, coord_source=loc.coord_source, aviso=approx),
                           profile=prof, aviso=AVISO_ORG)


@router.get("", response_model=list[OrgView], summary="Lista organizações (registros de fonte pública)")
def list_orgs(uf: str | None = Query(None, min_length=2, max_length=2), municipio_ibge: int | None = None, tipo: str | None = None,
              platform_status: str | None = Query(None, pattern="^(PUBLIC_RECORD|REGISTERED)$"), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    q = select(m.Organization).options(joinedload(m.Organization.location), joinedload(m.Organization.profile)).order_by(m.Organization.ong_id).limit(limit).offset(offset)
    if uf:
        q = q.where(m.Organization.uf == uf.upper())
    if municipio_ibge:
        q = q.where(m.Organization.municipio_ibge == municipio_ibge)
    if tipo:
        q = q.where(m.Organization.ong_tipo == tipo)
    if platform_status:
        q = q.where(m.Organization.platform_status == platform_status)
    return [visible(o, user) for o in db.scalars(q).unique()]


@router.get("/{org_id}", response_model=OrgView, summary="Consulta uma organização (registro completo só para ADMIN e para a própria ONG)")
def get_org(org_id: uuid.UUID, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    o = db.scalar(select(m.Organization).options(joinedload(m.Organization.location), joinedload(m.Organization.profile)).where(m.Organization.id == org_id))
    if o is None:
        raise HTTPException(404, "organização não encontrada")
    return visible(o, user)


@router.patch("/{org_id}/registration", response_model=OrganizationOut, summary="ADMIN registra o aceite da organização na plataforma")
def register_org(org_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN"))):
    o = db.scalar(select(m.Organization).options(joinedload(m.Organization.location), joinedload(m.Organization.profile)).where(m.Organization.id == org_id))
    if o is None:
        raise HTTPException(404, "organização não encontrada")
    o.platform_status, o.registered_at = "REGISTERED", dt.datetime.now(dt.timezone.utc)
    audit("organization.register", "OK", request, user, "organization", org_id, 200, session=db)
    db.commit()
    return to_out(o)


@router.put("/{org_id}/profile", response_model=OrganizationOut, summary="ONG declara o próprio perfil (USER_ENTERED); exige organização REGISTERED")
def put_profile(org_id: uuid.UUID, body: ProfileIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ORG", "ADMIN"))):
    if user.role == "ORG" and user.organization_id != org_id:
        raise forbid(request, user, "organization", org_id)
    o = db.scalar(select(m.Organization).options(joinedload(m.Organization.location), joinedload(m.Organization.profile)).where(m.Organization.id == org_id))
    if o is None:
        raise HTTPException(404, "organização não encontrada")
    if o.platform_status != "REGISTERED":
        raise HTTPException(409, "organização ainda não cadastrada/aceita na plataforma (platform_status=PUBLIC_RECORD)")
    mask = sum(1 << d for d in set(body.open_days))
    p = o.profile
    vals = dict(capacity_min_kg_day=body.capacity_min_kg_day, capacity_max_kg_day=body.capacity_max_kg_day, cold_chamber=body.cold_chamber, open_hour=body.open_hour,
                close_hour=body.close_hour, open_days_mask=mask, accepted_categories=list(body.accepted_categories), has_fleet=body.has_fleet,
                fleet_capacity_kg=body.fleet_capacity_kg if body.has_fleet else None, fleet_refrigerated=body.fleet_refrigerated and body.has_fleet,
                data_origin="USER_ENTERED", generator_version=None, seed=None, dataset_version=None, updated_at=dt.datetime.now(dt.timezone.utc))
    if p is None:
        p = m.OrganizationProfile(organization_id=o.id, **vals)
        db.add(p)
    else:
        for k, v in vals.items():
            setattr(p, k, v)
    audit("organization.profile_put", "OK", request, user, "organization", org_id, 200, session=db)
    db.commit()
    STATE.reload_index()  # perfil mudou: reconstrói o índice em memória
    db.refresh(o)
    return to_out(o)
