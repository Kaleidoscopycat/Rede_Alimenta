"""Robustez: ≥5 seeds, cenários alternativos e teste de misspecificação (treina em A, avalia em B). MÉTRICAS SIMULADAS.

Saída: ml/artifacts/ranker/robustness.json"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline

from ml.dataset import BOOL_FEATURES, CAT_FEATURES, FEATURES, NUM_FEATURES, build_pairs, temporal_split
from ml.evaluation.metrics import ORIGEM_METRICA, ranking_metrics
from ml.training.train import baselines, make_pre

ROOT = Path(__file__).resolve().parents[2]
SEEDS = [f"rb_s{i}" for i in range(1, 6)]
CEN = ["sc_acc_baixa", "sc_acc_alta", "sc_hf_baixo", "sc_decl_fiel", "sc_decl_otimista"]


def fit(tr):
    m = Pipeline([("pre", make_pre(NUM_FEATURES, BOOL_FEATURES, CAT_FEATURES, False)),
                  ("clf", HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=32, l2_regularization=1.0, random_state=1))])
    return m.fit(tr[FEATURES], tr["target"])


def sc(d, s):
    x = d[["lot_id", "target"]].copy(); x["s"] = s
    r = ranking_metrics(x, "s")
    return {k: r[k] for k in ("mrr", "top1_hit_rate", "top3_hit_rate", "ndcg@3", "n_lotes_avaliaveis")}


def main():
    data, models, out = {}, {}, {"rotulo": ORIGEM_METRICA, "por_tag": {}, "misspecificacao_MRR": {}}
    for t in SEEDS + CEN:
        df = temporal_split(build_pairs(t))
        tr, te = df[df.split == "train"], df[df.split == "test"].reset_index(drop=True)
        data[t] = te; models[t] = fit(tr)
        b = baselines(te)
        out["por_tag"][t] = {"taxa_target": float(df.target.mean()), "modelo_HGB": sc(te, models[t].predict_proba(te[FEATURES])[:, 1]),
                             "baseline_ong_mais_proxima": sc(te, b["baseline_ong_mais_proxima"]), "baseline_regra_distancia_categoria": sc(te, b["baseline_regra_distancia_categoria"]),
                             "baseline_aleatorio": sc(te, b["baseline_aleatorio"])}
        print(t, {k: round(v["mrr"], 3) for k, v in out["por_tag"][t].items() if isinstance(v, dict)}, flush=True)
    m = np.array([out["por_tag"][t]["modelo_HGB"]["mrr"] for t in SEEDS]); r = np.array([out["por_tag"][t]["baseline_regra_distancia_categoria"]["mrr"] for t in SEEDS])
    out["seeds"] = {"mrr_modelo_media": float(m.mean()), "mrr_modelo_dp": float(m.std(ddof=1)), "mrr_regra_media": float(r.mean()), "mrr_regra_dp": float(r.std(ddof=1)),
                    "ganho_sobre_regra_min": float((m - r).min()), "modelo_vence_regra_em_todas": bool(((m - r) > 0).all())}
    for a in ["rb_s1"]:
        out["misspecificacao_MRR"][f"treino={a}"] = {t: sc(data[t], models[a].predict_proba(data[t][FEATURES])[:, 1])["mrr"] for t in SEEDS[1:] + CEN}
    out["misspecificacao_nota"] = "Modelo treinado no cenário-base (rb_s1) e avaliado em cenários com parâmetros do simulador diferentes: mede dependência das premissas do gerador."
    (ROOT / "ml/artifacts/ranker/robustness.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out["seeds"]); print(out["misspecificacao_MRR"])


if __name__ == "__main__":
    main()
