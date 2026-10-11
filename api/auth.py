"""Autenticação mínima por TOKEN DE USUÁRIO (portador/Bearer) com perfil DONOR | ORG | ADMIN, validada por dependência do FastAPI.

* O token é gerado com `secrets.token_urlsafe(32)` (256 bits) e mostrado UMA vez; no banco fica só o SHA-256 (token de alta entropia ⇒ hash rápido é adequado).
* Falhas de autenticação/autorização vão para audit_logs SEM gravar o token.
* LIMITAÇÕES (registradas em security/STRIDE.md): tokens estáticos sem expiração/rotação automática/escopos; sem TLS e sem rate limit nesta fase (Parte 2/Fase 3)."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from typing import Any, Callable, Iterator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models as m
from database.session import get_sessionmaker, session_scope

log = logging.getLogger("api.auth")
bearer = HTTPBearer(auto_error=False, description="Token de usuário (Authorization: Bearer <token>)")
TOKEN_PREFIX = "rai_"


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_db() -> Iterator[Session]:
    s = get_sessionmaker()()
    try:
        yield s
    finally:
        s.close()


def audit(action: str, outcome: str, request: Request | None = None, user: m.User | None = None, resource_type: str | None = None, resource_id: Any = None,
          status_code: int | None = None, detail: dict | None = None, session: Session | None = None) -> None:
    """Grava em audit_logs (sessão própria por padrão, para sobreviver a rollback). NUNCA recebe nem grava o token."""
    row = m.AuditLog(user_id=user.id if user else None, role=user.role if user else None, action=action, resource_type=resource_type,
                     resource_id=str(resource_id) if resource_id is not None else None, outcome=outcome, status_code=status_code,
                     method=request.method if request else None, path=(request.url.path[:200] if request else None),
                     client_ip=(request.client.host if request and request.client else None), detail=detail or {})
    try:
        if session is not None:
            session.add(row)
        else:
            with session_scope() as s:
                s.add(row)
    except Exception:  # auditoria nunca derruba a requisição, mas a falha é logada
        log.exception("falha ao gravar audit_log")


def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> m.User:
    if creds is None or not creds.credentials:
        audit("auth.missing_token", "AUTH_FAILED", request, status_code=401)
        raise HTTPException(401, "autenticação necessária", headers={"WWW-Authenticate": "Bearer"})
    user = db.scalar(select(m.User).where(m.User.token_hash == hash_token(creds.credentials)))
    if user is None or not user.is_active:
        audit("auth.invalid_token", "AUTH_FAILED", request, user=user, status_code=401, detail={"motivo": "token desconhecido" if user is None else "usuário inativo"})
        raise HTTPException(401, "credenciais inválidas", headers={"WWW-Authenticate": "Bearer"})
    request.state.user = user
    return user


def require_roles(*roles: str) -> Callable[..., m.User]:
    def dep(request: Request, user: m.User = Depends(current_user)) -> m.User:
        if user.role not in roles:
            audit("authz.role_denied", "FORBIDDEN", request, user=user, status_code=403, detail={"exigido": list(roles)})
            raise HTTPException(403, "perfil sem permissão para este recurso")
        return user
    return dep


def forbid(request: Request, user: m.User, resource_type: str, resource_id: Any, reason: str = "recurso de outro usuário") -> HTTPException:
    """Registra e devolve 403 (autorização por dono do recurso). Usar: raise forbid(...)."""
    audit("authz.owner_denied", "FORBIDDEN", request, user=user, resource_type=resource_type, resource_id=resource_id, status_code=403, detail={"motivo": reason})
    return HTTPException(403, "acesso negado a este recurso")


def new_uuid(s: str) -> uuid.UUID:
    try:
        return uuid.UUID(s)
    except ValueError:
        raise HTTPException(422, "identificador inválido")
