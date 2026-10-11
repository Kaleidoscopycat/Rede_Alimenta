"""Tipo, perecibilidade e refrigeração a partir do texto livre do lote.
Degrau 1: BASELINE por regras/dicionário (palavras-chave da taxonomia). Degrau 2: TF-IDF de n-gramas de caracteres + LogisticRegression.
Degrau 3 (modelo em português do Hugging Face): NÃO implementado — exige superar o degrau 2 no conjunto MANUALLY_LABELED (ainda inexistente) e o
domínio huggingface.co está bloqueado neste ambiente; ver docs. A IA estrutura e sinaliza; não declara alimento próprio/impróprio."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from simulation.params import TAXONOMY_FILE
from .validity import parse_validity, strip

TAX = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))["categories"]
CATS = list(TAX)
PERECIB = ["NAO_PERECIVEL", "PERECIVEL_BAIXO_RISCO", "PERECIVEL_REFRIGERADO_CONGELADO", "PRONTO_ALTO_RISCO"]  # ordem de perecibilidade crescente
PER_RANK = {p: i for i, p in enumerate(PERECIB)}
CAT_PER = {c: TAX[c]["perecibilidade"] for c in CATS}
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "semantic"

# palavras-chave genéricas por categoria (dicionário do baseline; independente da lista de frases vagas do gerador)
GENERIC_KW = {
    "PANIFICADOS": ["padaria", "pao", "paes", "bolo", "rosca", "broa", "salgado"], "HORT_FOLHOSAS": ["verdura", "folha", "hortalica"],
    "HORT_RAIZES": ["legume", "raiz", "tuberculo"], "HORT_FRUTOS": ["hortifruti"], "FRUTAS": ["fruta"], "CARNES_PESCADOS": ["carne", "peixe", "embutido", "proteina"],
    "LATICINIOS_OVOS": ["laticinio", "lacteo", "ovo"], "REFEICOES_PRONTAS": ["marmit", "quentinha", "refeicao", "refeicoes", "comida pronta", "almoco", "prato"],
    "GRAOS_CEREAIS": ["grao", "cereal", "nao perecivel", "farinha"], "INDUSTRIALIZADOS": ["industrializ", "enlatad", "mercearia", "conserva"], "BEBIDAS": ["bebida", "liquido"],
}
COLD_CUES = re.compile(r"refriger|gelad|congel|camara fria|\b[45]\s*(?:c|graus|°c)\b|freezer|resfriad|-\s?18|\b4\s?°")
AMBIENT_CUES = re.compile(r"temperatura ambiente|temp\. ambiente|temp ambiente|local seco")
UNIT_PAT = [("kg", r"kg|quilos?|kilos?"), ("g", r"g|gramas?"), ("litro", r"litros?|lt|l"), ("caixa", r"caixas?|cx|cxs"), ("pacote", r"pacotes?|pct|pcts"),
            ("unidade", r"unidades?|un|und|unid|macos?|ma[cç]os?"), ("duzia", r"duzias?|dz"), ("bandeja", r"bandejas?|bdj|bdjs")]
WORD_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3}


def extract_quantity(text: str) -> tuple[float | None, str | None]:
    s = strip(text)
    for u, pat in UNIT_PAT:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:" + pat + r")\b", s)
        if m:
            return float(m.group(1).replace(",", ".")), u
    m = re.search(r"\b(um|uma|dois|duas|tres)\s+(?:" + "|".join(p for _, p in UNIT_PAT[2:]) + r")\b", s)
    if m:
        u = next(u for u, p in UNIT_PAT if re.fullmatch(p, re.search(r"\b(?:" + "|".join(p for _, p in UNIT_PAT[2:]) + r")\b", s[m.start(1) + len(m.group(1)):]).group(0)))
        return float(WORD_NUM[m.group(1)]), u
    return None, None


class RulesBaseline:
    """Dicionário de nomes de produto da taxonomia (+ palavras-chave genéricas). Sem treino."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str]] = []
        for c, cv in TAX.items():
            for p in cv["products"]:
                self.entries.append((strip(p["name"]), c))
        self.entries.sort(key=lambda x: -len(x[0]))

    def predict_category(self, text: str) -> tuple[str, float]:
        s = strip(text)
        for name, c in self.entries:
            if re.search(r"\b" + re.escape(name), s):
                return c, 0.9
        toks = [t for t in re.findall(r"[a-z]{4,}", s)]
        best, score = None, 0
        for name, c in self.entries:
            for w in name.split():
                if len(w) >= 4 and any(t.startswith(w[:5]) or (len(t) >= 4 and w.startswith(t[:5])) for t in toks):
                    if len(w) > score:
                        best, score = c, len(w)
        if best:
            return best, 0.6
        for c, kws in GENERIC_KW.items():
            if any(k in s for k in kws):
                return c, 0.4
        return "INDUSTRIALIZADOS", 0.0  # sem pista: classe mais ampla, confiança 0 => confirmação humana

    def predict_refrigeration(self, text: str, cat: str) -> bool:
        s = strip(text)
        if COLD_CUES.search(s):
            return True
        if AMBIENT_CUES.search(s):
            return False
        return TAX[cat]["p_refrigeracao"] >= 0.5

    def predict(self, text: str) -> dict:
        c, conf = self.predict_category(text)
        return {"categoria": c, "categoria_conf": conf, "perecibilidade": CAT_PER[c], "requires_refrigeration": self.predict_refrigeration(text, c)}


class TextClassifier:
    """TF-IDF char n-grams + LogisticRegression (3 cabeças: categoria, perecibilidade, refrigeração)."""

    def __init__(self, C: float = 10.0):
        self.C = C
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True, lowercase=True, strip_accents="unicode", max_features=250_000)
        self.heads: dict[str, LogisticRegression] = {}
        self.meta: dict[str, Any] = {}

    def fit(self, texts: list[str], y_cat: list[str], y_per: list[str], y_ref: list[bool]) -> "TextClassifier":
        X = self.vec.fit_transform(texts)
        for name, y in (("categoria", y_cat), ("perecibilidade", y_per), ("refrigeracao", [int(v) for v in y_ref])):
            self.heads[name] = LogisticRegression(C=self.C, max_iter=400, n_jobs=2).fit(X, y)
        return self

    def predict_proba(self, texts: list[str]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        X = self.vec.transform(texts)
        return {k: (h.classes_, h.predict_proba(X)) for k, h in self.heads.items()}

    def predict(self, texts: list[str]) -> pd.DataFrame:
        pp = self.predict_proba(texts)
        out = {}
        for k, (cls, P) in pp.items():
            out[k] = cls[P.argmax(1)]
            out[f"{k}_conf"] = P.max(1)
            if k == "categoria":
                top2 = np.sort(P, axis=1)[:, -2]
                out["categoria_2a_prob"] = top2
        out["refrigeracao"] = out["refrigeracao"].astype(bool)
        return pd.DataFrame(out)


def ordinal_cost(true: str, pred: str, c_under: float = 3.0, c_over: float = 1.0) -> float:
    d = PER_RANK[pred] - PER_RANK[true]
    return 0.0 if d == 0 else (c_under if d < 0 else c_over) * abs(d)  # subestimar perecibilidade é mais grave


def choose_threshold(conf: np.ndarray, true_per: list[str], pred_per: list[str], review_cost: float = 0.3, c_under: float = 3.0, c_over: float = 1.0
                     ) -> tuple[float, dict]:
    """Escolhe τ (no conjunto SIMULADO de validação) que minimiza: custo de revisão humana (conf<τ) + custo de erro de perecibilidade não sinalizado."""
    costs = np.array([ordinal_cost(t, p, c_under, c_over) for t, p in zip(true_per, pred_per)])
    grid = np.round(np.arange(0.30, 1.0001, 0.01), 2)
    tab = {}
    for t in grid:
        flag = conf < t
        tab[float(t)] = float((review_cost * flag + costs * (~flag)).mean())
    best = min(tab, key=tab.get)
    return best, {"grid_cost": tab, "review_cost": review_cost, "c_under": c_under, "c_over": c_over, "best_tau": best, "best_cost": tab[best],
                  "cost_no_review": float(costs.mean()), "cost_review_all": review_cost}


def ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> tuple[float, list]:
    edges = np.linspace(0, 1, bins + 1); tot = 0.0; rel = []
    for i in range(bins):
        m = (conf > edges[i]) & (conf <= edges[i + 1]) if i else (conf >= edges[i]) & (conf <= edges[i + 1])
        if m.any():
            tot += m.mean() * abs(correct[m].mean() - conf[m].mean())
            rel.append({"bin": f"{edges[i]:.1f}-{edges[i+1]:.1f}", "n": int(m.sum()), "conf_media": float(conf[m].mean()), "acuracia": float(correct[m].mean())})
    return float(tot), rel


class SemanticParser:
    """Orquestra: classificador (TF-IDF+LR) + parser de validade + quantidade + regras determinísticas. Saída para o modelo de match."""

    def __init__(self, clf: TextClassifier, tau: float, meta: dict):
        self.clf, self.tau, self.meta = clf, tau, meta

    @classmethod
    def load(cls, path: Path | None = None) -> "SemanticParser":
        d = joblib.load((path or ARTIFACT_DIR) / "semantic_parser.joblib")
        return cls(d["clf"], d["tau"], d["meta"])

    def parse(self, text: str, ref_date: dt.date | None = None) -> dict:
        ref_date = ref_date or dt.date.today()
        p = self.clf.predict([text]).iloc[0]
        cat = str(p["categoria"])
        v = parse_validity(text, ref_date, cat)
        q, u = extract_quantity(text)
        confirm = []
        if p["categoria_conf"] < self.tau:
            confirm.append("categoria")
        if p["perecibilidade_conf"] < self.tau:
            confirm.append("perecibilidade")
        if p["refrigeracao_conf"] < self.tau:
            confirm.append("refrigeracao")
        if v["validity_source"] != "INFORMADA" or v["validity_confidence"] < 0.7 or "ambigua" in v["flags"] or v["inconsistency_alert"]:
            confirm.append("validade")
        if q is None or u is None:
            confirm.append("quantidade")
        if p["categoria_2a_prob"] > 0.3:
            confirm.append("possivel_duas_categorias")
        return {"categoria": cat, "categoria_conf": float(p["categoria_conf"]), "perecibilidade": str(p["perecibilidade"]), "perecibilidade_conf": float(p["perecibilidade_conf"]),
                "requires_refrigeration": bool(p["refrigeracao"]), "refrigeracao_conf": float(p["refrigeracao_conf"]),
                "days_to_expiry": v["days_to_expiry"], "validity_source": v["validity_source"], "validity_confidence": v["validity_confidence"], "validity_flags": v["flags"],
                "blocked_expired": v["blocked_expired"], "inconsistency_alert": v["inconsistency_alert"], "quantidade": q, "unidade": u,
                "parse_confidence": float(min(p["categoria_conf"], p["perecibilidade_conf"], p["refrigeracao_conf"], v["validity_confidence"] if v["validity_source"] == "INFORMADA" else 0.4)),
                "needs_human_confirmation": confirm, "data_origin_training": "SIMULATED"}
