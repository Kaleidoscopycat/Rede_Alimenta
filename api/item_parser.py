"""Parser de texto livre EM ITENS (Fase 3 Parte 1, seção 2.5).

O texto do doador é dividido em segmentos (um por alimento). Para cada segmento:
  * produto, embalagem, número de unidades, peso/volume por embalagem e validade são extraídos por REGRAS (regex), nunca inventados;
  * categoria, perecibilidade e refrigeração vêm do parser semântico da Fase 1 (treinado em texto SIMULADO; desempenho em texto real DESCONHECIDO);
  * validade 'MM/AAAA' vira o ÚLTIMO dia do mês (regra definida pela equipe; a validade real pode ser ANTERIOR) e o item fica PENDENTE de confirmação.
Todo item vindo do texto é SUGESTÃO (entry_source=TEXTO_SUGERIDO): fica com `pending_fields` até o doador confirmar. Nada é gravado como doação aqui."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from api import item_rules as rules
from api.parsing import ParserService

PACKAGINGS = ("pacote", "caixa", "cx", "garrafa", "lata", "saco", "sacola", "pote", "frasco", "fardo", "bandeja", "unidade", "sache", "sachê", "barra", "cesta", "bisnaga")
_PKG = "|".join(sorted(PACKAGINGS, key=len, reverse=True))
_NUM = r"(\d+(?:[.,]\d+)?)"
UNIT_RE = r"(kg|quilos?|quilogramas?|gramas?|g|litros?|ml|mililitros?|l)"
WEIGHT_RE = re.compile(rf"(?:(?P<pkg>{_PKG})s?\s+(?:de|com)\s+)?(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>{UNIT_RE})\b", re.I)
COUNT_RE = re.compile(rf"\b{_NUM}\s*(?P<what>unidades?|un\b|(?:{_PKG})s?\b)", re.I)
VALID_RE = re.compile(r"(?:val(?:idade)?\.?|vence|vencimento|v[áa]lido\s+at[ée])\s*(?:em|:|até|ate)?\s*(?P<d>\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{4}-\d{2})", re.I)
UNIT_NORM = {"kg": "kg", "quilo": "kg", "quilos": "kg", "quilograma": "kg", "quilogramas": "kg", "g": "g", "grama": "g", "gramas": "g", "l": "l", "litro": "l", "litros": "l",
             "ml": "ml", "mililitro": "ml", "mililitros": "ml"}
REVIEW = "revisao_do_item"  # sempre presente em item sugerido: o doador precisa confirmar o item


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def split_segments(text: str) -> list[str]:
    """Divide em itens por vírgula, ponto e vírgula, quebra de linha ou ' e ' FORA de parênteses."""
    out, buf, depth, i = [], [], 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        if depth == 0 and (ch in ",;\n" or text[i:i + 3].lower() == " e "):
            out.append("".join(buf))
            buf = []
            i += 3 if ch == " " else 1
            continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [s.strip(" .\t") for s in out if len(s.strip(" .\t")) >= 3]


def parse_validity(raw: str) -> tuple[dt.date | None, str | None]:
    """→ (data, precisão DAY|MONTH). Data inválida → (None, None)."""
    raw = raw.strip()
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw):
            d, mth, y = (int(x) for x in raw.split("/"))
            return dt.date(y, mth, d), "DAY"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return dt.date.fromisoformat(raw), "DAY"
    except ValueError:
        return None, None
    d = rules.parse_month_year(raw if "/" in raw or "-" in raw else "")
    if d is not None:
        return d, "MONTH"
    return None, None


def merge_segments(segs: list[str]) -> list[str]:
    """Une fragmentos soltos (ex.: 'validade 12/2027' ou '3 unidades' separados por vírgula fora de parênteses) ao item anterior."""
    out: list[str] = []
    for s in segs:
        if out and (re.match(r"^(val|vence|vencimento)", s, re.I) or re.match(rf"^{_NUM}\s*(unidades?|un)\b", s, re.I)):
            out[-1] += ", " + s
        else:
            out.append(s)
    return out


def parse_items(svc: ParserService, text: str, today: dt.date, unit_mass_by_cat: dict[str, dict[str, float]], cat_perec: dict[str, str], max_items: int) -> dict[str, Any]:
    segs = merge_segments(split_segments(text))
    items, global_alerts = [], []
    if len(segs) > max_items:
        global_alerts.append(f"O texto tem mais de {max_items} itens: apenas os primeiros {max_items} foram analisados.")
        segs = segs[:max_items]
    for seg in segs:
        base = re.sub(r"\(.*?\)", " ", seg)
        product = re.sub(rf"(?:\d+(?:[.,]\d+)?\s+)?(?:{_PKG})s?\s+(?:de|com)\s+\d+(?:[.,]\d+)?\s*{UNIT_RE}\b(?:\s+de)?", " ", base, flags=re.I)
        product = re.sub(rf"^\s*\d+(?:[.,]\d+)?\s*(?:{UNIT_RE}|(?:{_PKG})s?)?\s*(?:de\s+)?", "", product, flags=re.I)
        product = VALID_RE.sub(" ", product)
        product = COUNT_RE.sub(" ", product)
        product = WEIGHT_RE.sub(" ", product)
        product = re.sub(r"\s+", " ", product).strip(" .-") or re.sub(r"\s+", " ", base).strip()
        r = svc.raw(seg, today)
        cat = r["categoria"]
        conf = float(r["categoria_conf"])
        notes: list[str] = []
        pending = [REVIEW]
        if cat is None or conf < svc.tau or "possivel_duas_categorias" in r["needs_human_confirmation"]:
            pending.append("categoria")
            notes.append("categoria incerta: confirme")
        # peso/volume por embalagem
        wm = WEIGHT_RE.search(seg)
        pkg = uw = uwu = None
        if wm:
            pkg = (wm.group("pkg") or "").lower() or None
            uw, uwu = _num(wm.group("n")), UNIT_NORM[wm.group("u").lower()]
        cm = None
        for c in COUNT_RE.finditer(seg):  # primeira contagem que não seja o próprio peso
            if wm and c.start() < wm.end() and c.end() > wm.start("n"):
                continue
            cm = c
            break
        count = _num(cm.group(1)) if cm else None
        if cm is not None and not pkg:
            w = cm.group("what").lower().rstrip("s")
            pkg = None if w in ("unidade", "un") else w
        if uw is None:
            pending.append("peso_por_unidade")
        if count is None:
            count = 1.0 if uw is not None else None
            pending.append("quantidade")
            if uw is not None:
                notes.append("número de unidades não informado: assumimos 1 (confirme)")
        # validade
        vm = VALID_RE.search(seg)
        expires = vdays = prec = vsrc = None
        if vm:
            d, prec = parse_validity(vm.group("d"))
            if d is not None:
                expires, vdays, vsrc = rules.end_of_day(d), rules.days_until(d, today), "SUGERIDA_PELO_TEXTO"
                if prec == "MONTH":
                    notes.append(rules.validity_note("MONTH", expires) or "")
                    pending.append("validade")
            else:
                pending.append("validade")
                notes.append("validade com formato não reconhecido")
        else:
            pending.append("validade")
            notes.append("validade não informada no texto")
        refrig = r["requires_refrigeration"]
        if refrig is None or float(r["refrigeracao_conf"]) < svc.tau:
            pending.append("exige_refrigeracao")
        else:
            pending.append("exige_refrigeracao")  # sugestão do parser: sempre confirmada pelo doador (ponto fraco do parser)
        w = None
        if uw is not None and count is not None and uwu is not None:
            w = rules.item_weight(count, uw, uwu, cat, unit_mass_by_cat.get(cat or ""))
            if w.note:
                notes.append(w.note)
        items.append({
            "produto": product[:80], "categoria": cat, "categoria_conf": round(conf, 4), "perecibilidade": cat_perec.get(cat) if cat else None,
            "exige_refrigeracao": refrig, "exige_refrigeracao_conf": round(float(r["refrigeracao_conf"]), 4), "quantity": count, "unit": pkg, "unit_weight": uw, "unit_weight_unit": uwu,
            "quantity_kg": w.quantity_kg if w else None, "weight_basis": w.basis if w else None, "weight_estimated": bool(w.estimated) if w else False,
            "expires_at": expires, "validity_days": vdays, "validity_precision": prec, "validity_source": vsrc, "pending_fields": sorted(set(pending)),
            "notes": [n for n in notes if n], "segmento": seg[:200]})
    return {"items": items, "alerts": global_alerts, "parser_version": svc.version, "confidence_threshold": svc.tau, "threshold_note": "limiar calibrado sobre texto simulado",
            "training_data_origin": "SIMULATED"}
