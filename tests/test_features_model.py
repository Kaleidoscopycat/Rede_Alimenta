import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from ml.dataset import FEATURES, FORBIDDEN, FEATURE_ORIGIN
from ml.evaluation.metrics import ranking_metrics, rank_within_lot, classification_metrics
ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml/artifacts/ranker"


def test_features_sem_vazamento():
    assert not (set(FEATURES) & FORBIDDEN)
    assert not any("latente" in f or "latent" in f or "_real" in f or "eff" in f for f in FEATURES)
    assert all(f in FEATURE_ORIGIN for f in FEATURES)


def test_metricas_ranking_calculadas_a_mao():
    df = pd.DataFrame({"lot_id": ["a"] * 3 + ["b"] * 3, "s": [3, 2, 1, 1, 2, 3], "target": [0, 1, 0, 0, 0, 1]})
    r = ranking_metrics(df, "s")
    assert abs(r["mrr"] - (0.5 + 1.0) / 2) < 1e-9
    assert r["top1_hit_rate"] == 0.5 and r["top3_hit_rate"] == 1.0
    assert abs(r["ndcg@3"] - (1 / np.log2(3) + 1.0) / 2) < 1e-9


def test_lote_sem_positivo_excluido_do_ranking():
    df = pd.DataFrame({"lot_id": ["a", "a", "b", "b"], "s": [1, 2, 1, 2], "target": [0, 0, 0, 1]})
    r = ranking_metrics(df, "s")
    assert r["n_lotes_sem_positivo"] == 1 and r["n_lotes_avaliaveis"] == 1


def test_classificacao_basica():
    m = classification_metrics(np.array([0, 1, 1, 0]), np.array([0.1, 0.9, 0.6, 0.4]), 0.5)
    assert m["precision"] == 1.0 and m["recall"] == 1.0


def test_artefato_integro_e_metadados():
    meta = json.loads((ART / "metadata.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((ART / "model.joblib").read_bytes()).hexdigest() == meta["model_sha256"]
    for k in ("model_version", "features", "feature_origin", "data_version_simulada", "data_origin", "aviso", "seed"):
        assert k in meta
    assert meta["features"] == FEATURES


def test_modelo_supera_baselines_no_teste_simulado():
    m = json.loads((ART / "metrics.json").read_text(encoding="utf-8"))
    best = m["modelos"][m["modelo_escolhido"]]["test"]["ranking"]["mrr"]
    for b in m["baselines"].values():
        assert best > b["test"]["mrr"]
    assert "SIMULADOS" in m["rotulo"]


def test_split_temporal_mantem_lote_inteiro():
    from ml.dataset import temporal_split
    ts = pd.date_range("2026-01-01", periods=10, freq="D")
    df = pd.DataFrame({"lot_id": np.repeat([f"L{i}" for i in range(10)], 3), "created_at": np.repeat(ts, 3), "target": 0})
    s = temporal_split(df)
    assert s.groupby("lot_id").split.nunique().max() == 1
    order = s.groupby("split").created_at.max()
    assert order["train"] < s[s.split == "test"].created_at.min()
