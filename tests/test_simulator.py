import tempfile
from pathlib import Path
import pandas as pd
import pytest
from simulation import generator

OBRIG = {"data_origin", "generator_version", "seed", "dataset_version"}
PROIBIDAS = {"cpf", "nome", "telefone", "email", "religiao", "restricao_religiosa", "aceita_alergenicos"}


@pytest.fixture(scope="module")
def runs():
    tmp = Path(tempfile.mkdtemp())
    generator.run(seed=11, n_lots=400, n_donors=120, tag="a", out_root=tmp)
    generator.run(seed=11, n_lots=400, n_donors=120, tag="b", out_root=tmp)
    generator.run(seed=12, n_lots=400, n_donors=120, tag="c", out_root=tmp)
    return tmp


def test_reprodutivel_por_seed(runs):
    a = pd.read_parquet(runs / "a/sim_pair_outcome.parquet"); b = pd.read_parquet(runs / "b/sim_pair_outcome.parquet"); c = pd.read_parquet(runs / "c/sim_pair_outcome.parquet")
    cols = ["lot_id", "ong_id", "dist_km", "target", "resposta"]
    pd.testing.assert_frame_equal(a[cols].reset_index(drop=True), b[cols].reset_index(drop=True))
    assert len(a) != len(c) or not a["target"].equals(c["target"])


def test_campos_obrigatorios_e_origem(runs):
    for f in runs.glob("a/sim_*.parquet"):
        d = pd.read_parquet(f)
        if f.stem == "sim_oracle_check":
            continue
        assert OBRIG <= set(d.columns), f.name
        assert set(d.data_origin.unique()) == {"SIMULATED"}, f.name


def test_sem_campos_proibidos(runs):
    for f in runs.glob("a/sim_*.parquet"):
        assert not (PROIBIDAS & {c.lower() for c in pd.read_parquet(f).columns}), f.name


def test_desfecho_nao_deterministico_e_ongs_reais(runs):
    p = pd.read_parquet(runs / "a/sim_pair_outcome.parquet")
    assert 0.02 < p.target.mean() < 0.9
    assert (p[p.elegivel_regra].target == 0).any() and (p[p.elegivel_regra].target == 1).any()  # elegível não implica sucesso
    org = pd.read_parquet(Path(__file__).resolve().parents[1] / "data/gold/organizations.parquet")
    assert set(p.ong_id) <= set(org.ong_id)
