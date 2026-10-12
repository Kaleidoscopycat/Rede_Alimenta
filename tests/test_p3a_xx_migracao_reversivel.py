"""Fase 3 Parte 1 (Etapa A) — migration 0003 (itens da doação) é REVERSÍVEL: upgrade → downgrade 0002 → upgrade, com dados já gravados.
Roda por último entre os testes p3a (altera o esquema do banco de TESTE e o restaura)."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, select, text

from database import models as m
from database.session import get_engine, reset_engine, session_scope

ROOT = Path(__file__).resolve().parents[1]
NOVAS_ITENS = {"description", "perecibilidade", "exige_refrigeracao", "validity_days", "expires_at", "validity_source", "validity_precision", "unit_weight", "unit_weight_unit",
               "weight_basis", "entry_source", "pending_fields", "parser_suggestion", "created_at", "updated_at"}
NOVAS_DOACAO = {"categories", "is_mixed_batch", "aggregated_at", "updated_at"}


def alembic(*args):
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    reset_engine()


def cols(tabela):
    return {c["name"] for c in inspect(get_engine()).get_columns(tabela)}


def test_upgrade_downgrade_upgrade_preserva_dados(p2_db, client, world, clock):
    c = client.post("/api/v1/donations/drafts", headers=world["donor_a"], json={})
    assert c.status_code == 201
    did = c.json()["id"]
    r = client.post(f"/api/v1/donations/{did}/items", headers=world["donor_a"], json={"produto": "item-tecnico-m", "categoria": "FRUTAS", "quantity": 2, "unit": "caixa", "unit_weight": 5,
                                                                                       "unit_weight_unit": "kg", "exige_refrigeracao": False})
    assert r.status_code == 201
    assert NOVAS_ITENS <= cols("donation_items") and NOVAS_DOACAO <= cols("donations")
    alembic("downgrade", "0002")
    try:
        assert not (NOVAS_ITENS & cols("donation_items")) and not (NOVAS_DOACAO & cols("donations"))
        with get_engine().connect() as cn:
            assert cn.execute(text("select version_num from alembic_version")).scalar() == "0002"
            assert cn.execute(text("select status from donations where id = :i"), {"i": did}).scalar() == "PENDING_CONFIRMATION"  # DRAFT não existe na 0002
            assert cn.execute(text("select count(*) from donation_items where donation_id = :i"), {"i": did}).scalar() == 1  # itens e dados antigos preservados
        fks = {fk["name"] for fk in inspect(get_engine()).get_foreign_keys("donation_items")}
        assert "donation_items_donation_id_fkey" in fks and "fk_ditem_donation_origin" not in fks
    finally:
        alembic("upgrade", "head")
    assert NOVAS_ITENS <= cols("donation_items") and NOVAS_DOACAO <= cols("donations")
    fks = {fk["name"] for fk in inspect(get_engine()).get_foreign_keys("donation_items")}
    assert "fk_ditem_donation_origin" in fks and "donation_items_donation_id_fkey" not in fks
    with session_scope() as s:
        d = s.get(m.Donation, did)
        assert d is not None and d.items and d.items[0].produto == "item-tecnico-m"
        # itens históricos do simulador seguem intactos (colunas novas NULAS, nada preenchido)
        hist = s.scalars(select(m.DonationItem).join(m.Donation, m.Donation.id == m.DonationItem.donation_id).where(m.Donation.entry_channel == "SIMULATOR_IMPORT").limit(50)).all()
        assert hist and all(h.entry_source is None and h.unit_weight is None and h.expires_at is None and h.pending_fields is None for h in hist)
