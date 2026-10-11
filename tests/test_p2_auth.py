"""Autenticação e autorização aplicadas NA API: 401 sem token, 403 perfil errado/recurso de outro usuário, acesso permitido, auditoria sem token."""
from sqlalchemy import select

from database import models as m
from database.session import session_scope
from tests.helpers_p2 import org_token, ready_donation

PUBLICOS = ["/health", "/ready", "/openapi.json", "/docs"]


def test_rotas_publicas_sem_token(client):
    for p in PUBLICOS:
        assert client.get(p).status_code == 200, p


def test_sem_token_401_em_todos_os_endpoints_protegidos(client, world):
    protegidos = [("GET", "/api/v1/organizations"), ("GET", "/api/v1/public-data/sources"), ("GET", "/api/v1/model/info"), ("GET", "/api/v1/me"), ("GET", "/api/v1/matches"),
                  ("POST", "/api/v1/donations/parse"), ("POST", "/api/v1/donations"), ("POST", "/api/v1/matches"), ("POST", "/api/v1/predictions"), ("POST", "/api/v1/donors"),
                  ("GET", "/api/v1/donations"), ("GET", "/api/v1/metrics/match-times")]
    for meth, path in protegidos:
        r = client.request(meth, path, json={} if meth == "POST" else None)
        assert r.status_code == 401, (meth, path, r.status_code)
        assert r.headers.get("www-authenticate") == "Bearer"


def test_token_invalido_401_e_nao_grava_token(client):
    fake = "rai_token_invalido_para_teste_0123456789"
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {fake}"})
    assert r.status_code == 401
    with session_scope() as s:
        logs = s.scalars(select(m.AuditLog).where(m.AuditLog.outcome == "AUTH_FAILED")).all()
        assert logs
        assert all(fake not in str(l.detail) and fake not in (l.path or "") and fake not in (l.resource_id or "") for l in logs)
        assert not any("rai_" in str(l.detail) for l in logs)


def test_perfil_errado_403(client, world):
    # DONOR não cadastra doadores nem lê métricas administrativas
    assert client.post("/api/v1/donors", headers=world["donor_a"], json={"donor_type": "MERCADO", "municipio_ibge": 3550308}).status_code == 403
    assert client.get("/api/v1/metrics/match-times", headers=world["donor_a"]).status_code == 403
    assert client.post("/api/v1/admin/users", headers=world["donor_a"], json={"role": "ADMIN", "label": "tentativa-indevida"}).status_code == 403
    # ORG não cadastra doação nem gera match
    org = client.get("/api/v1/organizations?limit=1", headers=world["admin"]).json()[0]["id"]
    oh = org_token(client, world["admin"], org)
    assert client.post("/api/v1/donations", headers=oh, json={"texto": "aaa bbb"}).status_code == 403
    assert client.post("/api/v1/matches", headers=oh, json={"donation_id": "00000000-0000-0000-0000-000000000000"}).status_code == 403
    with session_scope() as s:
        assert s.scalar(select(m.AuditLog).where(m.AuditLog.outcome == "FORBIDDEN", m.AuditLog.action == "authz.role_denied").limit(1)) is not None


def test_recurso_de_outro_usuario_403(client, world):
    d = ready_donation(client, world, "donor_a", 0)
    assert client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).status_code == 200  # acesso permitido ao dono
    assert client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_b"]).status_code == 403
    assert client.patch(f"/api/v1/donations/{d['id']}/confirm", headers=world["donor_b"], json={"accept_fields": []}).status_code == 403
    assert client.post("/api/v1/matches", headers=world["donor_b"], json={"donation_id": d["id"]}).status_code == 403
    assert client.get(f"/api/v1/donors/{world['donor_a_id']}", headers=world["donor_b"]).status_code == 403
    assert client.get(f"/api/v1/donors/{world['donor_a_id']}", headers=world["donor_a"]).status_code == 200
    # doador B não lista doações do A
    ids = {x["id"] for x in client.get("/api/v1/donations", headers=world["donor_b"]).json()}
    assert d["id"] not in ids
    with session_scope() as s:
        row = s.scalar(select(m.AuditLog).where(m.AuditLog.action == "authz.owner_denied").order_by(m.AuditLog.id.desc()).limit(1))
        assert row is not None and row.outcome == "FORBIDDEN"


def test_ong_so_ve_e_responde_propostas_dirigidas_a_ela(client, world):
    d = ready_donation(client, world, "donor_a", 1)
    mt = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5}).json()
    assert mt["status"] == "PROPOSED"
    r = client.get(f"/api/v1/organizations?limit=200", headers=world["admin"]).json()
    top = mt["ranking"][0]
    other = mt["ranking"][1]
    h_top, h_other = org_token(client, world["admin"], top["org_id"]), org_token(client, world["admin"], other["org_id"])
    assert client.get(f"/api/v1/matches/{mt['id']}", headers=h_top).status_code == 200
    assert client.get(f"/api/v1/matches/{mt['id']}", headers=h_other).status_code == 403  # nunca foi proposta a ela
    assert client.post(f"/api/v1/matches/{mt['id']}/respond", headers=h_other, json={"accept": True}).status_code == 403
    assert client.get(f"/api/v1/matches/{mt['id']}/events", headers=h_other).status_code == 403
    v = client.get(f"/api/v1/matches/{mt['id']}", headers=h_top).json()
    assert "ranking" not in v and v["awaiting_my_response"] is True and v["my_candidacy"]["org_id"] == top["org_id"]  # ONG não vê as demais candidatas
    # limpa: recusa para liberar a capacidade reservada
    assert client.post(f"/api/v1/matches/{mt['id']}/respond", headers=h_top, json={"accept": False}).status_code == 200


def test_conta_demo_exige_vinculo_coerente(client, world):
    org = client.get("/api/v1/organizations?limit=1", headers=world["admin"]).json()[0]["id"]
    # conta REAL de ONG exige organização REGISTERED (nenhuma está)
    r = client.post("/api/v1/admin/users", headers=world["admin"], json={"role": "ORG", "label": "conta-real-indevida", "organization_id": org, "is_demo": False})
    assert r.status_code == 422
    # doador simulado só aceita conta de demonstração
    r = client.post("/api/v1/admin/users", headers=world["admin"], json={"role": "DONOR", "label": "conta-real-indevida", "donor_id": str(world["donor_a_id"]), "is_demo": False})
    assert r.status_code == 422


def test_token_em_claro_nao_esta_no_banco(client, world):
    with session_scope() as s:
        for u in s.scalars(select(m.User)):
            assert len(u.token_hash) == 64 and not u.token_hash.startswith("rai_")
