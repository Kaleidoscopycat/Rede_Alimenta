"""Treino e avaliação do ranker de doação (lote → ONG). TODAS as métricas são calculadas sobre dados SIMULADOS."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.dataset import BOOL_FEATURES, CAT_FEATURES, FEATURE_ORIGIN, FEATURES, NUM_FEATURES, build_pairs, temporal_split
from ml.evaluation.metrics import ORIGEM_METRICA, best_f1_threshold, classification_metrics, ranking_metrics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ml" / "artifacts" / "ranker"
SEED = 20261003
MODEL_VERSION = "ranker-1.0.0"


def make_pre(num, boo, cat, scale):
    nump = [("imp", SimpleImputer(strategy="median", add_indicator=True))] + ([("sc", StandardScaler())] if scale else [])
    return ColumnTransformer([("num", Pipeline(nump), num + boo),
                              ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32, min_frequency=20), cat)])


def make_models(num, boo, cat):
    return {
        "LR": Pipeline([("pre", make_pre(num, boo, cat, True)), ("clf", LogisticRegression(C=1.0, max_iter=300, class_weight=None))]),
        "RF": Pipeline([("pre", make_pre(num, boo, cat, False)), ("clf", RandomForestClassifier(n_estimators=120, min_samples_leaf=20, max_features="sqrt", n_jobs=-1, random_state=SEED))]),
        "HGB": Pipeline([("pre", make_pre(num, boo, cat, False)), ("clf", HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, max_leaf_nodes=48, l2_regularization=1.0, random_state=SEED))]),
    }


def baselines(df: pd.DataFrame) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(SEED)
    near = -df["dist_km"].to_numpy()
    rule = (df["elegivel_regra"].to_numpy() * 1000.0 + df["categoria_aceita_declarada"].to_numpy() * 100.0 + near)
    return {"baseline_ong_mais_proxima": near, "baseline_regra_distancia_categoria": rule, "baseline_aleatorio": rng.random(len(df))}


def score_all(d: pd.DataFrame, s: np.ndarray, boot=0) -> dict:
    x = d[["lot_id", "target"]].copy(); x["s"] = s
    return ranking_metrics(x, "s", boot=boot)


def main(tag="main"):
    t0 = time.time()
    df = temporal_split(build_pairs(tag))
    tr, va, te = (df[df.split == s].reset_index(drop=True) for s in ("train", "val", "test"))
    print({s: (len(d), d.lot_id.nunique(), round(d.target.mean(), 3)) for s, d in (("train", tr), ("val", va), ("test", te))}, flush=True)
    res = {"rotulo": ORIGEM_METRICA, "dataset_tag": tag, "dataset_version": str(df["dataset_version"].iloc[0]), "n_pares": {"train": len(tr), "val": len(va), "test": len(te)},
           "divisao": "temporal por lote (70/15/15), todos os pares do lote no mesmo conjunto",
           "limitacao_circularidade": "Rótulos gerados por simulador cujo desfecho depende de atributos latentes e estrutura definidos pela equipe; o modelo aprende o simulador, não o mundo real. Contrafactual: todos os pares candidatos têm rótulo."}
    # baselines (val e test)
    res["baselines"] = {}
    for nm, sc in baselines(va).items():
        res["baselines"][nm] = {"val": score_all(va, sc)}
    for nm, sc in baselines(te).items():
        res["baselines"][nm]["test"] = score_all(te, sc, boot=200)
    # modelos
    models = make_models(NUM_FEATURES, BOOL_FEATURES, CAT_FEATURES)
    rng = np.random.default_rng(SEED)
    fitted, val_scores = {}, {}
    for nm, m in models.items():
        sub = tr
        if nm == "RF":  # amostra de lotes (mantém lotes inteiros) por custo computacional
            lots = tr.lot_id.unique(); keep = set(rng.choice(lots, size=min(len(lots), 12000), replace=False)); sub = tr[tr.lot_id.isin(keep)]
        t1 = time.time()
        m.fit(sub[FEATURES], sub["target"])
        p = m.predict_proba(va[FEATURES])[:, 1]
        fitted[nm], val_scores[nm] = m, p
        print(nm, "fit", round(time.time() - t1, 1), "s; val MRR", round(score_all(va, p)["mrr"], 4), flush=True)
    res["modelos"] = {}
    for nm, p in val_scores.items():
        thr = best_f1_threshold(va["target"].to_numpy(), p)
        res["modelos"][nm] = {"val": {"ranking": score_all(va, p), "classificacao": classification_metrics(va["target"].to_numpy(), p, thr)}, "threshold_val": thr}
    best = max(res["modelos"], key=lambda k: res["modelos"][k]["val"]["ranking"]["mrr"])
    res["modelo_escolhido"] = best; res["criterio_escolha"] = "maior MRR na validação"
    for nm, m in fitted.items():
        pt = m.predict_proba(te[FEATURES])[:, 1]
        res["modelos"][nm]["test"] = {"ranking": score_all(te, pt, boot=200), "classificacao": classification_metrics(te["target"].to_numpy(), pt, res["modelos"][nm]["threshold_val"])}
        if nm == best:
            te["_score"] = pt
    # quebra por segmento (modelo escolhido, teste)
    seg = {}
    for col in ("categoria", "perecibilidade", "exige_refrigeracao"):
        seg[col] = {str(k): score_all(g, g["_score"].to_numpy())["mrr"] for k, g in te.groupby(col) if g.lot_id.nunique() > 30}
    res["segmentos_mrr_modelo_escolhido_teste"] = seg
    # ablações (HGB)
    abl = {}
    decl = ["frota_capacidade_declarada_kg", "capacidade_declarada_max_kg_dia", "n_categorias_aceitas_declaradas", "horario_abertura_declarado_h", "horario_fechamento_declarado_h", "n_dias_funcionamento_declarados",
            "tem_frota", "frota_refrigerada_declarada", "camara_fria_declarada", "categoria_aceita_declarada", "dia_comum_declarado", "elegivel_regra", "kg_sobre_capacidade", "kg_sobre_frota",
            "precisa_frio_sem_frio_declarado"]
    for nome, drop in (("sem_atributos_declarados_pela_ONG", decl), ("apenas_distancia_e_lote", [f for f in FEATURES if f not in {"dist_km", "rank_distancia", "tempo_deslocamento_est_h", "razao_deslocamento_validade", "quantidade_kg", "horas_ate_validade", "categoria", "perecibilidade", "exige_refrigeracao", "mesmo_municipio"}])):
        num = [c for c in NUM_FEATURES if c not in drop]; boo = [c for c in BOOL_FEATURES if c not in drop]; cat = [c for c in CAT_FEATURES if c not in drop]
        mm = make_models(num, boo, cat)["HGB"].fit(tr[num + boo + cat], tr["target"])
        abl[nome] = score_all(te, mm.predict_proba(te[num + boo + cat])[:, 1])
    res["ablacao_HGB_teste"] = abl
    # importância por permutação (modelo escolhido; amostra de validação; queda de PR-AUC pareada)
    from sklearn.metrics import average_precision_score
    m = fitted[best]; samp = va.sample(min(60000, len(va)), random_state=SEED).reset_index(drop=True)
    base_ap = average_precision_score(samp["target"], m.predict_proba(samp[FEATURES])[:, 1]); imp = {}
    for f in FEATURES:
        x = samp[FEATURES].copy(); x[f] = x[f].sample(frac=1.0, random_state=1).to_numpy()
        imp[f] = float(base_ap - average_precision_score(samp["target"], m.predict_proba(x)[:, 1]))
    res["importancia_permutacao_pr_auc"] = dict(sorted(imp.items(), key=lambda kv: -kv[1]))
    res["importancia_nota"] = "Importância reflete o simulador (SIMULATED), não causalidade no mundo real."
    # artefato
    OUT.mkdir(parents=True, exist_ok=True)
    background = {"num_median": {c: float(tr[c].median()) for c in NUM_FEATURES + BOOL_FEATURES}, "cat_mode": {c: str(tr[c].mode().iloc[0]) for c in CAT_FEATURES}}
    joblib.dump(fitted[best], OUT / "model.joblib")
    h = hashlib.sha256((OUT / "model.joblib").read_bytes()).hexdigest()
    meta = {"model_version": MODEL_VERSION, "model_name": best, "model_sha256": h, "trained_at": dt.datetime.now(dt.timezone.utc).isoformat(), "data_version_simulada": res["dataset_version"],
            "data_version_real": "pipeline-" + __import__("pipelines.common", fromlist=["x"]).PIPELINE_VERSION + "+raw_checksums:" + hashlib.sha256((ROOT / "data" / "metadata" / "raw_checksums.json").read_bytes()).hexdigest()[:12],
            "data_origin": "SIMULATED (rótulos) + PUBLIC (atributos de ONG/município)", "features": FEATURES, "feature_origin": FEATURE_ORIGIN, "threshold_val": res["modelos"][best]["threshold_val"],
            "seed": SEED, "aviso": ORIGEM_METRICA, "background": background,
            "metricas_resumo_teste": {"ranking": {k: v for k, v in res["modelos"][best]["test"]["ranking"].items() if k in ("mrr", "top1_hit_rate", "top3_hit_rate", "ndcg@3")}}}
    (OUT / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "metrics.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("escolhido", best, "tempo", round(time.time() - t0), "s", flush=True)
    for nm, v in res["baselines"].items():
        print(nm, {k: round(v["test"][k], 4) for k in ("mrr", "top1_hit_rate", "top3_hit_rate", "ndcg@3")})
    for nm, v in res["modelos"].items():
        r = v["test"]["ranking"]; c = v["test"]["classificacao"]
        print(nm, {k: round(r[k], 4) for k in ("mrr", "top1_hit_rate", "top3_hit_rate", "ndcg@3")}, "auc", round(c["roc_auc"], 4), "prauc", round(c["pr_auc"], 4), "f1", round(c["f1"], 4))
    print("ablacao", {k: round(v["mrr"], 4) for k, v in abl.items()})
    print("top imp", list(res["importancia_permutacao_pr_auc"].items())[:8])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "main")
