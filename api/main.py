"""API FastAPI da Rede Alimenta IA — Fase 2 Parte 1 (plataforma, API e motor de match DOADOR → ONG).

Executar: DATABASE_URL=... uvicorn api.main:app   (Swagger em /docs).
Autenticação por token de usuário (Bearer) com perfis DONOR | ORG | ADMIN em TODOS os endpoints, exceto /health, /ready e a documentação OpenAPI.
Não há rotas de coleta/roteirização (Parte 2)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routers import admin, donations, donors, matches, organizations, predictions, public_data
from api.state import STATE
from core.settings import SETTINGS
from database.session import session_scope
from match import lifecycle

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _expiry_loop() -> None:
    """Tarefa em segundo plano: propostas sem resposta no prazo expiram e passam à próxima candidata (sem fila externa)."""
    loop = asyncio.get_running_loop()

    def once() -> int:
        if STATE.engine is None:
            return 0
        with session_scope() as s:
            return lifecycle.expire_overdue(s, STATE.engine)

    while True:
        try:
            n = await loop.run_in_executor(None, once)
            if n:
                log.info("expiração: %d proposta(s) expirada(s) → próxima candidata", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("falha na varredura de expiração")
        await asyncio.sleep(SETTINGS.expiry_scan_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.get_running_loop().run_in_executor(None, STATE.load)
    task = asyncio.create_task(_expiry_loop())
    yield
    task.cancel()


app = FastAPI(title="Rede Alimenta IA — API v1 (Fase 2 Parte 1)", version="2.1.0", lifespan=lifespan,
              description=("Conecta DOADOR → ONG. **Modelos treinados em dados SIMULADOS; atributos declarados das ONGs são SIMULADOS; métricas não representam desempenho real.** "
                           "Autenticação: `Authorization: Bearer <token>` (perfis DONOR, ORG, ADMIN). Sem TLS/rate limit nesta fase."))


@app.exception_handler(Exception)
async def _erro_generico(request: Request, exc: Exception):
    log.exception("erro não tratado")  # detalhe só no log; resposta genérica (evita vazamento de informação)
    return JSONResponse(status_code=500, content={"detail": "erro interno"})


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["infra"])
def ready():
    ok, why = STATE.ready()
    if not ok:
        return JSONResponse(status_code=503, content={"status": "not_ready", "motivo": why})
    return {"status": "ready", "model_version": STATE.ranker.meta["model_version"], "parser_version": STATE.parser.version, "engine_version": SETTINGS.engine_version,
            "orgs_ranqueaveis": len(STATE.index.orgs)}


for r in (organizations.router, public_data.router, donors.router, donations.router, matches.router, predictions.router, admin.router):
    app.include_router(r)
