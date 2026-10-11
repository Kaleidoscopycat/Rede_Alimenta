"""Migrations, modelos e importadores (origem preservada, rastreabilidade)."""
import pandas as pd
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from database import models as m
from database.importers import _require_simulated
from database.session import session_scope
from tests.conftest import ROOT


def test_migration_head_e_tabelas(p2_db):
    from sqlalchemy import inspect
    from database.session import get_engine
    insp = inspect(get_engine())
    tabelas = set(insp.get_table_names())
    esperadas = {"donors", "donor_locations", "organizations", "organization_locations", "food_categories", "public_data_sources", "public_dataset_versions", "public_indicators",
                 "donations", "donation_items", "matches", "match_events", "ml_predictions", "audit_logs", "users", "organization_profiles", "capacity_reservations", "alembic_version"}
    assert esperadas <= tabelas
    assert {"vehicles", "routes", "route_stops"} <= tabelas, "roteirização: migration 0002 (Fase 2 Parte 2)"
    with get_engine().connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar() == "0002"


def test_organizacoes_reais_com_rastreabilidade(p2_db):
    gold = pd.read_parquet(ROOT / "data" / "gold" / "organizations.parquet")
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(m.Organization)) == len(gold)
        assert s.scalar(select(func.count()).select_from(m.Organization).where(m.Organization.data_origin != "PUBLIC")) == 0
        for col in ("source", "source_record_id", "source_url", "last_verified_at"):
            assert s.scalar(select(func.count()).select_from(m.Organization).where(getattr(m.Organization, col).is_(None))) == 0
        assert s.scalar(select(func.count()).select_from(m.Organization).where(m.Organization.platform_status != "PUBLIC_RECORD")) == 0  # nenhuma é "cliente" por constar numa fonte
        # amostra: mesmo id de origem do gold
        row = gold.iloc[0]
        o = s.scalar(select(m.Organization).where(m.Organization.ong_id == row.ong_id))
        assert o.source_record_id == str(row.native_id) and o.source == row.source_id and o.source_url.startswith("https://")
        assert s.scalar(select(func.count()).select_from(m.PublicDataSource).where(m.PublicDataSource.publication_cleared.is_(True))) == 0
        assert s.scalar(select(func.count()).select_from(m.PublicDataSource).where(m.PublicDataSource.review_status == "NEEDS_REVIEW")) >= 5


def test_simulados_importados_com_origem(p2_db):
    with session_scope() as s:
        for model in (m.Donor, m.Donation, m.DonationItem, m.OrganizationProfile, m.DonorLocation):
            assert s.scalar(select(func.count()).select_from(model).where(model.data_origin == "SIMULATED")) > 0
            assert s.scalar(select(func.count()).select_from(model).where(model.data_origin != "SIMULATED")) == 0  # nada USER_ENTERED no import
            assert s.scalar(select(func.count()).select_from(model).where(model.dataset_version.is_(None))) == 0
            assert s.scalar(select(func.count()).select_from(model).where(model.generator_version.is_(None))) == 0
        assert s.scalar(select(func.count()).select_from(m.Donation).where(m.Donation.data_origin == "USER_ENTERED")) == 0
    n_lots = len(pd.read_parquet(ROOT / "data" / "simulated" / "smoke" / "sim_lot.parquet"))
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(m.Donation).where(m.Donation.entry_channel == "SIMULATOR_IMPORT")) == n_lots


def test_importador_recusa_origem_diferente_de_simulated():
    df = pd.DataFrame({"data_origin": ["SIMULATED", "PUBLIC"], "generator_version": ["0.2.0"] * 2, "seed": [1, 1], "dataset_version": ["x"] * 2})
    with pytest.raises(RuntimeError):
        _require_simulated(df, "t")
    df2 = pd.DataFrame({"data_origin": ["SIMULATED"], "generator_version": [None], "seed": [1], "dataset_version": ["x"]})
    with pytest.raises(RuntimeError):
        _require_simulated(df2, "t")


def test_importacao_idempotente(p2_db):
    from database.importers import import_all
    with session_scope() as s:
        rep = import_all(s, "smoke", with_lots=True)
    assert rep["organizations"]["organizations"] == 0 and rep["simulated"]["donations"] == 0


def test_constraints_de_origem_no_banco(p2_db):
    """Simulado nunca pode virar USER_ENTERED nem faltar rastreabilidade (CHECK no banco)."""
    with session_scope() as s:
        mun = s.scalar(select(m.Municipality.ibge_code).limit(1))
    with pytest.raises(IntegrityError):
        with session_scope() as s:  # SIMULATED sem trilha do gerador
            s.add(m.Donor(donor_type="X_TIPO", municipio_ibge=mun, data_origin="SIMULATED"))
    with pytest.raises(IntegrityError):
        with session_scope() as s:  # USER_ENTERED com trilha de simulador
            s.add(m.Donor(donor_type="X_TIPO", municipio_ibge=mun, data_origin="USER_ENTERED", generator_version="0.2.0", dataset_version="v", seed=1))
    with pytest.raises(IntegrityError):
        with session_scope() as s:  # origem inválida
            s.add(m.Donor(donor_type="X_TIPO", municipio_ibge=mun, data_origin="INVENTADO"))


def test_localizacao_ausente_nao_vira_coordenada(p2_db):
    """Organização sem posição: lat/lon NULL e não ranqueável (o banco rejeita coordenadas parciais ou rankable sem coordenada)."""
    with session_scope() as s:
        org = s.scalar(select(m.Organization).limit(1))
        loc = s.get(m.OrganizationLocation, org.id)
        bak = (loc.lat, loc.lon, loc.location_precision, loc.rankable_by_distance)
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            loc = s.get(m.OrganizationLocation, org.id)
            loc.lat, loc.lon, loc.rankable_by_distance = None, None, True  # sem coordenada mas "ranqueável": proibido
    with session_scope() as s:
        loc = s.get(m.OrganizationLocation, org.id)
        assert (loc.lat, loc.lon, loc.location_precision, loc.rankable_by_distance) == bak
