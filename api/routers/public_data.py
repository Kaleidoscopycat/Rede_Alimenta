from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.auth import current_user, get_db
from database import models as m

router = APIRouter(prefix="/api/v1/public-data", tags=["dados públicos"])


@router.get("/sources", summary="Fontes públicas reais, versões e status de licença (pendências de confirmação)")
def sources(db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    vers = {sid: n for sid, n in db.execute(select(m.PublicDatasetVersion.source_id, func.count()).group_by(m.PublicDatasetVersion.source_id))}
    rows = db.scalars(select(m.PublicDataSource).order_by(m.PublicDataSource.id)).all()
    items = [{"id": s.id, "name": s.name, "organization": s.organization, "dataset": s.dataset, "url": s.url, "license_status": s.license_status, "review_status": s.review_status,
              "commercial_use": s.commercial_use, "publication_cleared": s.publication_cleared, "raw_sha256": s.raw_sha256, "ingested_at": s.ingested_at, "source_updated_at": s.source_updated_at,
              "n_versions": vers.get(s.id, 0), "data_origin": s.data_origin} for s in rows]
    pend = [i["id"] for i in items if not i["publication_cleared"]]
    return {"sources": items, "pending_license_confirmation": pend,
            "aviso": "Nenhuma fonte está liberada para publicação (publication_cleared=false): confirmações formais pendentes (ver docs/data/PENDING_LICENSE_CONFIRMATIONS.md). A Fase 3 (deploy público) depende delas."}
