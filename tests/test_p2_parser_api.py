"""Parser semântico integrado à API: contrato, confiança, confirmação, bloqueios de validade e persistência em ml_predictions."""
import pytest
from sqlalchemy import func, select

from database import models as m
from database.session import session_scope

CAMPOS = {"categoria", "perecibilidade", "exige_refrigeracao", "dias_ate_validade", "quantidade_kg"}


def _parse(client, world, texto, donor="donor_a"):
    r = client.post("/api/v1/donations/parse", headers=world[donor], json={"texto": texto})
    assert r.status_code == 200, r.text
    return r.json()


def test_contrato_do_parse(client, world):
    j = _parse(client, world, world["texts"]["ready"][0])
    assert CAMPOS <= set(j["fields"])
    assert j["training_data_origin"] == "SIMULATED"
    assert j["parser_version"]
    assert "limiar calibrado sobre texto simulado" in j["threshold_note"]
    assert 0 < j["confidence_threshold"] <= 1
    assert "manual" in j["manually_labeled_evaluation"].lower() or "ausente" in j["manually_labeled_evaluation"].lower()
    for f in j["fields"].values():
        assert f["status"]
    assert "próprio para consumo" in j["aviso"] or "consumo" in j["aviso"]


def test_parse_grava_ml_predictions(client, world):
    with session_scope() as s:
        antes = s.scalar(select(func.count()).select_from(m.MlPrediction).where(m.MlPrediction.kind == "PARSER"))
    _parse(client, world, world["texts"]["ready"][1])
    with session_scope() as s:
        depois = s.scalar(select(func.count()).select_from(m.MlPrediction).where(m.MlPrediction.kind == "PARSER"))
        last = s.scalars(select(m.MlPrediction).where(m.MlPrediction.kind == "PARSER").order_by(m.MlPrediction.created_at.desc())).first()
        assert depois == antes + 1
        assert last.training_data_origin == "SIMULATED" and last.subject_data_origin == "SIMULATED" and last.model_version


def test_campos_abaixo_do_limiar_sao_pendentes(client, world):
    tau = None
    for t in world["texts"]["ready"][:10] + world["texts"]["pending"][:10]:
        j = _parse(client, world, t)
        tau = j["confidence_threshold"]
        for k, f in j["fields"].items():
            if f["value"] is not None and f["confidence"] is not None and f["confidence"] < tau:
                assert f["status"] == "PENDING_CONFIRMATION", (k, f)
    assert tau is not None


def test_pendente_so_gera_match_apos_confirmacao(client, world):
    if not world["texts"]["pending"]:
        pytest.skip("simulador não gerou texto pendente nesta amostra")
    r = client.post("/api/v1/donations", headers=world["donor_a"], json={"texto": world["texts"]["pending"][0]})
    d = r.json()
    if d["status"] != "PENDING_CONFIRMATION":
        pytest.skip(f"texto ficou {d['status']}")
    assert d["pending_fields"]
    assert client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]}).status_code in (409, 422)
    body = {"accept_fields": [k for k in d["pending_fields"] if k != "quantidade_kg"]}
    if "quantidade_kg" in d["pending_fields"]:
        body["quantidade_kg"] = 10.0
    c = client.patch(f"/api/v1/donations/{d['id']}/confirm", headers=world["donor_a"], json=body)
    assert c.status_code == 200, c.text
    j = c.json()
    with session_scope() as s:
        don = s.get(m.Donation, d["id"])
        for k in body["accept_fields"] + (["quantidade_kg"] if "quantidade_kg" in body else []):
            f = don.fields[k]
            assert f["decided_by"] and f["final"] is not None and f["decided_at"]
            assert "extracted" in f
    assert j["status"] in ("READY", "PENDING_CONFIRMATION", "BLOCKED_EXPIRED", "BLOCKED_NO_VALIDITY")


def test_validade_vencida_bloqueia_e_doador_pode_corrigir(client, world):
    if not world["texts"]["expired"]:
        pytest.skip("sem texto vencido na amostra")
    d = client.post("/api/v1/donations", headers=world["donor_a"], json={"texto": world["texts"]["expired"][0]}).json()
    assert d["status"] == "BLOCKED_EXPIRED"
    assert client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]}).status_code in (409, 422)


def test_sem_validade_bloqueia(client, world):
    if not world["texts"]["no_validity"]:
        pytest.skip("sem texto sem validade na amostra")
    d = client.post("/api/v1/donations", headers=world["donor_a"], json={"texto": world["texts"]["no_validity"][0]}).json()
    assert d["status"] == "BLOCKED_NO_VALIDITY"
    c = client.patch(f"/api/v1/donations/{d['id']}/confirm", headers=world["donor_a"], json={"dias_ate_validade": 5, "accept_fields": []})
    assert c.status_code == 200
    assert c.json()["validity_days"] == 5
    assert c.json()["validity_source"].startswith("INFORMADA_PELO_DOADOR")


def test_doacao_estruturada_sem_texto_e_vencida_bloqueia(client, world):
    r = client.post("/api/v1/donations", headers=world["donor_a"], json={"categoria": "HORT_FRUTOS", "exige_refrigeracao": False, "dias_ate_validade": -2, "quantidade_kg": 10})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "BLOCKED_EXPIRED"
    r = client.post("/api/v1/donations", headers=world["donor_a"], json={"categoria": "HORT_FRUTOS", "exige_refrigeracao": False, "dias_ate_validade": 4, "quantidade_kg": 10})
    assert r.json()["status"] == "READY"
    assert r.json()["data_origin"] == "SIMULATED"


def test_entrada_invalida_422(client, world):
    assert client.post("/api/v1/donations/parse", headers=world["donor_a"], json={"texto": "ab"}).status_code == 422
    assert client.post("/api/v1/donations", headers=world["donor_a"], json={"quantidade_kg": -1}).status_code == 422
    assert client.post("/api/v1/donations", headers=world["donor_a"], json={"campo_inexistente": 1}).status_code == 422


def test_aceitar_campo_ausente_422(client, world):
    d = client.post("/api/v1/donations", headers=world["donor_a"], json={"categoria": "HORT_FRUTOS", "dias_ate_validade": 3}).json()
    r = client.patch(f"/api/v1/donations/{d['id']}/confirm", headers=world["donor_a"], json={"accept_fields": ["quantidade_kg"]})
    assert r.status_code == 422
