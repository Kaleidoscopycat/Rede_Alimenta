from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import audit, forbid, get_db, require_roles
from api.schemas_v2 import DonorCreate, DonorOut
from database import models as m

router = APIRouter(prefix="/api/v1/donors", tags=["doadores"])


def donor_out(d: m.Donor, loc: m.DonorLocation | None) -> DonorOut:
    return DonorOut(id=d.id, donor_type=d.donor_type, donor_size=d.donor_size, display_name=d.display_name, municipio_ibge=d.municipio_ibge, data_origin=d.data_origin,
                    location_precision=loc.location_precision if loc else None, pickup_days_mask=d.pickup_days_mask, pickup_start_h=d.pickup_start_h, pickup_end_h=d.pickup_end_h)


@router.post("", response_model=DonorOut, status_code=201, summary="ADMIN cadastra doador (pessoa jurídica) — sempre USER_ENTERED")
def create_donor(body: DonorCreate, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN"))):
    muni = db.get(m.Municipality, body.municipio_ibge)
    if muni is None:
        raise HTTPException(422, "município não encontrado na base IBGE")
    d = m.Donor(donor_type=body.donor_type, donor_size=body.donor_size, display_name=body.display_name, municipio_ibge=body.municipio_ibge,
                pickup_days_mask=sum(1 << x for x in set(body.pickup_days)), pickup_start_h=body.pickup_start_h, pickup_end_h=body.pickup_end_h, load_minutes=body.load_minutes,
                data_origin="USER_ENTERED")
    db.add(d)
    db.flush()
    if body.lat is not None:
        loc = m.DonorLocation(donor_id=d.id, lat=body.lat, lon=body.lon, location_precision="EXACT", basis="INFORMADA_PELO_CADASTRO", data_origin="USER_ENTERED")
    elif muni.lat is not None:
        loc = m.DonorLocation(donor_id=d.id, lat=muni.lat, lon=muni.lon, location_precision="MUNICIPALITY_CENTROID", basis="CENTROIDE_MUNICIPIO", data_origin="USER_ENTERED")
    else:
        raise HTTPException(422, "município sem coordenada conhecida: informe lat/lon")
    db.add(loc)
    audit("donor.create", "OK", request, user, "donor", d.id, 201, session=db)
    db.commit()
    return donor_out(d, loc)


@router.get("/{donor_id}", response_model=DonorOut)
def get_donor(donor_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("ADMIN", "DONOR"))):
    if user.role == "DONOR" and user.donor_id != donor_id:
        raise forbid(request, user, "donor", donor_id)
    d = db.get(m.Donor, donor_id)
    if d is None:
        raise HTTPException(404, "doador não encontrado")
    loc = db.scalars(select(m.DonorLocation).where(m.DonorLocation.donor_id == d.id).order_by(m.DonorLocation.id.desc())).first()
    return donor_out(d, loc)
