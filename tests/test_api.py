"""Contrato do endpoint de predição e do modelo da Fase 1, agora sob a API v1 autenticada (Fase 2 Parte 1: /predict → POST /api/v1/predictions)."""
import pytest
from pydantic import ValidationError

from api.schemas import LoteIn

BASE = {"categoria": "FRUTAS", "quantidade_kg": 80, "horas_ate_validade": 72, "municipio_ibge": 3550308, "top_n": 3}


def test_health_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_model_info(client, world):
    j = client.get("/api/v1/model/info", headers=world["admin"]).json()
    assert j["ranker"]["model_version"] and "SIMULAD" in j["ranker"]["aviso"].upper() and j["ranker"]["model_sha256"]


def test_predict_contrato(client, world):
    r = client.post("/api/v1/predictions", headers=world["admin"], json={**BASE, "donor_id": str(world["donor_a_id"])})
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("ranking", "prediction", "confidence", "factors", "model_version", "data_version", "data_origin"):
        assert k in j
    assert len(j["ranking"]) == 3
    ps = [x["probabilidade"] for x in j["ranking"]]
    assert ps == sorted(ps, reverse=True) and all(0 <= p <= 1 for p in ps)
    assert "SIMULATED" in j["data_origin"]


def test_entradas_invalidas(client, world):
    h = world["admin"]
    d = {"donor_id": str(world["donor_a_id"])}
    assert client.post("/api/v1/predictions", headers=h, json={**d, "quantidade_kg": -1}).status_code == 422
    assert client.post("/api/v1/predictions", headers=h, json={**BASE, **d, "horas_ate_validade": 0}).status_code == 422
    assert client.post("/api/v1/predictions", headers=h, json={**BASE, **d, "categoria": "XYZ"}).status_code == 422
    assert client.post("/api/v1/predictions", headers=h, json={**d, "categoria": "FRUTAS", "quantidade_kg": 5, "horas_ate_validade": 5}).status_code == 422
    assert client.post("/api/v1/predictions", headers=h, json={**BASE, **d, "campo_extra": 1}).status_code == 422
    # predictions e model/info: só ADMIN (Fase 3 Parte 1, seção 3)
    assert client.post("/api/v1/predictions", headers=world["donor_a"], json=BASE).status_code == 403


def test_resposta_nao_expoe_pessoa_fisica(client, world):
    j = client.post("/api/v1/predictions", headers=world["admin"], json={**BASE, "donor_id": str(world["donor_a_id"])}).json()
    s = str(j).lower()
    for t in ("cpf", "telefone", "email", "razao_social"):
        assert t not in s


def test_schema_valida_janela():
    with pytest.raises(ValidationError):
        LoteIn(categoria="FRUTAS", quantidade_kg=1, horas_ate_validade=5, municipio_ibge=3550308, janela_retirada_inicio_h=10, janela_retirada_fim_h=9)
