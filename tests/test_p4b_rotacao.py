"""Fase 4 · Etapa B — rotação de token (scripts/create_user.py --rotate). Banco de teste."""
import json
import sys
import uuid

import pytest
from sqlalchemy import select

from database import models as m
from database.session import session_scope
from scripts import create_user as cu
from tests.conftest import _mk_user


def _label():
    return "teste-rotacao-" + uuid.uuid4().hex[:8]


def _ativos(label):
    with session_scope() as s:
        return [(u.id, u.role, u.donor_id, u.organization_id, u.is_demo, u.expires_at, u.is_active) for u in s.scalars(select(m.User).where(m.User.label == label))]


def test_rotacao_troca_o_token_e_preserva_perfil_e_vinculo(client, world):
    label = _label()
    _, antigo = _mk_user("DONOR", label, donor_id=world["donor_a_id"], demo=True)
    assert client.get("/api/v1/me", headers=antigo).status_code == 200
    uid, role, tok = cu.rotate(label, 24)
    novo = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/me", headers=antigo).status_code == 401  # o token antigo morre
    r = client.get("/api/v1/me", headers=novo)
    assert r.status_code == 200 and r.json()["role"] == role == "DONOR"
    linhas = _ativos(label)
    assert len(linhas) == 2 and sum(1 for x in linhas if x[6]) == 1
    ativo = next(x for x in linhas if x[6])
    assert str(ativo[0]) == uid and ativo[2] == world["donor_a_id"] and ativo[4] is True and ativo[5] is not None  # vínculo, --demo e validade pedida


def test_rotacao_sem_validade_nao_herda_expiracao(client, world):
    label = _label()
    _, h = _mk_user("ADMIN", label)
    with session_scope() as s:
        import datetime as dt
        s.scalar(select(m.User).where(m.User.label == label)).expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    cu.rotate(label)
    assert next(x for x in _ativos(label) if x[6])[5] is None


def test_auditoria_user_rotate_sem_token(client, world):
    label = _label()
    _mk_user("ADMIN", label)
    _, _, tok = cu.rotate(label)
    with session_scope() as s:
        rows = [r for r in s.scalars(select(m.AuditLog).where(m.AuditLog.action == "user.rotate")) if (r.detail or {}).get("label") == label]
    assert len(rows) == 1 and rows[0].detail["role"] == "ADMIN" and rows[0].outcome == "OK"
    assert tok not in json.dumps(rows[0].detail) and tok not in str(rows[0].resource_id)


def test_rotulo_inexistente_e_ambiguo_nao_alteram_nada(client, world):
    with pytest.raises(cu.RotateError, match="nenhum usuário ativo"):
        cu.rotate("rotulo-que-nao-existe-" + uuid.uuid4().hex[:6])
    label = _label()
    _, h1 = _mk_user("ADMIN", label)
    _, h2 = _mk_user("ADMIN", label)
    with pytest.raises(cu.RotateError, match="ambíguo"):
        cu.rotate(label)
    assert client.get("/api/v1/me", headers=h1).status_code == 200 and client.get("/api/v1/me", headers=h2).status_code == 200
    assert len(_ativos(label)) == 2


def test_rotacao_com_rotulo_revogado_falha(client, world):
    label = _label()
    _mk_user("ADMIN", label)
    assert cu.revoke(label) == 1
    with pytest.raises(cu.RotateError):
        cu.rotate(label)


def test_validade_invalida():
    for h in (0, -1, 721):
        with pytest.raises(cu.RotateError):
            cu.rotate("qualquer", h)


def test_falha_no_meio_desfaz_tudo(client, world, monkeypatch):
    label = _label()
    _, antigo = _mk_user("ADMIN", label)

    def boom(*a, **k):
        raise RuntimeError("falha simulada na auditoria")
    monkeypatch.setattr(cu.m, "AuditLog", boom)
    with pytest.raises(RuntimeError):
        cu.rotate(label)
    assert len(_ativos(label)) == 1 and client.get("/api/v1/me", headers=antigo).status_code == 200  # transação desfeita: o token antigo segue válido


def test_cli_imprime_o_novo_token_uma_vez_e_nunca_o_antigo(client, world, monkeypatch, capsys):
    label = _label()
    _, antigo = _mk_user("ADMIN", label)
    tok_antigo = antigo["Authorization"].split(" ", 1)[1]
    monkeypatch.setattr(sys, "argv", ["create_user", "--rotate", label, "--expires-in-hours", "12"])
    cu.main()
    out = capsys.readouterr().out
    assert out.count("TOKEN=rai_") == 1 and tok_antigo not in out and "role=ADMIN" in out
    novo = out.split("TOKEN=", 1)[1].split()[0]
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {novo}"}).status_code == 200
    monkeypatch.setattr(sys, "argv", ["create_user", "--rotate", "nao-existe-" + uuid.uuid4().hex[:6]])
    with pytest.raises(SystemExit) as e:
        cu.main()
    assert "nenhum usuário ativo" in str(e.value) and "rai_" not in str(e.value)
