from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.auth import audit, current_user, get_db, hash_token, new_token, require_roles
from api.schemas_v2 import MeOut, UserCreate, UserCreated
from api.state import STATE
from database import models as m

router = APIRouter(prefix="/api/v1", tags=["conta e administração"])
LIMITES = ("Autenticação mínima: token estático por usuário (expiração opcional e revogação manual; sem rotação automática nem escopos). O TLS é terminado pela plataforma de hospedagem; "
           "há limite de tentativas de autenticação inválidas por IP (em memória, por instância) e não há limite global de requisições (ver security/STRIDE.md e docs/SEGURANCA_FINAL.md).")


@router.get("/me", response_model=MeOut, summary="Identidade do token (perfil e vínculo)")
def me(user: m.User = Depends(current_user)):
    scope = "ALL" if user.role == "ADMIN" else ("SIMULATED" if user.is_demo else "USER_ENTERED")
    return MeOut(user_id=user.id, role=user.role, label=user.label, donor_id=user.donor_id, organization_id=user.organization_id, is_demo=user.is_demo, data_origin_scope=scope,
                 auth_limitations=LIMITES)


@router.post("/admin/users", response_model=UserCreated, status_code=201, summary="ADMIN cria usuário e recebe o token UMA vez")
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: m.User = Depends(require_roles("ADMIN"))):
    donor = db.get(m.Donor, body.donor_id) if body.donor_id else None
    org = db.get(m.Organization, body.organization_id) if body.organization_id else None
    if body.role == "DONOR":
        if donor is None or body.organization_id:
            raise HTTPException(422, "perfil DONOR exige donor_id existente (e nenhum organization_id)")
        if body.is_demo != (donor.data_origin == "SIMULATED"):
            raise HTTPException(422, "conta de demonstração (is_demo) só pode ser vinculada a doador SIMULATED, e doador SIMULATED só aceita conta is_demo")
    elif body.role == "ORG":
        if org is None or body.donor_id:
            raise HTTPException(422, "perfil ORG exige organization_id existente (e nenhum donor_id)")
        if not body.is_demo and org.platform_status != "REGISTERED":
            raise HTTPException(422, "conta real de ONG exige organização REGISTERED (cadastro/aceite); contas is_demo operam só sobre dados SIMULATED")
    else:
        if body.donor_id or body.organization_id or body.is_demo:
            raise HTTPException(422, "ADMIN não se vincula a doador/organização nem é demo")
    token = new_token()
    u = m.User(role=body.role, label=body.label, donor_id=body.donor_id, organization_id=body.organization_id, token_hash=hash_token(token), is_demo=body.is_demo)
    db.add(u)
    db.flush()
    audit("user.create", "OK", request, admin, "user", u.id, 201, detail={"role": body.role, "is_demo": body.is_demo}, session=db)
    db.commit()
    return UserCreated(user_id=u.id, role=u.role, label=u.label, token=token, aviso="Guarde o token agora: ele não pode ser recuperado (apenas o hash é armazenado). " + LIMITES)


@router.post("/admin/reload-index", summary="ADMIN recarrega o índice de ONGs em memória a partir do banco")
def reload_index(request: Request, db: Session = Depends(get_db), admin: m.User = Depends(require_roles("ADMIN"))):
    STATE.reload_index()
    audit("index.reload", "OK", request, admin, status_code=200, session=db)
    db.commit()
    return {"orgs_ranqueaveis": len(STATE.index.orgs), "sem_localizacao": STATE.index.n_no_location, "sem_perfil_declarado": STATE.index.n_no_profile, "segundos": STATE.index.load_seconds}
