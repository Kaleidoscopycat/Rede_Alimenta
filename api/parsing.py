"""Integração do parser semântico da Fase 1 (tipo, perecibilidade, refrigeração, validade, quantidade) à API.

A IA ESTRUTURA e SINALIZA incertezas; NUNCA afirma que o alimento é próprio ou impróprio para consumo.
Todas as respostas informam: origem dos dados de treino (SIMULATED), parser_version e que o limiar τ foi calibrado sobre TEXTO SIMULADO."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from ml.semantic.classifier import ARTIFACT_DIR, SemanticParser

AVISO_PARSER = ("A análise é uma ESTRUTURAÇÃO automática do texto — não afirma que o alimento é próprio ou impróprio para consumo; confirme os campos. "
                "Modelo treinado e limiar de confiança (τ) calibrado sobre texto SIMULADO (data_origin=SIMULATED); não há conjunto MANUALLY_LABELED, "
                "portanto o desempenho em textos reais é DESCONHECIDO.")
THRESHOLD_NOTE = "limiar calibrado sobre texto simulado"
FIELDS = ("categoria", "perecibilidade", "exige_refrigeracao", "dias_ate_validade", "quantidade_kg")


class ParserService:
    def __init__(self) -> None:
        self.path = ARTIFACT_DIR / "semantic_parser.joblib"
        self.sha = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.parser = SemanticParser.load()
        meta = self.parser.meta
        self.version = f"semantic-parser-1.0.0+{self.sha[:12]}"
        self.tau = float(self.parser.tau)
        self.meta = {"trained_on": meta.get("trained_on"), "dataset_tag": meta.get("dataset_tag"), "trained_at": meta.get("trained_at"), "tau": self.tau, "sha256": self.sha}
        mp = ARTIFACT_DIR / "metrics.json"
        self.metrics_note = "Métricas em ml/artifacts/semantic/metrics.json — todas calculadas sobre texto SIMULADO" if mp.exists() else ""

    def raw(self, text: str, ref: dt.date) -> dict[str, Any]:
        return self.parser.parse(text, ref)


def to_kg(quantidade: float | None, unidade: str | None, categoria: str | None, unit_mass: dict[str, float] | None) -> tuple[float | None, str, float]:
    """Converte quantidade+unidade para kg. Retorna (kg, nota, confiança). Conversões por unidade usam massas unitárias da taxonomia (PREMISSA do projeto) ⇒ confiança baixa."""
    if quantidade is None or unidade is None:
        return None, "quantidade/unidade não identificadas", 0.0
    if unidade == "kg":
        return float(quantidade), "kg informado", 0.95
    if unidade == "g":
        return float(quantidade) / 1000.0, "convertido de gramas", 0.95
    if unidade == "litro":
        return float(quantidade), "litro → kg assumindo densidade ≈ 1 (PREMISSA); confirme", 0.5
    um = unit_mass or {}
    if unidade == "duzia" and "unidade" in um:
        return float(quantidade) * 12 * float(um["unidade"]), "dúzia × massa unitária da categoria (PREMISSA); confirme", 0.5
    if unidade in um:
        return float(quantidade) * float(um[unidade]), f"{unidade} × massa unitária da categoria {categoria} (PREMISSA sem fonte); confirme", 0.5
    return None, f"sem massa unitária para '{unidade}' na categoria: informe quantidade_kg", 0.0


def build_parse_response(svc: ParserService, text: str, ref: dt.date, unit_mass_by_cat: dict[str, dict[str, float]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retorna (resposta para a API, saída bruta do parser)."""
    r = svc.raw(text, ref)
    need = set(r["needs_human_confirmation"])
    cat = r["categoria"]
    kg, kg_note, kg_conf = to_kg(r["quantidade"], r["unidade"], cat, unit_mass_by_cat.get(cat))

    def st(pending: bool, value: Any) -> str:
        return "MISSING" if value is None else ("PENDING_CONFIRMATION" if pending else "OK")

    val_pending = "validade" in need or r["validity_source"] != "INFORMADA"
    fields = {
        "categoria": {"value": cat, "confidence": round(r["categoria_conf"], 4), "status": st("categoria" in need or "possivel_duas_categorias" in need, cat),
                      "note": "possível segunda categoria" if "possivel_duas_categorias" in need else None},
        "perecibilidade": {"value": r["perecibilidade"], "confidence": round(r["perecibilidade_conf"], 4), "status": st("perecibilidade" in need, r["perecibilidade"]), "note": None},
        "exige_refrigeracao": {"value": r["requires_refrigeration"], "confidence": round(r["refrigeracao_conf"], 4), "status": st("refrigeracao" in need, r["requires_refrigeration"]),
                               "note": "refrigeração é o ponto fraco do parser (acurácia ≈ 0,90–0,92 em texto SIMULADO)"},
        "dias_ate_validade": {"value": r["days_to_expiry"], "confidence": round(r["validity_confidence"], 4) if r["days_to_expiry"] is not None else 0.0,
                              "status": st(val_pending, r["days_to_expiry"]), "note": f"validity_source={r['validity_source']}"},
        "quantidade_kg": {"value": None if kg is None else round(kg, 3), "confidence": kg_conf, "status": st(kg_conf < 0.9, kg), "note": kg_note},
    }
    alerts = []
    if r["inconsistency_alert"]:
        alerts.append("Inconsistência entre categoria e validade informada (ex.: perecível com validade muito longa ou não perecível com validade de 1 dia). Confira.")
    if r["blocked_expired"]:
        alerts.append("Validade já vencida no texto: o match fica BLOQUEADO (regra explícita).")
    if r["days_to_expiry"] is None:
        alerts.append("Validade ausente e sem possibilidade de inferência: o match fica BLOQUEADO até o doador informar a validade.")
    elif r["validity_source"] == "INFERIDA_PELA_CATEGORIA":
        alerts.append("Validade INFERIDA pela categoria (estimativa conservadora, premissa sem fonte): confirmação obrigatória.")
    if "ambigua" in r["validity_flags"]:
        alerts.append("Expressão de validade imprecisa: confirmação obrigatória.")
    resp = {
        "fields": fields, "validity_source": r["validity_source"], "validity_flags": r["validity_flags"], "alerts": alerts,
        "blocked": {"expired": bool(r["blocked_expired"]), "no_validity": r["days_to_expiry"] is None and not r["blocked_expired"]},
        "needs_human_confirmation": sorted(need), "quantidade_texto": {"quantidade": r["quantidade"], "unidade": r["unidade"]},
        "parser_version": svc.version, "confidence_threshold": svc.tau, "threshold_note": THRESHOLD_NOTE, "training_data_origin": "SIMULATED",
        "manually_labeled_evaluation": "ausente (a equipe precisa criar o conjunto MANUALLY_LABELED)", "aviso": AVISO_PARSER,
    }
    return resp, r
