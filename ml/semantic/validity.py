"""Parser de validade: regex + biblioteca de datas (dateparser, só como fallback p/ datas por extenso).

Saída com ORIGEM declarada: validity_source = INFORMADA | INFERIDA_PELA_CATEGORIA | AUSENTE. NUNCA preenche a validade em silêncio:
- quando só a categoria permite estimar (categorias de vida curta), devolve a estimativa CONSERVADORA (mínimo da premissa) com source=INFERIDA;
- lote vencido (dias < 0) é bloqueado por REGRA DETERMINÍSTICA (`blocked_expired`), nunca por modelo;
- categoria x validade incompatíveis geram alerta de inconsistência (não corrige o valor).
A IA estrutura e sinaliza; NÃO afirma que um alimento está próprio ou impróprio para consumo.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata
from typing import Any

import yaml

from simulation.params import TAXONOMY_FILE

_TAX = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))["categories"]
INFER_CATS = ("PANIFICADOS", "REFEICOES_PRONTAS", "HORT_FOLHOSAS")
MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
AMBIG = [(r"vence hoje ou amanha", 0), (r"daqui (?:a )?umas duas semanas", 14), (r"so daqui uns meses", 90), (r"daqui (?:a )?uns dias", 4), (r"(?:essa|esta) semana", 3),
         (r"semana que vem|proxima semana", 7), (r"mes que vem|proximo mes", 30), (r"ano que vem", 365)]
CTX = r"(?:vence|vencem|vencer|vencimento|validade|val\.?|venc\.?|prazo(?: de)?|dura|ate|em|uns|usar)"


def strip(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def max_days_premise(cat: str) -> float:
    c = _TAX[cat]
    return float(max(c["days"][1], c.get("days_frozen", [0, 0])[1]))


def inconsistency_alert(cat: str | None, days: int | None) -> bool:
    if cat is None or days is None or cat not in _TAX:
        return False
    if _TAX[cat]["perecibilidade"] == "NAO_PERECIVEL":
        return days <= 1
    return days > max_days_premise(cat) * 1.3 * 1.5 + 3


def _mk_date(d: int, m: int, y: int | None, ref: dt.date, past_ok: bool) -> dt.date | None:
    try:
        if y is None:
            cand = dt.date(ref.year, m, d)
            if cand < ref and not past_ok:
                cand = dt.date(ref.year + 1, m, d)
            return cand
        y = y + 2000 if y < 100 else y
        return dt.date(y, m, d)
    except ValueError:
        return None


def _month_end(m: int, y: int) -> dt.date | None:
    if not (1 <= m <= 12):
        return None
    y = y + 2000 if y < 100 else y
    nxt = dt.date(y + (m == 12), (m % 12) + 1, 1)
    return nxt - dt.timedelta(days=1)


def parse_validity(text: str, ref: dt.date, category: str | None = None) -> dict[str, Any]:
    s = strip(text)
    flags: list[str] = []
    days: int | None = None; conf = 0.0; matched = ""
    past_ok = bool(re.search(r"vencid|ontem|desde", s))
    # 1) frases imprecisas (ambíguas)
    for pat, v in AMBIG:
        if re.search(pat, s):
            days, conf, matched = v, 0.35, pat; flags.append("ambigua"); break
    # 2) hoje / amanhã com contexto
    if days is None:
        if re.search(r"(?:vence|vencem|val\.?|validade|prazo|precisa sair|consumir)[^.;|\n]{0,18}\bhoje\b|\bvalidade hoje\b", s):
            days, conf, matched = 0, 0.95, "hoje"
        elif re.search(r"(?:vence|vencem|val\.?|validade|ate|so dura ate)[^.;|\n]{0,15}\bamanha\b", s):
            days, conf, matched = 1, 0.95, "amanha"
    # 3) prazo relativo numérico
    if days is None:
        m = re.search(r"(\d+)\s*(?:a|ou)\s*(\d+)\s*dias?", s)
        if m:
            days, conf, matched = min(int(m.group(1)), int(m.group(2))), 0.55, m.group(0); flags.append("ambigua")
        else:
            m = re.search(r"(\d+)\s*(?:meses|mes)\b", s) if re.search(r"(?:daqui|vence|validade|val)[^.;|\n]{0,15}\d+\s*mes", s) else None
            if m:
                days, conf, matched = 30 * int(m.group(1)), 0.5, m.group(0); flags.append("ambigua")
            else:
                m = re.search(r"(\d+)\s*semanas?\b", s) if re.search(r"(?:vence|validade|val|em|ate)[^.;|\n]{0,12}\d+\s*semana", s) else None
                if m:
                    days, conf, matched = 7 * int(m.group(1)), 0.7, m.group(0)
                else:
                    m = re.search(r"(\d+)\s*dias?\b", s) or re.search(CTX + r"\s*(\d+)\s*d\b", s)
                    if m:
                        days, conf, matched = int(m.group(1)), 0.95, m.group(0)
                        if re.search(r"\buns\s+\d+\s*dias", s) or re.search(r"\b(?:uns|cerca de|aprox\w*)\s*\d+", s):
                            flags.append("ambigua"); conf = 0.6
    # 4) datas absolutas
    if days is None:
        cands = []
        for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)|(?<![\d/])(\d{1,2})/(20\d{2})(?!\d)|(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", s):
            if m.group(1):
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3)); dtv = _mk_date(d, mo, y, ref, True); c = 0.95
            elif m.group(4):
                dtv = _month_end(int(m.group(4)), int(m.group(5))); c = 0.7; flags.append("formato_mes_ano")
            else:
                a, b = int(m.group(6)), int(m.group(7))
                if b <= 12 and a <= 31:
                    dtv = _mk_date(a, b, None, ref, past_ok); c = 0.9
                elif a <= 12 and 20 <= b <= 40:
                    dtv = _month_end(a, b); c = 0.6; flags.append("formato_mes_ano")
                else:
                    dtv = None; c = 0
            if dtv:
                cands.append((dtv, c, m.group(0)))
        if not cands:
            mm = re.search(r"(\d{1,2}) de (" + "|".join(MESES) + r")(?: de (\d{4}))?", s)
            if mm:
                try:
                    import dateparser  # fallback "15 de outubro" (biblioteca de datas)
                    pd_ = dateparser.parse(mm.group(0), languages=["pt"], settings={"DATE_ORDER": "DMY", "PREFER_DATES_FROM": "future", "RELATIVE_BASE": dt.datetime(ref.year, ref.month, ref.day)})
                    if pd_:
                        cands.append((pd_.date(), 0.85, mm.group(0)))
                except Exception:  # noqa: BLE001 - fallback opcional: a falha é registrada e o campo segue como ausente (bloqueio seguro)
                    logging.getLogger(__name__).debug("fallback dateparser falhou para %r", mm.group(0), exc_info=True)
        if cands:
            if len({c[0] for c in cands}) > 1:
                flags.append("multiplas_datas")
            dtv, c, matched = min(cands, key=lambda x: x[0])
            days = (dtv - ref).days; conf = c - (0.15 if "multiplas_datas" in flags else 0)
    if days is not None:
        src = "INFORMADA"
    elif category in INFER_CATS:
        days, src, conf = int(_TAX[category]["days"][0]), "INFERIDA_PELA_CATEGORIA", 0.4  # estimativa conservadora (mínimo da premissa)
    else:
        src, conf = "AUSENTE", 0.0
    blocked = days is not None and days < 0 and src == "INFORMADA"
    if blocked:
        flags.append("vencido")
    return {"days_to_expiry": days, "validity_source": src, "validity_confidence": float(conf), "flags": sorted(set(flags)), "matched": matched,
            "blocked_expired": bool(blocked), "inconsistency_alert": bool(src == "INFORMADA" and inconsistency_alert(category, days))}
