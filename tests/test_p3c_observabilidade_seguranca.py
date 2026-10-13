"""Fase 3 Parte 2 (Etapa A): observabilidade (request ID, JSON, privacidade), premissa de refeições configurável, indicador de segurança calculado só de arquivos e revogação de token."""
import json
import logging
import uuid

import pytest
from sqlalchemy import select

from core import logging_setup
from database import models as m
from database.session import session_scope


# --------------------------------------------------------------------------------- observabilidade (sem banco)
def test_request_id_validacao():
    assert logging_setup.valid_request_id("abc12345-XYZ_9.0") == "abc12345-XYZ_9.0"
    for ruim in (None, "", "curto", "x" * 65, "com espaco 123456", "inj\r\nX-Evil: 1", "a;b;c;d;e;f"):
        gerado = logging_setup.valid_request_id(ruim)
        assert logging_setup.REQUEST_ID_RE.match(gerado) and gerado != ruim


def test_json_formatter_inclui_evt_e_request_id():
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "olá %s", ("mundo",), None)
    rec.evt, rec.latency_ms = "prediction.ranker", 12.5
    rec.request_id = "rid-12345678"
    out = json.loads(logging_setup.JsonFormatter().format(rec))
    assert out["msg"] == "olá mundo" and out["evt"] == "prediction.ranker" and out["request_id"] == "rid-12345678" and out["level"] == "INFO"


# --------------------------------------------------------------------------------- premissa de refeições
def test_premissa_refeicoes_configuravel(monkeypatch):
    from core.settings import ASSUMPTIONS, ProjectAssumptions
    assert ASSUMPTIONS.kg_per_meal == 0.4 and ASSUMPTIONS.kg_to_meals(4) == pytest.approx(10)
    monkeypatch.setenv("MEAL_KG_PER_MEAL", "0.5")
    assert ProjectAssumptions().kg_to_meals(5) == pytest.approx(10)
    monkeypatch.setenv("MEAL_KG_PER_MEAL", "0")
    with pytest.raises(RuntimeError):
        ProjectAssumptions()


# --------------------------------------------------------------------------------- indicador de segurança (somente arquivos)
def _bandit(n):
    return {"results": [{"issue_severity": "HIGH"} for _ in range(n)], "metrics": {"_totals": {"loc": 100}}}


def test_seguranca_so_conta_com_antes_e_depois(tmp_path, monkeypatch):
    from api import security_reports
    monkeypatch.setenv("SECURITY_REPORTS_DIR", str(tmp_path))
    (tmp_path / "antes").mkdir()
    (tmp_path / "antes" / "bandit.json").write_text(json.dumps(_bandit(5)))
    r = security_reports.compute()
    assert r["total_mitigadas_comprovadas"] == 0 and r["fase2"]["bandit"]["comprovado"] is False
    assert any("pendente" in p for p in r["pendencias"])
    (tmp_path / "depois").mkdir()
    (tmp_path / "depois" / "bandit.json").write_text(json.dumps(_bandit(2)))
    r = security_reports.compute()
    assert r["fase2"]["bandit"]["mitigadas"] == 3 and r["total_mitigadas_comprovadas"] == 3
    assert r["fase2"]["bandit"]["antes"]["sha256_16"]


def test_seguranca_trivy_ci_pendente_sem_json(tmp_path, monkeypatch):
    from api import security_reports
    monkeypatch.setenv("SECURITY_REPORTS_DIR", str(tmp_path))
    ci = security_reports.compute()["trivy_imagem_ci"]
    assert ci["comprovado"] is False and ci["mitigadas"] is None and "estimado" in ci["situacao"]
    tri = lambda n: {"SchemaVersion": 2, "ArtifactName": "img", "Results": [{"Vulnerabilities": [{"Severity": "HIGH", "FixedVersion": "1"}] * n}]}  # noqa: E731
    for d, n in (("antes", 4), ("depois", 0)):
        (tmp_path / "ci" / d).mkdir(parents=True)
        (tmp_path / "ci" / d / "api.json").write_text(json.dumps(tri(n)))
    ci = security_reports.compute()["trivy_imagem_ci"]
    assert ci["comprovado"] and ci["high_critical_antes"] == 4 and ci["high_critical_depois"] == 0 and ci["mitigadas"] == 4


# --------------------------------------------------------------------------------- com banco
def test_request_id_na_resposta(client, world):
    rid = "teste-rid-" + uuid.uuid4().hex[:8]
    r = client.get("/api/v1/me", headers={**world["admin"], "X-Request-ID": rid})
    assert r.headers["x-request-id"] == rid
    r2 = client.get("/api/v1/me", headers={**world["admin"], "X-Request-ID": "invalido com espaco"})
    assert r2.headers["x-request-id"] != "invalido com espaco" and logging_setup.REQUEST_ID_RE.match(r2.headers["x-request-id"])


def test_log_de_requisicao_nao_vaza_token_nem_query(client, world, caplog):
    tok = world["admin"]["Authorization"].split(" ", 1)[1]
    with caplog.at_level(logging.INFO):
        client.get("/api/v1/admin/stats/overview?uf=SP", headers=world["admin"])
    texto = " ".join(r.getMessage() + json.dumps({k: str(v) for k, v in r.__dict__.items() if k in ("evt", "path")}) for r in caplog.records if r.name.startswith("api."))  # o logger "httpx" é do cliente de teste, não da API
    assert tok not in texto and "uf=SP" not in texto
    assert any(r.name == "api.request" for r in caplog.records)


def test_revogar_token_por_rotulo(client, world):
    from api.auth import hash_token, new_token
    from scripts.create_user import revoke
    tok, label = new_token(), "teste-admin-defesa-" + uuid.uuid4().hex[:6]
    with session_scope() as s:
        s.add(m.User(role="ADMIN", label=label, token_hash=hash_token(tok), is_demo=False))
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/admin/stats/overview", headers=h).status_code == 200
    assert revoke(label) == 1
    assert client.get("/api/v1/admin/stats/overview", headers=h).status_code == 401
    assert revoke(label) == 0  # idempotente
    with session_scope() as s:
        rows = list(s.scalars(select(m.AuditLog).where(m.AuditLog.action == "user.revoke")))
    assert any(r.detail.get("label") == label and r.detail.get("desativados") == 1 for r in rows)
    assert tok not in json.dumps([r.detail for r in rows])


def test_estrategias_reprodutiveis_pela_semente(client, world):
    body = {"n_lots": 4, "seed": 11, "raio_km": 60, "tempo_solver_s": 1}
    a = client.post("/api/v1/admin/stats/logistics/strategies", headers=world["admin"], json=body).json()
    b = client.post("/api/v1/admin/stats/logistics/strategies", headers=world["admin"], json=body).json()
    assert a["estrategias"] == b["estrategias"] and a["lotes"] == b["lotes"]
    for e in a["estrategias"]:
        assert e["lotes_entregues_no_prazo"] + e["lotes_nao_entregues"] == e["lotes"] == 4
