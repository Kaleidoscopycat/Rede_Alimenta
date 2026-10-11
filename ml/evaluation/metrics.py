"""Métricas de ranking (principais) e de classificação. TODA métrica calculada sobre dados SIMULADOS deve ser rotulada como tal
(`ORIGEM_METRICA`); nunca é desempenho no mundo real.

Ranking por lote: relevância binária = target (aceitou ∧ coletou dentro da validade). Lotes sem nenhum par positivo não são
avaliáveis em hit-rate/MRR/NDCG (contados em `n_lotes_sem_positivo`). Empates de score: desempate ALEATÓRIO com seed fixa (documentado).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)

ORIGEM_METRICA = "calculada sobre dados SIMULADOS (não representa desempenho no mundo real)"


def rank_within_lot(df: pd.DataFrame, score: str, lot: str = "lot_id", seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    tb = rng.random(len(df))
    order = np.lexsort((tb, -df[score].to_numpy(dtype=float), df[lot].to_numpy()))
    ranks = np.empty(len(df), dtype=np.int64)
    lots_sorted = df[lot].to_numpy()[order]
    start = np.r_[True, lots_sorted[1:] != lots_sorted[:-1]]
    idx = np.arange(len(df))
    grp_start = np.maximum.accumulate(np.where(start, idx, 0))
    ranks[order] = idx - grp_start + 1
    return ranks


def per_lot_metrics(df: pd.DataFrame, score: str, lot: str = "lot_id", target: str = "target", ks=(1, 3, 5), seed: int = 7) -> pd.DataFrame:
    r = rank_within_lot(df, score, lot, seed)
    t = df[target].to_numpy().astype(int)
    d = pd.DataFrame({"lot": df[lot].to_numpy(), "rank": r, "t": t})
    pos = d[d.t == 1]
    first = pos.groupby("lot")["rank"].min().rename("first_rank")
    npos = pos.groupby("lot").size().rename("n_pos")
    out = pd.concat([first, npos], axis=1)
    out["rr"] = 1.0 / out["first_rank"]
    for k in ks:
        out[f"hit{k}"] = (out["first_rank"] <= k).astype(float)
        sel = pos[pos["rank"] <= k]
        dcg = (1.0 / np.log2(sel["rank"] + 1)).groupby(sel["lot"]).sum().reindex(out.index).fillna(0.0)
        idcg = out["n_pos"].map(lambda n: float(np.sum(1.0 / np.log2(np.arange(1, min(int(n), k) + 1) + 1))))
        out[f"ndcg{k}"] = dcg / idcg
    return out


def ranking_metrics(df: pd.DataFrame, score: str, lot: str = "lot_id", target: str = "target", ks=(1, 3, 5), seed: int = 7, boot: int = 0) -> dict:
    pl = per_lot_metrics(df, score, lot, target, ks, seed)
    n_all = df[lot].nunique()
    res = {"n_lotes": int(n_all), "n_lotes_avaliaveis": int(len(pl)), "n_lotes_sem_positivo": int(n_all - len(pl)),
           "mrr": float(pl["rr"].mean()), **{f"top{k}_hit_rate": float(pl[f"hit{k}"].mean()) for k in ks}, **{f"ndcg@{k}": float(pl[f"ndcg{k}"].mean()) for k in ks},
           "origem_metrica": ORIGEM_METRICA}
    if boot:
        rng = np.random.default_rng(seed + 1)
        arr = {c: pl[c].to_numpy() for c in ["rr", *[f"hit{k}" for k in ks], *[f"ndcg{k}" for k in ks]]}
        n = len(pl)
        ci = {}
        samples = rng.integers(0, n, size=(boot, n))
        for c, v in arr.items():
            m = v[samples].mean(axis=1)
            ci[c] = [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]
        res["ic95_bootstrap_por_lote"] = {("mrr" if c == "rr" else c.replace("hit", "top").replace("ndcg", "ndcg@") + ("_hit_rate" if c.startswith("hit") else "")): v for c, v in ci.items()}
    return res


def classification_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    y = np.asarray(y).astype(int); pred = (np.asarray(p) >= threshold).astype(int)
    cm = confusion_matrix(y, pred, labels=[0, 1])
    return {"threshold": float(threshold), "precision": float(precision_score(y, pred, zero_division=0)), "recall": float(recall_score(y, pred, zero_division=0)),
            "f1": float(f1_score(y, pred, zero_division=0)), "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else None,
            "pr_auc": float(average_precision_score(y, p)), "brier": float(brier_score_loss(y, np.clip(p, 0, 1))),
            "matriz_confusao": {"tn": int(cm[0, 0]), "fp": int(cm[0, 1]), "fn": int(cm[1, 0]), "tp": int(cm[1, 1])},
            "taxa_positivos": float(y.mean()), "origem_metrica": ORIGEM_METRICA}


def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    ts = np.unique(np.quantile(p, np.linspace(0.01, 0.99, 197)))
    f = [f1_score(y, (p >= t).astype(int), zero_division=0) for t in ts]
    return float(ts[int(np.argmax(f))])
