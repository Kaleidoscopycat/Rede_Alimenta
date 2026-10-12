"""STRIDE P2B-1 (Divulgação de informação) — MITIGADO na Fase 3 Parte 1 (seção 3): visibilidade por perfil aplicada NA API (response_model por perfil), não só na tela.
(Este arquivo substitui o antigo teste esperado-falhar `test_p2b_divulgacao_scores_pendente.py`: o comportamento desejado passou a ser exigido.)

  DONOR → só a situação da doação e a ONG que aceitou; nunca ranking, scores, elegibilidade, modelo, pesos ou latências.
  ORG   → a doação dirigida a ela, análise textual SEM scores e a própria candidatura (sem posição, sem outras ONGs).
  ADMIN → tudo; o acesso é auditado (`admin.access`)."""
import pytest
from sqlalchemy import select

from api.schemas_views import DonorDonationView, DonorMatchView, OrgMatchView
from database import models as m
from database.session import session_scope
from tests.helpers_p2 import admin_match, org_token, ready_donation

SCORES = {"ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE", "business_rule_components"}
PROIBIDAS = SCORES | {"ranking", "posicao", "eligibility", "weights", "latency_ms", "engine_version", "model_version", "current_position", "current_org", "n_candidates", "score_definitions",
                      "org_id", "regras_aprovadas", "profile_origin"}


def chaves(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            chaves(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            chaves(v, acc)
    return acc


@pytest.fixture()
def cenario(client, world):
    """Doação READY de doador SIMULADO + match PROPOSED; devolve (doação, match do doador, visão ADMIN, headers da ONG proposta)."""
    d = ready_donation(client, world, "donor_a", 3)
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5})
    assert r.status_code == 201, r.text
    full = admin_match(client, world, r.json()["id"])
    assert full["status"] == "PROPOSED" and full["ranking"]
    org = org_token(client, world["admin"], full["ranking"][0]["org_id"])
    yield d, r.json(), full, org
    mid = full["id"]
    for _ in range(40):  # libera a capacidade reservada
        st = client.get(f"/api/v1/matches/{mid}", headers=world["admin"]).json()["status"]
        if st != "PROPOSED":
            break
        client.post(f"/api/v1/matches/{mid}/respond", headers=world["admin"], json={"accept": False})


def test_doador_nao_recebe_scores_ranking_nem_elegibilidade(client, world, cenario):
    d, mt, full, _ = cenario
    assert mt["perfil"] == "DONOR" and mt["situacao"] and mt["status"] == "PROPOSED"
    assert not (chaves(mt) & PROIBIDAS), chaves(mt) & PROIBIDAS
    for path in (f"/api/v1/matches/{mt['id']}", "/api/v1/matches"):
        j = client.get(path, headers=world["donor_a"]).json()
        assert not (chaves(j) & PROIBIDAS), (path, chaves(j) & PROIBIDAS)
    # não vaza nem o pseudônimo das ONGs candidatas no corpo do match
    ongs = {c["ong_id"] for c in full["ranking"]}
    corpo = str(client.get(f"/api/v1/matches/{mt['id']}", headers=world["donor_a"]).json())
    assert not any(o in corpo for o in ongs)
    # a doação do doador também não traz scores
    dv = client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()
    assert not (chaves(dv) & PROIBIDAS)
    # eventos para o doador: só tipos e tempos
    ev = client.get(f"/api/v1/matches/{mt['id']}/events", headers=world["donor_a"]).json()["events"]
    assert ev and not (chaves(ev) & (PROIBIDAS | {"detail", "ong_id", "rank_position"}))


def test_ong_nao_recebe_scores_posicao_nem_outras_candidatas(client, world, cenario):
    _, mt, full, org = cenario
    v = client.get(f"/api/v1/matches/{mt['id']}", headers=org).json()
    assert v["perfil"] == "ORG" and v["awaiting_my_response"] is True
    assert not (chaves(v) & PROIBIDAS), chaves(v) & PROIBIDAS
    mc = v["my_candidacy"]
    assert mc["dist_km"] == full["ranking"][0]["dist_km"] and mc["explicacao"] and not any("SCORE" in e for e in mc["explicacao"])
    # análise da IA para a ONG: texto e fatos do lote, sem números de score
    a = v["donation"]["analise"]
    assert a and any("Validade mais próxima" in x for x in a) and not any("SCORE" in x.upper() for x in a)
    assert "doador_id" not in v["donation"] and v["donation"]["doador"].keys() == {"tipo", "porte", "municipio_ibge"}
    lst = client.get("/api/v1/matches?status=PROPOSED", headers=org).json()
    assert lst and not (chaves(lst) & PROIBIDAS)
    ev = client.get(f"/api/v1/matches/{mt['id']}/events", headers=org).json()["events"]
    assert ev and not (chaves(ev) & {"ong_id", "rank_position"}) and "FINAL_SCORE" not in str(ev)


def test_apenas_admin_ve_ranking_modelo_e_predictions(client, world, cenario):
    _, mt, full, org = cenario
    rota = f"/api/v1/matches/{mt['id']}/ranking"
    for hdr in (world["donor_a"], world["donor_b"], org):
        assert client.get(rota, headers=hdr).status_code == 403
        assert client.get("/api/v1/model/info", headers=hdr).status_code == 403
        assert client.post("/api/v1/predictions", headers=hdr, json={"categoria": "FRUTAS", "quantidade_kg": 1, "horas_ate_validade": 5, "municipio_ibge": 3550308}).status_code == 403
    assert client.get(rota).status_code == 401
    r = client.get(rota, headers=world["admin"]).json()
    assert r["perfil"] == "ADMIN" and r["ranking"] and SCORES & set(r["ranking"][0]) == {"ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE", "business_rule_components"}
    assert r["eligibility"]["n_eligible"] >= 1 and r["weights"] and r["latency_ms"]
    assert client.get("/api/v1/model/info", headers=world["admin"]).status_code == 200


def test_acesso_admin_e_auditado_sem_token(client, world, cenario):
    _, mt, _, _ = cenario
    with session_scope() as s:
        n0 = len(s.scalars(select(m.AuditLog.id).where(m.AuditLog.action == "admin.access")).all())
    client.get(f"/api/v1/matches/{mt['id']}/ranking", headers=world["admin"])
    client.get("/api/v1/model/info", headers=world["admin"])
    client.get(f"/api/v1/matches/{mt['id']}", headers=world["admin"])
    with session_scope() as s:
        rows = s.scalars(select(m.AuditLog).where(m.AuditLog.action == "admin.access").order_by(m.AuditLog.id.desc())).all()
        assert len(rows) >= n0 + 3
        novos = rows[:3]
        assert {r.resource_type for r in novos} >= {"match.ranking", "model_info", "match"} and all(r.role == "ADMIN" and r.outcome == "OK" for r in novos)
        assert all(world["admin"]["Authorization"].split()[1] not in str(r.detail) + (r.path or "") for r in novos)
    # acesso de doador/ONG NÃO gera admin.access
    with session_scope() as s:
        n1 = len(s.scalars(select(m.AuditLog.id).where(m.AuditLog.action == "admin.access")).all())
    client.get(f"/api/v1/matches/{mt['id']}", headers=world["donor_a"])
    with session_scope() as s:
        assert len(s.scalars(select(m.AuditLog.id).where(m.AuditLog.action == "admin.access")).all()) == n1


def test_negativas_de_acesso_sao_auditadas(client, world, cenario):
    _, mt, _, _ = cenario
    client.get(f"/api/v1/matches/{mt['id']}/ranking", headers=world["donor_a"])
    with session_scope() as s:
        row = s.scalar(select(m.AuditLog).where(m.AuditLog.action == "authz.role_denied").order_by(m.AuditLog.id.desc()).limit(1))
        assert row is not None and row.outcome == "FORBIDDEN" and row.role == "DONOR"


def test_response_model_descarta_chaves_extras_defesa_em_profundidade():
    """Mesmo que um construtor de view erre e passe campos a mais, o schema do perfil os descarta."""
    base = {"id": "5f6f1c2e-5b0e-4b3a-9f43-0a1b2c3d4e5f", "donation_id": "5f6f1c2e-5b0e-4b3a-9f43-0a1b2c3d4e50", "data_origin": "SIMULATED", "status": "PROPOSED", "situacao": "x",
            "created_at": "2026-10-13T10:00:00+00:00", "updated_at": "2026-10-13T10:00:00+00:00", "closed_at": None, "aviso": "x"}
    v = DonorMatchView.model_validate({**base, "ranking": [{"FINAL_SCORE": 0.9}], "ML_SCORE": 0.8, "current_org": "ONG-1", "weights": {}})
    assert not (set(v.model_dump()) & PROIBIDAS)
    assert OrgMatchView.model_fields.keys().isdisjoint({"ranking", "eligibility", "weights", "latency_ms", "model_version"})
    assert DonorDonationView.model_fields.keys().isdisjoint({"ranking", "eligibility", "weights"})


def test_organizacoes_visao_publica_para_doador_e_completa_para_dono_e_admin(client, world):
    adm = client.get("/api/v1/organizations?limit=3", headers=world["admin"]).json()
    assert adm and all(o["perfil"] == "COMPLETA" and "location" in o and "source_url" in o for o in adm)
    pub = client.get("/api/v1/organizations?limit=3", headers=world["donor_a"]).json()
    assert pub and all(o["perfil"] == "PUBLICA" and not ({"location", "profile", "source_url", "license_review_status", "last_verified_at", "id"} & set(o)) for o in pub)
    um = adm[0]
    own = org_token(client, world["admin"], um["id"])
    assert client.get(f"/api/v1/organizations/{um['id']}", headers=own).json()["perfil"] == "COMPLETA"
    outro = adm[1]
    assert client.get(f"/api/v1/organizations/{outro['id']}", headers=own).json()["perfil"] == "PUBLICA"


def test_me_informa_perfil_e_escopo(client, world):
    me = client.get("/api/v1/me", headers=world["donor_a"]).json()
    assert me["role"] == "DONOR" and me["is_demo"] is True and me["data_origin_scope"] == "SIMULATED" and me["donor_id"]
    assert client.get("/api/v1/me", headers=world["admin"]).json()["data_origin_scope"] == "ALL"
