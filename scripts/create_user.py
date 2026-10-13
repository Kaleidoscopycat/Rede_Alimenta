"""Cria um usuário (token mostrado UMA vez; só o hash vai ao banco). Uso:
  python -m scripts.create_user --role ADMIN --label admin-local
  python -m scripts.create_user --role DONOR --label conta-doador --donor-id <uuid> [--demo]
  python -m scripts.create_user --role ORG --label conta-ong --org-id <uuid> [--demo]
  python -m scripts.create_user --role ADMIN --label admin-ci --token-env E2E_ADMIN_TOKEN   # usa o token JÁ definido nessa variável de ambiente (CI); nada é impresso
  python -m scripts.create_user --role ADMIN --label admin-defesa --expires-in-hours 12   # token que expira sozinho (401 depois do prazo); sem a opção, não expira
  python -m scripts.create_user --revoke <label>   # desativa (is_active=false) os usuários ATIVOS com esse rótulo — ex.: token ADMIN criado para a defesa; grava auditoria `user.revoke`; não imprime token
  python -m scripts.create_user --list donors|orgs [--limit 10]   # lista ids para usar em --donor-id / --org-id (doadores SIMULATED: id do simulador; ONGs: pseudônimo público; sem dados pessoais)
Regras: contas --demo só operam sobre dados SIMULATED (doador SIMULATED / ONG sem cadastro real). O rótulo NÃO deve ser nome de pessoa física."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Portabilidade: permite `python scripts/x.py` de qualquer pasta, sem PYTHONPATH (a raiz do projeto entra em sys.path uma única vez).
_ROOT = str(_Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import argparse
import datetime as dt
import os
import re
import uuid

from sqlalchemy import select

from api.auth import hash_token, new_token
from database import models as m
from database.session import session_scope


def revoke(label: str) -> int:
    """Desativa os usuários ATIVOS com o rótulo informado (o token deixa de autenticar). Registra `user.revoke` em audit_logs (rótulo e quantidade; nunca o token). Devolve quantos foram desativados."""
    with session_scope() as s:
        users = list(s.scalars(select(m.User).where(m.User.label == label, m.User.is_active.is_(True))))
        for u in users:
            u.is_active = False
        s.add(m.AuditLog(user_id=None, role=None, action="user.revoke", resource_type="user", resource_id=None, outcome="OK" if users else "NOOP", status_code=None, method="CLI", path=None,
                         client_ip=None, detail={"label": label, "desativados": len(users), "roles": sorted({u.role for u in users})}))
    return len(users)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["DONOR", "ORG", "ADMIN"])
    ap.add_argument("--label")
    ap.add_argument("--list", choices=["donors", "orgs"], help="apenas lista ids de doadores SIMULATED ou de ONGs (pseudônimo) para usar nos comandos de criação")
    ap.add_argument("--revoke", metavar="LABEL", help="desativa os usuários ativos com este rótulo (revogação do token, p.ex. o ADMIN criado para a defesa)")
    ap.add_argument("--expires-in-hours", type=float, help="o token deixa de valer após N horas (0 < N <= 720); sem a opção o token não expira")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--donor-id")
    ap.add_argument("--org-id")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--token-env", help="nome da variável de ambiente que já contém o token (formato rai_...); o token NÃO é impresso. Usado pelo CI para um token por perfil")
    a = ap.parse_args()
    if a.revoke:
        n = revoke(a.revoke)
        print(f"revogados={n}" + ("" if n else " (nenhum usuário ativo com este rótulo)"))
        return
    if a.list:
        with session_scope() as s:
            if a.list == "donors":
                rows = s.execute(select(m.Donor.id, m.Donor.external_id, m.Donor.data_origin).where(m.Donor.data_origin == "SIMULATED").order_by(m.Donor.external_id).limit(max(a.limit, 1))).all()
            else:
                rows = s.execute(select(m.Organization.id, m.Organization.ong_id, m.Organization.data_origin).order_by(m.Organization.ong_id).limit(max(a.limit, 1))).all()
        for r in rows:
            print(f"{r[0]}  {r[1]}  {r[2]}")
        return
    if a.expires_in_hours is not None and not (0 < a.expires_in_hours <= 720):
        raise SystemExit("--expires-in-hours deve estar entre 0 (exclusivo) e 720 (30 dias)")
    if not a.role or not a.label:
        raise SystemExit("informe --role e --label (ou use --list donors|orgs)")
    if a.token_env:
        token = os.environ.get(a.token_env, "")
        if not re.fullmatch(r"rai_[A-Za-z0-9_\-]{40,}", token):
            raise SystemExit(f"a variável {a.token_env} não contém um token válido (esperado: rai_ + 40 ou mais caracteres de token_urlsafe)")
    else:
        token = new_token()
    with session_scope() as s:
        donor = s.get(m.Donor, uuid.UUID(a.donor_id)) if a.donor_id else None
        org = s.get(m.Organization, uuid.UUID(a.org_id)) if a.org_id else None
        if a.role == "DONOR" and (donor is None or a.demo != (donor.data_origin == "SIMULATED")):
            raise SystemExit("DONOR exige --donor-id; --demo se e somente se o doador for SIMULATED")
        if a.role == "ORG" and (org is None or (not a.demo and org.platform_status != "REGISTERED")):
            raise SystemExit("ORG exige --org-id; conta real exige organização REGISTERED (use --demo para dados SIMULATED)")
        u = m.User(role=a.role, label=a.label, donor_id=donor.id if donor else None, organization_id=org.id if org else None, token_hash=hash_token(token), is_demo=a.demo,
                   expires_at=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=a.expires_in_hours)) if a.expires_in_hours else None)
        if a.token_env and s.scalar(select(m.User.id).where(m.User.token_hash == u.token_hash)):
            raise SystemExit("já existe um usuário com este token")
        s.add(u)
        s.flush()
        if a.token_env:
            print(f"user_id={u.id}\nrole={a.role}\n(token lido de {a.token_env}; não é exibido)")
        else:
            print(f"user_id={u.id}\nTOKEN={token}\n(guarde agora; não é possível recuperar)")
        if u.expires_at:
            print(f"expira_em={u.expires_at.isoformat()}")


if __name__ == "__main__":
    main()
