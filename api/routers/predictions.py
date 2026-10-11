from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from api.auth import audit, get_db, require_roles
from api.routers.donations import resolve_donor
from api.schemas import LoteIn, ModelInfo, PredictOut
from api.schemas_v2 import PredictionIn
from api.service import AVISO
from api.state import STATE
from core.settings import SETTINGS
from database import models as m

router = APIRouter(prefix="/api/v1", tags=["modelo"])


@router.post("/predictions", response_model=PredictOut, summary="Predição direta do ranker da Fase 1 (sem criar doação/match)")
def predictions(body: PredictionIn, request: Request, db: Session = Depends(get_db), user: m.User = Depends(require_roles("DONOR", "ADMIN"))):
    donor = resolve_donor(db, request, user, body.donor_id)
    if STATE.ranker is None:
        raise HTTPException(503, "modelo indisponível")
    data = body.model_dump(exclude={"donor_id"})
    try:
        lote = LoteIn(**data)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False, include_input=False)) from None
    r = STATE.ranker
    t0 = time.perf_counter()
    try:
        out = r.predict(lote.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    ms = (time.perf_counter() - t0) * 1000
    res = PredictOut(**out, model_version=r.meta["model_version"], data_version=r.data_version, data_origin=r.meta["data_origin"], aviso=AVISO)
    db.add(m.MlPrediction(kind="RANKER", model_name="ranker", model_version=r.meta["model_version"], output={"top": [x.model_dump() for x in res.ranking[:5]], "confidence": res.confidence},
                          confidence=res.confidence, training_data_origin="SIMULATED", subject_data_origin=donor.data_origin, latency_ms=ms, created_by=user.id))
    audit("prediction.create", "OK", request, user, "donor", donor.id, 200, session=db)
    db.commit()
    return res


@router.get("/model/info", summary="Versões, hashes, origem dos dados de treino e limitações dos modelos e do motor")
def model_info(user: m.User = Depends(require_roles("DONOR", "ORG", "ADMIN"))):
    if STATE.ranker is None or STATE.parser is None:
        raise HTTPException(503, "modelo indisponível")
    mt = STATE.ranker.meta
    return {"ranker": ModelInfo(model_version=mt["model_version"], model_name=mt["model_name"], model_sha256=mt["model_sha256"], trained_at=mt["trained_at"],
                                data_version_simulada=mt["data_version_simulada"], data_origin=mt["data_origin"], features=mt["features"], feature_origin=mt["feature_origin"],
                                threshold_val=mt["threshold_val"], metricas_resumo_teste=mt["metricas_resumo_teste"], aviso=AVISO).model_dump(),
            "parser": {"parser_version": STATE.parser.version, **STATE.parser.meta, "threshold_note": "limiar calibrado sobre texto simulado", "training_data_origin": "SIMULATED",
                       "manually_labeled": "ausente — PROVISORIO_rascunho_ia.csv é rascunho gerado por IA e NÃO é rotulagem manual (não usado como teste de desempenho)"},
            "match_engine": {"engine_version": SETTINGS.engine_version, "weights": STATE.engine.weights(), "proposal_ttl_minutes": SETTINGS.proposal_ttl_minutes},
            "avisos": ["métricas do ranker/parser foram calculadas sobre dados SIMULADOS e não representam desempenho real",
                       "dados simulados com limitações conhecidas: R1 (volume por banco) não passa e R6 (kg sem destino) mostra simulador pessimista; não use taxas/volumes simulados como mundo real"]}
