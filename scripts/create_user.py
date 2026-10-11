"""Cria um usuário (token mostrado UMA vez; só o hash vai ao banco). Uso:
  python -m scripts.create_user --role ADMIN --label admin-local
  python -m scripts.create_user --role DONOR --label conta-doador --donor-id <uuid> [--demo]
  python -m scripts.create_user --role ORG --label conta-ong --org-id <uuid> [--demo]
Regras: contas --demo só operam sobre dados SIMULATED (doador SIMULATED / ONG sem cadastro real). O rótulo NÃO deve ser nome de pessoa física."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Portabilidade: permite `python scripts/x.py` de qualquer pasta, sem PYTHONPATH (a raiz do projeto entra em sys.path uma única vez).
_ROOT = str(_Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import argparse
import uuid

from api.auth import hash_token, new_token
from database import models as m
from database.session import session_scope


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=["DONOR", "ORG", "ADMIN"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--donor-id")
    ap.add_argument("--org-id")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    token = new_token()
    with session_scope() as s:
        donor = s.get(m.Donor, uuid.UUID(a.donor_id)) if a.donor_id else None
        org = s.get(m.Organization, uuid.UUID(a.org_id)) if a.org_id else None
        if a.role == "DONOR" and (donor is None or a.demo != (donor.data_origin == "SIMULATED")):
            raise SystemExit("DONOR exige --donor-id; --demo se e somente se o doador for SIMULATED")
        if a.role == "ORG" and (org is None or (not a.demo and org.platform_status != "REGISTERED")):
            raise SystemExit("ORG exige --org-id; conta real exige organização REGISTERED (use --demo para dados SIMULATED)")
        u = m.User(role=a.role, label=a.label, donor_id=donor.id if donor else None, organization_id=org.id if org else None, token_hash=hash_token(token), is_demo=a.demo)
        s.add(u)
        s.flush()
        print(f"user_id={u.id}\nTOKEN={token}\n(guarde agora; não é possível recuperar)")


if __name__ == "__main__":
    main()
