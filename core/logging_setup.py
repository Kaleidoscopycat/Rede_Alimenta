"""Logging estruturado e identificador de requisição (observabilidade — Fase 3 Parte 2).

* production  → uma linha JSON por evento (ts, level, logger, msg, request_id + campos extras), pronta para agregadores de log.
* development → texto legível, com o request_id entre colchetes.
* request_id  → aceito do cabeçalho `X-Request-ID` (somente formato seguro: 8–64 caracteres de [A-Za-z0-9._-]) ou gerado (uuid4 hex); devolvido na resposta
  e presente em TODO log emitido durante a requisição (contextvar), inclusive nas respostas de erro.
* Privacidade: o log de requisição registra método, caminho (SEM query string), status e duração. Nunca registra cabeçalhos, corpo, token nem IP de cliente.
  Quem loga eventos de negócio (predição, match, ingestão, simulação) usa identificadores técnicos e contagens, nunca texto digitado por usuário."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")
REQUEST_ID_HEADER = "X-Request-ID"
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "request_id", "taskName"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) in (None, "-"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z", "level": record.levelname, "logger": record.name,
                               "msg": record.getMessage(), "request_id": getattr(record, "request_id", "-")}
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


class DevFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")


def configure_logging(production: bool | None = None, level: str | None = None) -> None:
    """Idempotente: substitui os handlers da raiz (uvicorn mantém os seus). `production=None` usa APP_ENV."""
    from core.settings import IS_PRODUCTION
    import os
    prod = IS_PRODUCTION if production is None else production
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_rai_handler", False):
            root.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h._rai_handler = True  # type: ignore[attr-defined]
    h.addFilter(RequestIdFilter())
    h.setFormatter(JsonFormatter() if prod else DevFormatter())
    root.addHandler(h)
    root.setLevel((level or os.environ.get("LOG_LEVEL", "INFO")).upper())


def valid_request_id(v: str | None) -> str:
    return v if v and REQUEST_ID_RE.match(v) else uuid.uuid4().hex


class RequestContextMiddleware:
    """ASGI puro: define o request_id, devolve o cabeçalho, registra UMA linha por requisição e transforma exceções não tratadas em 500 genérico com o request_id (sem traceback na resposta)."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.log = logging.getLogger("api.request")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        hdr = {k.lower(): v for k, v in scope.get("headers", [])}
        rid = valid_request_id(hdr.get(b"x-request-id", b"").decode("latin-1"))
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        info = {"status": 0, "started": False}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                info["status"], info["started"] = message["status"], True
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.lower().encode(), rid.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            self.log.exception("erro não tratado", extra={"evt": "unhandled_exception", "method": scope["method"], "path": scope["path"]})
            info["status"] = 500
            if not info["started"]:
                body = json.dumps({"detail": "erro interno", "request_id": rid}).encode()
                await send({"type": "http.response.start", "status": 500, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                                                                       (REQUEST_ID_HEADER.lower().encode(), rid.encode())]})
                await send({"type": "http.response.body", "body": body})
        finally:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            lvl = logging.WARNING if info["status"] >= 500 else logging.INFO
            self.log.log(lvl, "%s %s -> %s (%.1f ms)", scope["method"], scope["path"], info["status"], ms,
                         extra={"evt": "http_request", "method": scope["method"], "path": scope["path"], "status": info["status"], "duration_ms": ms})
            request_id_var.reset(token)
