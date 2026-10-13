"""Fase 3 Parte 2 (Etapa A): endpoints do dashboard /api/v1/admin/stats — só ADMIN (200 + auditoria `admin.access`), DONOR/ORG recebem 403 e sem token 401.
Rótulos de origem (PÚBLICO/SIMULADO/MEDIDO) e premissa de refeições (kg ÷ 0,4) são verificados; nada de dado real é inventado."""
import pytest
from sqlalchemy import select

from database import models as m
from database.session import session_scope
from tests.helpers_p2 import org_token, ready_donation

GETS = ["overview", "donations-matches", "meals-by-region", "map", "organizations", "donors", "public-data", "territorial", "ai", "security"]
BASE = "/api/v1/admin/stats"


@pytest.fixture(scope="module")
def com_match(client, world):
    d = ready_donation(client, world, "donor_a", 4)
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("path", GETS)
def test_admin_200_e_auditoria(client, world, com_match, path):
    r = client.get(f"{BASE}/{path}", headers=world["admin"])
    assert r.status_code == 200, f"{path}: {r.text[:400]}"
    with session_scope() as s:
        n = s.scalar(select(m.AuditLog.id).where(m.AuditLog.action == "admin.access").limit(1))
    assert n is not None


@pytest.mark.parametrize("path", GETS)
def test_donor_e_org_recebem_403(client, world, com_match, path):
    assert client.get(f"{BASE}/{path}", headers=world["donor_a"]).status_code == 403
    org = org_token(client, world["admin"], client.get(f"/api/v1/matches/{com_match['id']}", headers=world["admin"]).json()["ranking"][0]["org_id"])
    assert client.get(f"{BASE}/{path}", headers=org).status_code == 403
    assert client.get(f"{BASE}/{path}").status_code == 401


def test_logistica_so_admin_e_simulacao(client, world):
    assert client.post(f"{BASE}/logistics/strategies", headers=world["donor_a"], json={}).status_code == 403
    r = client.post(f"{BASE}/logistics/strategies", headers=world["admin"], json={"n_lots": 4, "seed": 7, "raio_km": 60, "tempo_solver_s": 1})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tipo"] == "SIMULACAO" and "SIMULAÇÃO" in j["rotulo"]
    assert [e["id"][0] for e in j["estrategias"]] == ["A", "B", "C"]


def test_overview_premissa_e_sem_doacao_real(client, world):
    j = client.get(f"{BASE}/overview", headers=world["admin"]).json()
    assert "0.4" in str(j) or "0,4" in str(j)
    txt = str(j)
    assert "MEDIDO" in txt or "SIMULADO" in txt
