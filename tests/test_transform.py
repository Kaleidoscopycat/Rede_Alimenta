from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]


def test_gold_territorio_5571_municipios_unicos():
    t = pd.read_parquet(ROOT / "data/gold/territory.parquet")
    assert len(t) == 5571 and t.codigo_ibge.is_unique


def test_gold_organizacoes_chaves_e_origem():
    o = pd.read_parquet(ROOT / "data/gold/organizations.parquet")
    assert o.ong_id.is_unique and len(o) == 54590
    assert set(o.location_precision.unique()) <= {"EXACT", "MUNICIPALITY_CENTROID", "NONE"}
    assert set(o.data_origin.unique()) == {"PUBLIC"}
    assert set(o.geo_quality.unique()) <= {"OK", "REVISAR", "SUSPEITA", "NAO_APLICAVEL"}


def test_rankable_exige_coordenada_valida():
    o = pd.read_parquet(ROOT / "data/gold/organizations.parquet")
    r = o[o.rankable_by_distance]
    assert r.lat.notna().all() and r.lon.notna().all()
    assert r.lat.between(-34, 6).all() and r.lon.between(-75, -28).all()


def test_sem_pessoa_fisica_nem_documento_em_gold():
    o = pd.read_parquet(ROOT / "data/gold/organizations.parquet")
    proibidas = {"cpf", "nome_responsavel", "telefone", "email", "cnpj", "razao_social", "endereco"}
    assert not (proibidas & {c.lower() for c in o.columns})
