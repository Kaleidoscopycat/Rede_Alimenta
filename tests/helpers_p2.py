"""Auxiliares dos testes da Fase 2 Parte 1 (sem dados de negócio: tudo vem do simulador ou de ONGs reais importadas)."""
from __future__ import annotations

import itertools

from api.auth import hash_token, new_token
from database import models as m
from database.session import session_scope

_counter = itertools.count(1)


def org_token(client, admin, org_uuid: str, demo: bool = True) -> dict:
    """Conta de demonstração (is_demo) para uma ONG real: opera apenas sobre dados SIMULATED."""
    r = client.post("/api/v1/admin/users", headers=admin, json={"role": "ORG", "label": f"teste-conta-ong-{next(_counter)}", "organization_id": org_uuid, "is_demo": demo})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def new_ready_donation(client, world, donor="donor_a", kind="ready", idx=0, extra=None):
    texto = world["texts"][kind][idx]
    body = {"texto": texto, **(extra or {})}
    r = client.post("/api/v1/donations", headers=world[donor], json=body)
    assert r.status_code == 201, r.text
    return r.json()


def ready_donation(client, world, donor="donor_a", idx=0):
    d = new_ready_donation(client, world, donor, "ready", idx)
    assert d["status"] == "READY", d
    return d
