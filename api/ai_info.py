"""Painel de IA: métricas REAIS lidas dos artefatos versionados (ml/artifacts), com os NOMES REAIS das métricas e o rótulo de origem dos dados.
Nada é calculado nem estimado aqui: tudo vem de ml/artifacts/ranker/{metadata,metrics,robustness}.json e ml/artifacts/semantic/metrics.json (gerados na Fase 1)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROTULO = "calculada sobre dados SIMULADOS (não representa desempenho no mundo real)"

# nomes reais (como em docs/MODEL_REPORT.md e GET /model/info) → explicação em linguagem simples
GLOSSARIO = {
    "mrr": "MRR (Mean Reciprocal Rank): olha em que posição do ranking ficou a primeira ONG que realmente aceitaria e coletaria; 1,0 = sempre em 1º lugar. Não é acurácia.",
    "top1_hit_rate": "Top-1: em quantos lotes a ONG em 1º lugar era uma das que aceitariam e coletariam dentro da validade (no simulador).",
    "top3_hit_rate": "Top-3: em quantos lotes pelo menos uma das 3 primeiras ONGs era adequada (no simulador).",
    "ndcg@3": "NDCG@3: nota de qualidade da ordem das 3 primeiras ONGs (1,0 = ordem ideal).",
    "roc_auc": "ROC-AUC: capacidade de separar pares adequados de inadequados (0,5 = acaso; 1,0 = perfeito).",
    "pr_auc": "PR-AUC: equilíbrio entre acertar os pares adequados e não errar os inadequados; deve ser lida contra a taxa de positivos.",
    "f1": "F1: média entre precisão e revocação no limiar escolhido na validação simulada.",
    "acc_categoria": "Acurácia da categoria: % de textos de doação em que o parser acertou a categoria do alimento (texto SIMULADO).",
    "acc_perecibilidade": "Acurácia da perecibilidade: % de acertos da classe de perecibilidade (texto SIMULADO).",
    "acc_refrigeracao": "Acurácia da refrigeração: % de acertos de 'exige refrigeração' (texto SIMULADO).",
}


def art_dir() -> Path:
    return Path(os.environ.get("ML_ARTIFACTS_DIR", str(ROOT / "ml" / "artifacts")))


def _json(p: Path) -> Any | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rk(x: dict | None) -> dict[str, Any]:
    r = (x or {}).get("ranking", x or {})
    return {"mrr": r.get("mrr"), "top1_hit_rate": r.get("top1_hit_rate"), "top3_hit_rate": r.get("top3_hit_rate"), "ndcg@3": r.get("ndcg@3")}


def ranker_block() -> dict[str, Any]:
    d = art_dir() / "ranker"
    meta, met, rob = _json(d / "metadata.json"), _json(d / "metrics.json"), _json(d / "robustness.json")
    if not (meta and met):
        return {"disponivel": False, "motivo": "artefatos do ranker ausentes", "rotulo": ROTULO}
    escolhido = met.get("modelo_escolhido")
    tabela: list[dict[str, Any]] = []
    nomes = {"baseline_aleatorio": "Baseline: aleatório", "baseline_ong_mais_proxima": "Baseline: ONG mais próxima", "baseline_regra_distancia_categoria": "Baseline: regra (elegível, categoria, distância)"}
    for k, label in nomes.items():
        t = (met.get("baselines", {}).get(k) or {}).get("test")
        if t:
            tabela.append({"modelo": label, "tipo": "baseline", **_rk(t), "escolhido": False})
    mlabel = {"LR": "Regressão logística", "RF": "Random Forest", "HGB": "HistGradientBoosting"}
    for k, label in mlabel.items():
        t = (met.get("modelos", {}).get(k) or {}).get("test")
        if t:
            tabela.append({"modelo": label, "tipo": "modelo", **_rk(t), "escolhido": k == escolhido})
    cls = ((met.get("modelos", {}).get(escolhido) or {}).get("test") or {}).get("classificacao") or {}
    ic = (((met.get("modelos", {}).get(escolhido) or {}).get("test") or {}).get("ranking") or {}).get("ic95_bootstrap_por_lote")
    imp = (rob or {}).get("importancia_permutacao_pr_auc") or {}
    top_imp = sorted(imp.items(), key=lambda kv: -kv[1])[:15]
    return {"disponivel": True, "rotulo": ROTULO, "versao": meta.get("model_version"), "modelo": meta.get("model_name"), "treinado_em": meta.get("trained_at"), "sha256": meta.get("model_sha256"),
            "limiar_decisao_validacao": meta.get("threshold_val"), "seed": meta.get("seed"),
            "datasets": {"simulado": meta.get("data_version_simulada"), "real": meta.get("data_version_real"), "origem": meta.get("data_origin"), "n_pares": met.get("n_pares"),
                         "divisao": met.get("divisao")},
            "tabela_comparacao": tabela, "ic95_mrr_modelo_escolhido": (ic or {}).get("mrr") if ic else None,
            "classificacao_modelo_escolhido": {k: cls.get(k) for k in ("roc_auc", "pr_auc", "f1", "precision", "recall", "brier", "threshold")},
            "importancia_permutacao_pr_auc": [{"atributo": k, "queda_pr_auc": round(v, 5)} for k, v in top_imp], "importancia_nota": (rob or {}).get("importancia_nota"),
            "ablacoes_mrr": {k: v.get("mrr") for k, v in (met.get("ablacao_HGB_teste") or {}).items()},
            "robustez_seeds": (rob or {}).get("seeds"), "limitacao_circularidade": met.get("limitacao_circularidade")}


def parser_block() -> dict[str, Any]:
    s = _json(art_dir() / "semantic" / "metrics.json")
    if not s:
        return {"disponivel": False, "motivo": "artefatos do parser ausentes", "rotulo": ROTULO}
    rows = []
    for a in s.get("avaliacoes", []):
        lr = a.get("logreg_tfidf") or {}
        base = a.get("baseline_regras") or {}
        rows.append({"conjunto": a.get("conjunto"), "n": a.get("n"), "acc_categoria": lr.get("acc_categoria"), "acc_perecibilidade": lr.get("acc_perecibilidade"),
                     "acc_refrigeracao": lr.get("acc_refrigeracao"), "baseline_acc_categoria": base.get("acc_categoria"), "baseline_acc_perecibilidade": base.get("acc_perecibilidade"),
                     "baseline_acc_refrigeracao": base.get("acc_refrigeracao"), "taxa_revisao_humana": a.get("taxa_revisao_humana")})
    return {"disponivel": True, "rotulo": s.get("rotulo") or ROTULO, "limiar_confianca_tau": s.get("tau"), "avaliacoes": rows, "manually_labeled": s.get("MANUALLY_LABELED"),
            "manually_labeled_existe": False if str(s.get("MANUALLY_LABELED", "")).startswith("AUSENTE") else True}


def limitations(mixed: dict[str, Any]) -> list[dict[str, str]]:
    parcela = mixed.get("parcela")
    misto = ("O ranker foi treinado e avaliado SOMENTE com lotes SIMULADOS de UMA categoria; em lote misto (várias categorias) o desempenho é DESCONHECIDO. "
             + (f"Parcela de lotes mistos entre as doações cadastradas pela plataforma: {parcela * 100:.1f}% ({mixed['n_mistos']} de {mixed['n_total']})." if parcela is not None else
                "Nenhuma doação cadastrada pela plataforma ainda: não há parcela de lotes mistos a exibir."))
    return [
        {"id": "circularidade", "titulo": "Circularidade da simulação", "texto": "Os rótulos de treino vêm de um simulador definido pela equipe; o modelo aprende a lógica do simulador, não o mundo real. Todas as métricas medem aderência ao simulador."},
        {"id": "lote_misto", "titulo": "Lote misto: desempenho desconhecido", "texto": misto},
        {"id": "sem_manually_labeled", "titulo": "Sem conjunto MANUALLY_LABELED", "texto": "O parser de texto foi treinado e calibrado em texto SIMULADO e não há conjunto rotulado manualmente pela equipe; o desempenho em textos reais é DESCONHECIDO. O rascunho gerado por IA não é rotulagem manual."},
        {"id": "pseudonimo", "titulo": "ONGs por pseudônimo", "texto": "As ONGs aparecem por pseudônimo (ong_id) e por tipo/UF/município; nomes e CNPJs não são exibidos. Capacidade, horários e refrigeração das ONGs são DECLARADOS SIMULADOS."},
        {"id": "dados_demo", "titulo": "Dados demonstrativos", "texto": "Doadores, lotes e desfechos são SIMULADOS; ONGs e municípios vêm de fontes públicas com licença em revisão. Uso exclusivamente acadêmico, sem fins comerciais."},
    ]
