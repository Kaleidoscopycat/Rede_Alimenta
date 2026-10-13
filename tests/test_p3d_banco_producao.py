"""Fase 3 Parte 2 · Etapa B (com banco de teste) — expiração opcional de token, limitador de autenticação em production e RLS em todas as tabelas."""
import datetime as dt

from sqlalchemy import select, text

from database import models as m
from database.session import get_engine, session_scope
from tests.conftest import _mk_user


def _expira(label, delta):
    uid, h = _mk_user("ADMIN", label)
    with session_scope() as s:
        s.get(m.User, uid).expires_at = dt.datetime.now(dt.timezone.utc) + delta
    return h


def test_token_expirado_e_recusado_e_o_futuro_vale(client):
    assert client.get("/api/v1/me", headers=_expira("teste-exp-vencido", dt.timedelta(seconds=-5))).status_code == 401
    ok = client.get("/api/v1/me", headers=_expira("teste-exp-futuro", dt.timedelta(hours=1)))
    assert ok.status_code == 200 and ok.json()["role"] == "ADMIN"


def test_token_expirado_resposta_generica_e_auditoria_com_motivo(client):
    h = _expira("teste-exp-generico", dt.timedelta(seconds=-5))
    r = client.get("/api/v1/me", headers=h)
    desconhecido = client.get("/api/v1/me", headers={"Authorization": "Bearer rai_desconhecido_de_teste_0000"})
    assert r.status_code == desconhecido.status_code == 401 and r.json() == desconhecido.json() == {"detail": "credenciais inválidas"}  # não revela se o token existe/expirou
    with session_scope() as s:
        motivos = [row.detail.get("motivo") for row in s.scalars(select(m.AuditLog).where(m.AuditLog.action == "auth.invalid_token").order_by(m.AuditLog.id.desc()).limit(5)) if row.detail]
    assert "token expirado" in motivos


def test_sem_expiracao_nada_muda(client, world):
    assert client.get("/api/v1/me", headers=world["admin"]).status_code == 200


def test_limitador_em_production_devolve_429_e_audita(client, world, monkeypatch):
    import api.auth as auth
    from core.hardening import AuthFailureLimiter
    monkeypatch.setattr(auth, "IS_PRODUCTION", True)
    monkeypatch.setattr(auth, "AUTH_LIMITER", AuthFailureLimiter(max_failures=3, window_s=60))
    ruim = {"Authorization": "Bearer rai_token_invalido_de_teste_1"}
    assert [client.get("/api/v1/me", headers=ruim).status_code for _ in range(3)] == [401, 401, 401]
    r = client.get("/api/v1/me", headers=ruim)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/api/v1/me", headers=world["admin"]).status_code == 429  # o IP está bloqueado para qualquer token enquanto durar a janela
    with session_scope() as s:
        assert s.scalar(select(m.AuditLog).where(m.AuditLog.action == "auth.rate_limited").limit(1)) is not None


def test_limitador_desligado_fora_de_production(client, world):
    ruim = {"Authorization": "Bearer rai_token_invalido_de_teste_2"}
    assert {client.get("/api/v1/me", headers=ruim).status_code for _ in range(30)} == {401}
    assert client.get("/api/v1/me", headers=world["admin"]).status_code == 200


def test_rls_em_todas_as_tabelas(p2_db):
    """Falha se alguma tabela do schema (inclusive criada por migration futura) ficar sem RLS."""
    with get_engine().connect() as c:
        sem = c.execute(text("select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = current_schema() and c.relkind in ('r','p') and not c.relrowsecurity")).scalars().all()
    assert sem == [], f"tabelas sem RLS: {sem}"


def test_api_continua_lendo_com_rls_ligado(client, world):
    """A API conecta como dono das tabelas (ignora RLS, sem FORCE): nada quebra."""
    assert client.get("/api/v1/organizations?limit=1", headers=world["admin"]).status_code == 200


def test_coluna_expires_at_existe_e_e_opcional(p2_db):
    with get_engine().connect() as c:
        col = c.execute(text("select is_nullable from information_schema.columns where table_name='users' and column_name='expires_at'")).scalar()
    assert col == "YES"
