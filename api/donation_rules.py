"""Regras de montagem/validação de uma doação a partir do parser + correções do doador. Funções PURAS (testáveis).

Regras explícitas:
  R-VAL-1  validade ausente sem possibilidade de inferência  ⇒ BLOCKED_NO_VALIDITY
  R-VAL-2  validade vencida (dias < 0 ou vencida no texto)    ⇒ BLOCKED_EXPIRED
  R-CONF-1 campo com confiança abaixo do limiar, ausente, inferido ou ambíguo ⇒ PENDING_CONFIRMATION (match só após confirmação do doador)
  R-AUD-1  para cada campo guarda-se: valor extraído, confiança, valor final, quem decidiu (PARSER | DONOR | DONOR_CONFIRMED_EXTRACTED | DERIVED_FROM_CATEGORY) e quando."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from core.settings import TZ

REQUIRED = ("categoria", "perecibilidade", "exige_refrigeracao", "dias_ate_validade", "quantidade_kg")
PENDING_STATES = ("PENDING_CONFIRMATION", "MISSING")


def fields_from_parse(resp: dict[str, Any] | None, raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k in REQUIRED:
        src = (resp or {}).get("fields", {}).get(k)
        if src is None:
            out[k] = {"extracted": None, "extracted_confidence": None, "final": None, "status": "MISSING", "decided_by": None, "note": "não informado"}
        else:
            out[k] = {"extracted": src["value"], "extracted_confidence": src["confidence"], "final": src["value"], "status": src["status"], "decided_by": "PARSER", "note": src.get("note")}
    if raw is not None:
        out["dias_ate_validade"]["validity_source"] = raw["validity_source"]
        out["dias_ate_validade"]["expired_in_text"] = bool(raw["blocked_expired"])
        out["dias_ate_validade"]["inconsistency_alert"] = bool(raw["inconsistency_alert"])
    return out


def apply_donor_decisions(fields: dict[str, dict[str, Any]], overrides: dict[str, Any], accept: list[str], user_id: uuid.UUID, now: dt.datetime, today: dt.date,
                          category_perecibilidade: dict[str, str]) -> list[str]:
    """Aplica correções/aceites do doador. Retorna a lista de campos alterados. Levanta ValueError (→ 422) em aceite de campo ausente."""
    changed: list[str] = []
    stamp = {"decided_by_user_id": str(user_id), "decided_at": now.isoformat()}
    ov = dict(overrides)
    if ov.get("validade_data") is not None:
        ov["dias_ate_validade"] = (ov.pop("validade_data") - today).days
    ov.pop("validade_data", None)
    ov = {k: v for k, v in ov.items() if v is not None}
    for k, v in ov.items():
        if v is None:
            continue
        f = fields.setdefault(k, {"extracted": None, "extracted_confidence": None})
        f.update(final=v, status="CONFIRMED", decided_by="DONOR", note="valor informado/corrigido pelo doador", **stamp)
        if k == "dias_ate_validade":
            f["validity_source"], f["expired_in_text"], f["inconsistency_alert"] = "INFORMADA_PELO_DOADOR", False, False
        changed.append(k)
    if "categoria" in ov and "perecibilidade" not in ov:
        fields["perecibilidade"].update(final=category_perecibilidade.get(ov["categoria"]), status="CONFIRMED", decided_by="DERIVED_FROM_CATEGORY",
                                        note="derivada da categoria confirmada pelo doador", **stamp)
        changed.append("perecibilidade")
    for k in accept:
        f = fields.get(k)
        if f is None or f.get("final") is None:
            raise ValueError(f"não é possível aceitar o campo '{k}': sem valor extraído (informe o valor)")
        if k not in ov:
            f.update(status="CONFIRMED", decided_by="DONOR_CONFIRMED_EXTRACTED", **stamp)
            if k == "dias_ate_validade":
                f["validity_source"] = f.get("validity_source", "") + "|CONFIRMADA_PELO_DOADOR"
                f["inconsistency_alert"] = False
            changed.append(k)
    return changed


def evaluate(fields: dict[str, dict[str, Any]], now: dt.datetime) -> dict[str, Any]:
    """Status da doação + valores finais. Não inventa nada: campo sem valor fica MISSING."""
    days_f = fields["dias_ate_validade"]
    days = days_f.get("final")
    status, reason = "READY", None
    if days_f.get("expired_in_text") and days_f.get("decided_by") != "DONOR":
        status, reason = "BLOCKED_EXPIRED", "validade vencida segundo o texto informado (R-VAL-2)"
    elif days is None:
        status, reason = "BLOCKED_NO_VALIDITY", "validade ausente e sem possibilidade de inferência (R-VAL-1): informe a validade"
    elif days < 0:
        status, reason = "BLOCKED_EXPIRED", f"validade vencida há {-days} dia(s) (R-VAL-2)"
    else:
        pend = [k for k in REQUIRED if fields[k].get("status") in PENDING_STATES or fields[k].get("final") is None]
        if pend:
            status, reason = "PENDING_CONFIRMATION", "campos pendentes de confirmação: " + ", ".join(pend)
    expires_at = None
    if days is not None and days >= 0:
        expires_at = dt.datetime.combine(now.astimezone(TZ).date() + dt.timedelta(days=int(days)), dt.time(23, 59, 59), tzinfo=TZ)
    return {"status": status, "block_reason": reason, "expires_at": expires_at, "validity_days": None if days is None else int(days),
            "validity_source": days_f.get("validity_source"), "categoria": fields["categoria"].get("final"), "perecibilidade": fields["perecibilidade"].get("final"),
            "exige_refrigeracao": fields["exige_refrigeracao"].get("final"), "quantity_kg": fields["quantidade_kg"].get("final"),
            "pending": [k for k in REQUIRED if fields[k].get("status") in PENDING_STATES or fields[k].get("final") is None]}
