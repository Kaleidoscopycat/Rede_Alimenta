"""Fase 3 Parte 2 · Etapa B — migrations 0004 (RLS) e 0005 (expiração) são REVERSÍVEIS: upgrade → downgrade 0003 → upgrade, com dados. Roda por último (altera o esquema do banco de TESTE e o restaura)."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text

from database.session import get_engine, reset_engine

ROOT = Path(__file__).resolve().parents[1]


def alembic(*args):
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    reset_engine()


def sem_rls():
    with get_engine().connect() as c:
        return c.execute(text("select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = current_schema() and c.relkind in ('r','p') and not c.relrowsecurity")).scalars().all()


def contagem():
    with get_engine().connect() as c:
        return c.execute(text("select count(*) from organizations")).scalar(), c.execute(text("select count(*) from users")).scalar()


def test_upgrade_downgrade_upgrade_rls_e_expiracao(p2_db):
    antes = contagem()
    assert sem_rls() == [] and "expires_at" in {c["name"] for c in inspect(get_engine()).get_columns("users")}
    alembic("downgrade", "0003")
    try:
        assert "expires_at" not in {c["name"] for c in inspect(get_engine()).get_columns("users")}
        assert "users" in sem_rls() and "organizations" in sem_rls()  # RLS desabilitado no downgrade
        with get_engine().connect() as cn:
            assert cn.execute(text("select version_num from alembic_version")).scalar() == "0003"
        assert contagem() == antes  # nenhum dado perdido
    finally:
        alembic("upgrade", "head")
    assert sem_rls() == [] and contagem() == antes
    assert "expires_at" in {c["name"] for c in inspect(get_engine()).get_columns("users")}


def test_migration_rls_roda_sem_os_papeis_do_supabase(p2_db):
    with get_engine().connect() as c:
        assert c.execute(text("select count(*) from pg_roles where rolname in ('anon','authenticated')")).scalar() == 0  # PostgreSQL local: papéis não existem e a migration passou
