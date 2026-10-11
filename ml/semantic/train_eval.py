"""Treino e avaliação da análise semântica (seção 12). Treina SOMENTE em texto SIMULADO; avalia em simulado visto, simulado reservado (F4)
e rascunho IA provisório. MANUALLY_LABELED: ausente (reportado como tal)."""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from ml.semantic.classifier import (ARTIFACT_DIR, RulesBaseline, TextClassifier, choose_threshold, ece, extract_quantity)
from ml.semantic.validity import parse_validity

ROOT = Path(__file__).resolve().parents[2]
TAG = sys.argv[1] if len(sys.argv) > 1 else "main"


def load_sim():
    d = pd.read_parquet(ROOT / "data" / "simulated" / TAG / "sim_lot_text.parquet")
    return {s: d[d.text_split == s].reset_index(drop=True) for s in ("train", "val", "test_seen", "test_heldout")}


def load_prov():
    p = ROOT / "data" / "manual_labeled" / "PROVISORIO_rascunho_ia.csv"
    return pd.read_csv(p, sep=";") if p.exists() else None


def eval_set(df: pd.DataFrame, clf: TextClassifier, base: RulesBaseline, tau: float, nome: str) -> dict:
    indef = df[df["y_categoria"] == "INDEFINIDO"]
    extra = {}
    if len(indef):  # textos genuinamente indefinidos: o comportamento correto é pedir confirmação humana
        Pi = clf.predict(indef["texto"].tolist())
        extra = {"n_indefinido": int(len(indef)), "indefinido_sinalizado_para_revisao": float(((Pi["categoria_conf"].values < tau) | (Pi["perecibilidade_conf"].values < tau)).mean())}
    df = df[df["y_categoria"] != "INDEFINIDO"].reset_index(drop=True)
    texts = df["texto"].tolist()
    yc = df["y_categoria"].values; yp = df["y_perecibilidade"].values; yr = df["y_exige_refrigeracao"].astype(bool).values
    P = clf.predict(texts)
    B = pd.DataFrame([base.predict(t) for t in texts])
    out = {"conjunto": nome, "n": int(len(df)), **extra}
    for lab, pr in (("baseline_regras", B), ("logreg_tfidf", P)):
        c = pr["categoria"].values; p = pr["perecibilidade"].values; r = pr["refrigeracao"].values if "refrigeracao" in pr else pr["requires_refrigeration"].values
        out[lab] = {"acc_categoria": float((c == yc).mean()), "acc_perecibilidade": float((p == yp).mean()), "acc_refrigeracao": float((r == yr).mean())}
        from sklearn.metrics import f1_score
        out[lab]["f1_macro_categoria"] = float(f1_score(yc, c, average="macro"))
        out[lab]["subestima_perecibilidade"] = float(np.mean([a != b and _rk(b) < _rk(a) for a, b in zip(yp, p)]))
    conf = P["perecibilidade_conf"].values; corr = (P["perecibilidade"].values == yp)
    e, rel = ece(conf, corr)
    out["ece_perecibilidade"] = e; out["reliability_perecibilidade"] = rel
    cc = P["categoria_conf"].values; e2, _ = ece(cc, P["categoria"].values == yc)
    out["ece_categoria"] = e2
    flag = (P["perecibilidade_conf"].values < tau) | (P["categoria_conf"].values < tau)
    out["taxa_revisao_humana"] = float(flag.mean())
    out["acc_categoria_sem_revisao"] = float((P["categoria"].values == yc)[~flag].mean()) if (~flag).any() else None
    # validade
    ref = pd.to_datetime(df["reference_date"]).dt.date
    rows = [parse_validity(t, r_, c) for t, r_, c in zip(texts, ref, P["categoria"].values)]
    v = pd.DataFrame(rows)
    ytrue = df["y_dias_ate_validade"].values
    inf = df["y_validity_source"].values == "INFORMADA"
    got = v["days_to_expiry"].notna().values & (v["validity_source"].values == "INFORMADA")
    both = inf & got
    out["validade"] = {
        "n_informada_verdade": int(inf.sum()),
        "taxa_extracao": float((got & inf).sum() / max(inf.sum(), 1)),
        "exatidao_exata": float((np.abs(v["days_to_expiry"].values[both] - ytrue[both]) < 0.5).mean()) if both.any() else None,
        "mae_dias": float(np.nanmean(np.abs(v["days_to_expiry"].values[both] - ytrue[both]))) if both.any() else None,
        "falso_positivo_informada": float((got & ~inf).sum() / max((~inf).sum(), 1)),
        "alerta_inconsistencia_taxa": float(v["inconsistency_alert"].mean()),
    }
    # quantidade
    q = [extract_quantity(t) for t in texts]
    qv = np.array([x[0] if x[0] is not None else np.nan for x in q]); qu = np.array([x[1] for x in q], dtype=object)
    yq = df["y_quantidade"].values; yu = df["y_unidade"].values
    hasq = ~np.isnan(yq)
    out["quantidade"] = {"taxa_extracao": float((~np.isnan(qv))[hasq].mean()) if hasq.any() else None,
                         "acc_valor": float((np.abs(qv[hasq] - yq[hasq]) < 1e-6).mean()) if hasq.any() else None,
                         "acc_unidade": float((qu[hasq] == yu[hasq]).mean()) if hasq.any() else None}
    return out


from ml.semantic.classifier import PER_RANK  # noqa: E402


def _rk(x):
    return PER_RANK[x]


def main():
    sp = load_sim()
    tr, va = sp["train"], sp["val"]
    base = RulesBaseline()
    best = None
    sel = {}
    for C in (1.0, 10.0, 50.0):
        clf = TextClassifier(C=C).fit(tr.texto.tolist(), tr.y_categoria.tolist(), tr.y_perecibilidade.tolist(), tr.y_exige_refrigeracao.astype(bool).tolist())
        P = clf.predict(va.texto.tolist())
        acc = float((P["categoria"].values == va.y_categoria.values).mean())
        accp = float((P["perecibilidade"].values == va.y_perecibilidade.values).mean())
        sel[C] = {"acc_categoria_val": acc, "acc_perecibilidade_val": accp}
        print("C", C, sel[C], flush=True)
        if best is None or acc + accp > best[0]:
            best = (acc + accp, C, clf, P)
    _, C, clf, Pv = best
    tau, info = choose_threshold(np.minimum(Pv["perecibilidade_conf"].values, Pv["categoria_conf"].values), va.y_perecibilidade.tolist(), Pv["perecibilidade"].tolist())
    print("C escolhido", C, "tau", tau, flush=True)
    res = {"C_escolhido": C, "selecao_C": {str(k): v for k, v in sel.items()}, "tau": tau,
           "tau_info": {k: v for k, v in info.items() if k != "grid_cost"},
           "rotulo": "Métricas calculadas sobre dados SIMULADOS (textos gerados por modelo de linguagem de templates). Não representam desempenho em textos reais.",
           "avaliacoes": []}
    res["avaliacoes"].append(eval_set(sp["test_seen"], clf, base, tau, "SIMULADO_visto (famílias F1-F3, teste)"))
    res["avaliacoes"].append(eval_set(sp["test_heldout"], clf, base, tau, "SIMULADO_reservado (família F4, nunca vista no treino)"))
    prov = load_prov()
    if prov is not None:
        res["avaliacoes"].append(eval_set(prov, clf, base, tau, "RASCUNHO_IA_PROVISORIO (n pequeno; NÃO é rotulagem humana)"))
    ml_path = ROOT / "data" / "manual_labeled" / "manual_labeled_text.csv"
    if ml_path.exists():
        ml_df = pd.read_csv(ml_path, sep=";")
        res["avaliacoes"].append(eval_set(ml_df, clf, base, tau, "MANUALLY_LABELED (rotulagem humana)"))
    res["MANUALLY_LABELED"] = None if ml_path.exists() else "AUSENTE: conjunto rotulado manualmente pela equipe ainda não existe; ver data/manual_labeled/manual_labeled_text_TEMPLATE.csv"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"trained_on": "SIMULATED", "dataset_tag": TAG, "C": C, "tau": tau, "n_train": int(len(tr)), "trained_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    joblib.dump({"clf": clf, "tau": tau, "meta": meta}, ARTIFACT_DIR / "semantic_parser.joblib")
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    for a in res["avaliacoes"]:
        print(a["conjunto"], a["n"])
        for k in ("baseline_regras", "logreg_tfidf"):
            print("  ", k, {x: round(y, 3) for x, y in a[k].items()})
        print("   ece_per", round(a["ece_perecibilidade"], 3), "revisao", round(a["taxa_revisao_humana"], 3), "validade", a["validade"], "qtd", a["quantidade"])


if __name__ == "__main__":
    main()
