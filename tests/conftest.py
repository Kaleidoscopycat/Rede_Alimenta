import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EXPIRY_SCAN_SECONDS", "3600")  # tarefa de expiração não interfere nos testes (eles chamam expire_overdue explicitamente)

import pytest


# ====================================================================================== Fase 2 Parte 1: PostgreSQL de TESTE
# Exige TEST_DATABASE_URL apontando para um banco cujo nome termina em `_test` (o esquema é recriado!). Sem isso, os testes de banco são PULADOS (e relatados como tal).
class Clock:
    """Relógio controlável (terça-feira 10:00 America/Sao_Paulo): evita dependência do horário real nas regras de janela de coleta."""

    def __init__(self) -> None:
        self.now = dt.datetime(2026, 10, 13, 13, 0, tzinfo=dt.timezone.utc)

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now = self.now + dt.timedelta(**kw)


@pytest.fixture(scope="session")
def p2_db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida: testes de banco pulados")
    assert url.rsplit("/", 1)[-1].split("?")[0].endswith("_test"), "TEST_DATABASE_URL deve apontar para banco *_test (o esquema é recriado)"
    os.environ["DATABASE_URL"] = url
    from sqlalchemy import text
    from database.session import get_engine, reset_engine, session_scope
    from database.importers import import_all
    reset_engine()
    with get_engine().begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True, env={**os.environ, "DATABASE_URL": url})
    with session_scope() as s:
        rep = import_all(s, "smoke", with_lots=True)  # organizações REAIS + dados SIMULADOS do simulador (tag smoke)
    return rep


@pytest.fixture(scope="session")
def clock(p2_db):
    c = Clock()
    mp = pytest.MonkeyPatch()
    from api.routers import donations
    from match import lifecycle
    mp.setattr(donations, "_now", c)
    mp.setattr(lifecycle, "utcnow", c)
    yield c
    mp.undo()


@pytest.fixture(scope="session")
def client(p2_db, clock):
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c


def _mk_user(role, label, donor_id=None, org_id=None, demo=False):
    from api.auth import hash_token, new_token
    from database import models as m
    from database.session import session_scope
    tok = new_token()
    with session_scope() as s:
        u = m.User(role=role, label=label, donor_id=donor_id, organization_id=org_id, token_hash=hash_token(tok), is_demo=demo)
        s.add(u)
        s.flush()
        uid = u.id
    return uid, {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def world(client, clock):
    """Contas TÉCNICAS de teste (tokens) sobre dados do simulador (SIMULATED) e ONGs reais; nenhuma entidade de negócio é inventada."""
    import pandas as pd
    from sqlalchemy import select, func
    from database import models as m
    from database.session import session_scope
    from api.state import STATE
    from core.settings import TZ
    from match.index import OrgIndex  # noqa
    w: dict = {}
    _, w["admin"] = _mk_user("ADMIN", "teste-admin")
    sim = ROOT / "data" / "simulated" / "smoke"
    lots = pd.read_parquet(sim / "sim_lot.parquet", columns=["lot_id", "donor_id"])
    txt = pd.read_parquet(sim / "sim_lot_text.parquet", columns=["lot_id", "texto"])
    don = pd.read_parquet(sim / "sim_donor.parquet", columns=["donor_id", "municipio_ibge"])
    with session_scope() as s:
        pop = {r[0]: r[1] for r in s.execute(select(m.PublicIndicator.municipio_ibge, m.PublicIndicator.value).where(m.PublicIndicator.code == "populacao_2026"))}
        dv = s.scalar(select(m.Donor.dataset_version).limit(1))
        ext2id = {r.external_id: r.id for r in s.execute(select(m.Donor.external_id, m.Donor.id).where(m.Donor.dataset_version == dv))}
    don["pop"] = don["municipio_ibge"].map(pop).fillna(0)
    ranked = don.sort_values("pop", ascending=False)
    a, b = ranked.iloc[0]["donor_id"], ranked.iloc[1]["donor_id"]
    if a == b:
        raise AssertionError
    w["donor_a_id"], w["donor_b_id"] = ext2id[a], ext2id[b]
    w["donor_a_ext"] = a
    _, w["donor_a"] = _mk_user("DONOR", "teste-conta-doador-a", donor_id=w["donor_a_id"], demo=True)
    _, w["donor_b"] = _mk_user("DONOR", "teste-conta-doador-b", donor_id=w["donor_b_id"], demo=True)
    # textos SIMULADOS do simulador, classificados pelo próprio parser na data do relógio de teste
    today = clock().astimezone(TZ).date()
    ready, pending, noval, expired = [], [], [], []
    for r in txt.itertuples(index=False):
        raw = STATE.parser.raw(r.texto, today)
        need = raw["needs_human_confirmation"]
        if raw["blocked_expired"]:
            expired.append(r.texto)
        elif raw["days_to_expiry"] is None:
            noval.append(r.texto)
        elif raw["validity_source"] == "INFORMADA" and raw["days_to_expiry"] >= 3 and raw["unidade"] == "kg" and raw["quantidade"] and raw["quantidade"] <= 200 and not need:
            ready.append(r.texto)
        elif raw["validity_source"] == "INFORMADA" and raw["days_to_expiry"] >= 3 and raw["unidade"] in ("caixa", "unidade") and raw["quantidade"] and raw["quantidade"] <= 20:
            pending.append(r.texto)
    w["texts"] = {"ready": ready, "pending": pending, "no_validity": noval, "expired": expired}
    return w
