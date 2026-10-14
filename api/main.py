"""API FastAPI da Rede Alimenta IA — Fase 2 Parte 1 (plataforma, API e motor de match DOADOR → ONG).

Executar: DATABASE_URL=... uvicorn api.main:app   (Swagger em /docs).
Autenticação por token de usuário (Bearer) com perfis DONOR | ORG | ADMIN em TODOS os endpoints, exceto /health, /ready e a documentação OpenAPI.
Rotas de coleta (Fase 2 Parte 2): POST /api/v1/routes/plan e GET /api/v1/routes/{id}."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.openapi_docs import DESCRICAO, instalar
from api.routers import admin, admin_stats, donations, drafts, donors, matches, organizations, predictions, public_data, routes
from api.state import STATE
from core.logging_setup import REQUEST_ID_HEADER, RequestContextMiddleware, configure_logging
from core.hardening import RateLimitMiddleware, SecurityHeadersMiddleware, cors_origins
from core.settings import IS_PRODUCTION, SETTINGS
from database.session import session_scope
from match import lifecycle

configure_logging()  # JSON em production, texto legível em development (APP_ENV)
log = logging.getLogger("api")


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


# production: /docs, /redoc e /openapi.json desligados (a documentação pública da API não é exposta); development: comportamento anterior
app = FastAPI(title="Rede Alimenta IA — API v1 (Fase 3 Parte 2)", version="3.2.0", lifespan=lifespan,
              docs_url=None if IS_PRODUCTION else "/docs", redoc_url=None if IS_PRODUCTION else "/redoc", openapi_url=None if IS_PRODUCTION else "/openapi.json",
              description=DESCRICAO)
instalar(app)  # contrato OpenAPI com erros padronizados e exemplos genéricos (api/openapi_docs.py); não altera rotas nem respostas


# Ordem das middlewares (a última adicionada é a mais externa): RequestContext → CORS → cabeçalhos de segurança → rate limit → rotas.
# O rate limit fica por dentro para que o 429 também saia com cabeçalhos de segurança/CORS e entre no log de requisição com request_id.
app.add_middleware(RateLimitMiddleware)  # por token/IP, desligável por RATE_LIMIT_ENABLED=false; isenta /health e /ready
if IS_PRODUCTION:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
                       allow_credentials=False, max_age=600)
app.add_middleware(RequestContextMiddleware)  # request_id + log de requisição + 500 genérico com request_id (a middleware captura antes do handler abaixo)


@app.exception_handler(Exception)
async def _erro_generico(request: Request, exc: Exception):
    """Rede de segurança (a middleware já converte exceções em 500 genérico). Detalhe só no log; resposta sem traceback e com o request_id."""
    rid = getattr(request.state, "request_id", "-")
    log.exception("erro não tratado", extra={"request_id": rid, "evt": "unhandled_exception"})
    return JSONResponse(status_code=500, content={"detail": "erro interno", "request_id": rid}, headers={REQUEST_ID_HEADER: rid})


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


for r in (organizations.router, public_data.router, donors.router, donations.router, drafts.router, matches.router, predictions.router, admin.router, admin_stats.router, routes.router):
    app.include_router(r)
