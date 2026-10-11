"""Gerador de descrições textuais dos lotes (SIMULATED) com rótulos de verdade gerados JUNTO (DATA_SIMULATION_SPEC §6).

- 4 famílias de modelos de frase: F1 telegráfica, F2 frase completa, F3 informal, F4 campos/lista (RESERVADA: fora do treino).
- Operadores de variação: abreviações, erros de digitação, acentos, caixa, formatos de data, unidades, temperatura mencionada ou ausente.
- Casos difíceis de propósito: validade ausente/ambígua/inconsistente, texto vago, duas categorias.
- Privacidade: nenhum nome de pessoa, telefone, e-mail, CNPJ, marca ou endereço.
RISCO DE CIRCULARIDADE: o léxico de produto é o mesmo da taxonomia (premissa); no texto simulado produto->categoria é determinístico
por construção. Um classificador pode apenas aprender os modelos de frase deste gerador (ver DATA_SIMULATION.md).
"""
from __future__ import annotations

import datetime as dt
import random
from typing import Any

TRAIN_FAMILIES = ("F1", "F2", "F3")
RESERVED_FAMILY = "F4"

UNIT_FORMS = {
    "caixa": (["caixa", "caixas"], ["cx", "cxs"]), "pacote": (["pacote", "pacotes"], ["pct", "pcts"]),
    "unidade": (["unidade", "unidades"], ["un", "und"]), "duzia": (["dúzia", "dúzias"], ["dz", "dz"]),
    "bandeja": (["bandeja", "bandejas"], ["bdj", "bdjs"]), "litro": (["litro", "litros"], ["L", "lt"]),
    "kg": (["quilo", "quilos"], ["kg", "kg"]), "g": (["grama", "gramas"], ["g", "g"]),
}
GENDER = {"caixa": "f", "pacote": "m", "unidade": "f", "duzia": "f", "bandeja": "f", "litro": "m", "kg": "m", "g": "f"}
WORDS_M = {1: "um", 2: "dois", 3: "três"}
WORDS_F = {1: "uma", 2: "duas", 3: "três"}
DESCRIPTORS = ["fresco", "frescos", "de primeira", "da semana", "em bom estado", "embalado", "tipo 1", "selecionado"]
FILLERS = ["Retirada somente no local.", "Material embalado.", "Preferência para retirada pela manhã.", "Disponível para retirada imediata.",
           "Não temos como entregar.", "Retirar na portaria.", "Embalagens fechadas.", "Sobrou do estoque desta semana.", "Quantidade aproximada."]
ALLERGEN_WORD = {"leite fluido": "leite", "queijo": "leite", "iogurte natural": "leite", "iogurte": "leite", "creme de leite": "leite",
                 "ovos": "ovo", "requeijão": "leite", "manteiga": "leite", "macarrão": "glúten", "aveia": "glúten", "farinha de trigo": "glúten",
                 "lasanha": "glúten", "amendoim": "amendoim", "sardinha em lata": "peixe", "leite em pó": "leite", "biscoito": "glúten",
                 "bebida de soja": "soja"}
VAGUE_BY_CAT = {
    "PANIFICADOS": ["sobras de padaria", "pães variados", "salgados e pães do dia"], "HORT_FOLHOSAS": ["verduras", "verduras variadas"],
    "HORT_RAIZES": ["legumes", "legumes variados"], "HORT_FRUTOS": ["legumes e verduras", "hortaliças"], "FRUTAS": ["frutas diversas", "frutas variadas"],
    "CARNES_PESCADOS": ["carnes variadas", "proteína congelada"], "LATICINIOS_OVOS": ["laticínios", "produtos lácteos"],
    "REFEICOES_PRONTAS": ["refeições do dia", "comida pronta"], "GRAOS_CEREAIS": ["alimentos não perecíveis", "grãos"],
    "INDUSTRIALIZADOS": ["produtos industrializados", "mercearia"], "BEBIDAS": ["bebidas", "líquidos variados"],
}
VAGUE_GENERIC = ["alimentos diversos", "mantimentos", "doação de comida", "itens variados", "alimentos", "uma doação de alimentos"]
TEMP_REF = ["refrigerado", "mantido refrigerado", "mantido a 4 °C", "na geladeira", "mantido a 4°C", "gelado", "temp. 4C", "armazenado a 5 °C"]
TEMP_FRZ = ["congelado", "mantido congelado", "congelado a -18 °C", "freezer -18C", "mantido a -18°C"]
TEMP_AMB = ["temperatura ambiente", "armazenado em local seco", "em temp. ambiente"]
INCONS_STATED = {"HORT_FOLHOSAS": (120, 365), "PANIFICADOS": (15, 90), "REFEICOES_PRONTAS": (10, 60), "HORT_FRUTOS": (60, 200), "FRUTAS": (60, 200),
                 "LATICINIOS_OVOS": (100, 300), "CARNES_PESCADOS": (250, 400), "GRAOS_CEREAIS": (0, 1), "INDUSTRIALIZADOS": (0, 1), "BEBIDAS": (0, 1), "HORT_RAIZES": (150, 300)}
INFER_CATS = ("PANIFICADOS", "REFEICOES_PRONTAS", "HORT_FOLHOSAS")  # validade só "inferível" onde o intervalo da premissa é curto (<=4 dias)


def _typo(w: str, rng: random.Random) -> str:
    if len(w) < 4:
        return w
    i = rng.randrange(1, len(w) - 1)
    op = rng.choice(["swap", "drop", "dup"])
    if op == "swap":
        return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    if op == "drop":
        return w[:i] + w[i + 1:]
    return w[:i] + w[i] + w[i:]


def _strip_accents(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _abbrev(prod: str, rng: random.Random) -> str:
    out = []
    for w in prod.split():
        if w in ("de", "da", "do") and rng.random() < 0.5:
            continue
        if len(w) > 6 and rng.random() < 0.5:
            w = w[: rng.choice([3, 4, 5])] + "."
        out.append(w)
    return " ".join(out)


def _qty_phrase(q: int | None, unit: str, rng: random.Random, abbreviate: bool, compact: bool) -> str:
    if q is None:
        return rng.choice(["várias", "algumas", "bastante"]) + " " + UNIT_FORMS[unit][0][1]
    sing, plur = UNIT_FORMS[unit][0]
    abbr_s, abbr_p = UNIT_FORMS[unit][1]
    num = str(q)
    if q <= 3 and unit not in ("kg", "g") and rng.random() < 0.15:
        num = (WORDS_F if GENDER[unit] == "f" else WORDS_M)[q]
    if abbreviate:
        u = abbr_s if q == 1 else abbr_p
        return f"{num}{u}" if compact else f"{num} {u}"
    return f"{num} {sing if q == 1 else plur}"


def _date_forms(d: int, ref: dt.date, rng: random.Random) -> tuple[str, str]:
    """(texto, tipo) para validade informada com d dias a partir de ref."""
    exp = ref + dt.timedelta(days=d)
    ds = f"{exp.day:02d}/{exp.month:02d}"
    dfull = f"{exp.day:02d}/{exp.month:02d}/{exp.year}"
    dshort = f"{exp.day:02d}/{exp.month:02d}/{exp.year % 100:02d}"
    prefer_abs = d >= 30 and rng.random() < 0.8
    if not prefer_abs and rng.random() < 0.6:
        if d == 0:
            return rng.choice(["vence hoje", "val. hoje", "validade hoje"]), "rel"
        if d == 1:
            return rng.choice(["vence amanhã", "vence em 1 dia", "val. 1 dia", "validade amanhã"]), "rel"
        return rng.choice([f"vence em {d} dias", f"validade {d} dias", f"val. {d}d", f"prazo de {d} dias", f"vence em {d} d"]), "rel"
    choices = [f"val. {dfull}", f"validade {dfull}", f"vence dia {ds}" if d < 200 else f"vence em {dfull}", f"val {dshort}", f"vencimento {dfull}"]
    if d < 150:
        choices += [f"val. {ds}", f"val {ds}", f"validade {ds}"]
    return rng.choice(choices), "abs"


def _ambiguous_phrase(d: int, rng: random.Random) -> str:
    """Frase de validade imprecisa aplicável a qualquer d (o rótulo continua sendo o d verdadeiro do lote)."""
    cands = []
    if d <= 1:
        cands.append("vence hoje ou amanhã")
    if 1 <= d <= 7:
        cands += ["vence daqui uns dias", "vence essa semana"]
    if 5 <= d <= 10:
        cands.append("vence semana que vem")
    if 8 <= d <= 19:
        cands.append("vence daqui umas duas semanas")
    if 20 <= d <= 70:
        cands.append("vence mês que vem")
    if 71 <= d < 200:
        cands.append("vence só daqui uns meses")
    if d >= 200:
        cands.append("vence ano que vem")
    return rng.choice(cands)


def build_text(lot: dict, family: str, flags: dict, tax: dict, rng: random.Random, p: dict) -> dict[str, Any]:
    """Gera o texto e os rótulos. `lot`: produto, categoria, perecibilidade, quantidade, unidade, dias_ate_validade, temperatura_conservacao,
    exige_refrigeracao, ref_date (date). `flags`: vago, ausente, ambigua, inconsistente, duas_categorias (bool)."""
    noise: list[str] = []
    cat, prod, d = lot["categoria"], lot["produto"], int(lot["dias_ate_validade"])
    ref: dt.date = lot["ref_date"]
    qty, unit = lot["quantidade"], lot["unidade"]
    y_qty: float | None = float(qty); y_unit = unit
    # ---- quantidade/unidade
    if unit == "kg" and qty <= 10 and rng.random() < 0.08:
        qty, unit = int(qty * 1000), "g"; y_qty, y_unit = float(qty), "g"; noise.append("kg_para_g")
    abbreviate = family in ("F1", "F4") and rng.random() < 0.75 or family == "F3" and rng.random() < 0.35 or family == "F2" and rng.random() < 0.15
    compact = family == "F1" and rng.random() < 0.6
    # ---- produto
    prod_txt = prod
    diffs: list[str] = []
    cat2 = None
    if flags.get("vago"):
        diffs.append("vago")
        if rng.random() < 0.5:
            prod_txt = rng.choice(VAGUE_BY_CAT[cat]); noise.append("vago_por_categoria")
        else:
            prod_txt = rng.choice(VAGUE_GENERIC); noise.append("vago_generico")
        if rng.random() < 0.5:
            qty = None; y_qty = None; noise.append("sem_quantidade")
    elif flags.get("duas_categorias"):
        diffs.append("duas_categorias")
        other = rng.choice([c for c in tax["categories"] if c != cat])
        prod2 = rng.choice(tax["categories"][other]["products"])["name"]
        cat2 = other
        prod_txt = rng.choice([f"{prod} e {prod2}", f"cesta com {prod} e {prod2}", f"{prod} + {prod2}"])
        noise.append("duas_categorias")
    else:
        if rng.random() < 0.35:
            prod_txt = _abbrev(prod, rng); noise.append("abrev_produto")
        if rng.random() < 0.25 and not prod_txt.endswith("s") and cat in ("HORT_FOLHOSAS", "HORT_RAIZES", "HORT_FRUTOS", "FRUTAS"):
            prod_txt = prod_txt + "s"; noise.append("plural")
        if rng.random() < 0.15:
            prod_txt = prod_txt + " " + rng.choice(DESCRIPTORS); noise.append("descritor")
    qty_txt = _qty_phrase(qty if qty is None else int(qty), unit, rng, abbreviate, compact) if qty is not None else _qty_phrase(None, "caixa", rng, False, False)
    # ---- validade
    y_days: int | None = d
    vsrc = "INFORMADA"
    val_txt: str | None = None
    val_kind = None
    if flags.get("ausente") or (flags.get("vago") and rng.random() < 0.6):
        vsrc = "INFERIDA_PELA_CATEGORIA" if cat in INFER_CATS else "AUSENTE"
        y_days = None
        if flags.get("ausente"):
            diffs.append("validade_ausente")
        noise.append("sem_validade")
    elif flags.get("ambigua"):
        val_txt = _ambiguous_phrase(d, rng); val_kind = "ambigua"; diffs.append("validade_ambigua")
    elif flags.get("inconsistente"):
        lo, hi = INCONS_STATED[cat]
        s = rng.randint(lo, hi)
        val_txt, val_kind = _date_forms(s, ref, rng); y_days = s; diffs.append("inconsistente_com_categoria")
    else:
        val_txt, val_kind = _date_forms(d, ref, rng)
    # ---- temperatura
    temp_txt = None
    if rng.random() < p["p_temp_mention"]:
        st = lot["temperatura_conservacao"]
        temp_txt = rng.choice(TEMP_FRZ if st == "CONGELADO" else TEMP_REF if st == "REFRIGERADO" else TEMP_AMB if rng.random() < 0.3 else TEMP_REF)
        if st == "AMBIENTE" and temp_txt in TEMP_REF:
            temp_txt = None  # não menciona refrigeração falsa
    # ---- alérgeno
    allerg_txt = None
    if lot.get("allergen_product") and rng.random() < p["p_allergen_mention"]:
        allerg_txt = rng.choice([f"contém {ALLERGEN_WORD.get(prod, 'leite')}", f"alérgeno: {ALLERGEN_WORD.get(prod, 'leite')}"])
    # ---- montar por família
    tid, body = _compose(family, qty_txt, prod_txt, val_txt, temp_txt, allerg_txt, flags, rng, qty is None)
    if rng.random() < 0.18 and family != "F4":
        body += " " + rng.choice(FILLERS); noise.append("filler_longo")
    if family in ("F2", "F3") and rng.random() < 0.10:
        body = rng.choice(["Bom dia. ", "Olá, ", "Boa tarde! "]) + body[0].lower() + body[1:]; noise.append("saudacao")
    # ---- ruído ortográfico
    if rng.random() < p["p_typo"]:
        words = body.split(" ")
        idx = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
        if idx:
            for i in rng.sample(idx, k=min(len(idx), rng.choice([1, 1, 2]))):
                words[i] = _typo(words[i], rng)
            body = " ".join(words); noise.append("typo")
    if rng.random() < 0.20:
        body = _strip_accents(body); noise.append("sem_acentos")
    cs = rng.random()
    if cs < 0.08:
        body = body.upper(); noise.append("caixa_alta")
    elif cs < 0.22 and family != "F2":
        body = body.lower(); noise.append("caixa_baixa")
    if rng.random() < 0.07:
        body = body.replace(" ", "  ", 1); noise.append("espaco_duplo")
    labels = {
        "y_categoria": cat, "y_categoria_2": cat2, "y_produto": prod, "y_perecibilidade": lot["perecibilidade"],
        "y_exige_refrigeracao": bool(lot["exige_refrigeracao"]), "y_dias_ate_validade": y_days, "y_dias_lote_verdade": d,
        "y_validity_source": vsrc, "y_quantidade": y_qty, "y_unidade": y_unit, "y_contem_alergenico_texto": allerg_txt is not None,
    }
    return {"texto": body.strip(), "template_family_id": family, "template_id": tid, "noise_ops": noise, "difficulty_flags": diffs,
            "validity_kind": val_kind, **labels}


def _compose(fam, q, prod, val, temp, allerg, flags, rng, no_qty) -> tuple[str, str]:
    t = [x for x in (temp,) if x]
    a = [x for x in (allerg,) if x]
    if fam == "F1":
        opts = [
            ("F1-1", lambda: " ".join(x for x in (q, prod, temp, val, allerg) if x)),
            ("F1-2", lambda: " ".join(x for x in (prod, q, val, temp, allerg) if x)),
            ("F1-3", lambda: " - ".join(x for x in (f"{q} {prod}", val, temp, allerg) if x)),
            ("F1-4", lambda: f"{prod} ({q})" + "".join(f" {x}" for x in (val, temp, allerg) if x)),
            ("F1-5", lambda: ", ".join(x for x in (f"{q} {prod}", temp, val) if x)),
        ]
    elif fam == "F2":
        opts = [
            ("F2-1", lambda: f"Temos {q} de {prod} para doação." + (f" {temp.capitalize()}." if temp else "") + (f" {val.capitalize()}." if val else "") + (f" {allerg.capitalize()}." if allerg else "")),
            ("F2-2", lambda: f"Gostaríamos de doar {q} de {prod}" + (f", {temp}" if temp else "") + (f", {val}" if val else "") + (f" ({allerg})" if allerg else "") + "."),
            ("F2-3", lambda: f"Disponibilizamos {q} de {prod} para retirada." + (f" O produto está {temp}." if temp and not temp.startswith("temp") else (f" Armazenamento: {temp}." if temp else "")) + (f" A validade: {val.replace('vence ', '').replace('validade ', '').replace('val. ', '')}." if val else "")),
            ("F2-4", lambda: f"Doação de {prod}: {q}." + (f" {val.capitalize()}." if val else "") + (f" {temp.capitalize()}." if temp else "") + (f" {allerg.capitalize()}." if allerg else "")),
            ("F2-5", lambda: f"Nossa loja tem {q} de {prod} disponíveis" + (f", {val}" if val else "") + (f" e {temp}" if temp else "") + "."),
        ]
    elif fam == "F3":
        opts = [
            ("F3-1", lambda: f"oi, sobrou {q} de {prod} aqui" + (f", {val}" if val else "") + (f", {temp}" if temp else "") + ". alguém pode buscar?"),
            ("F3-2", lambda: f"pessoal, tenho {prod} ({q})" + (f" {temp}" if temp else "") + (f" {val}" if val else "") + (f" {allerg}" if allerg else "") + ", quem busca?"),
            ("F3-3", lambda: f"bom dia! temos {q} de {prod}" + (f", {val}" if val else "") + ", pode retirar hoje?" + (f" ({temp})" if temp else "")),
            ("F3-4", lambda: f"vamos doar {prod}, {q}" + (f" - {val}" if val else "") + (f" - {temp}" if temp else "") + " - só retirar"),
            ("F3-5", lambda: f"to com {q} de {prod} sobrando" + (f", {temp}" if temp else "") + (f", {val}" if val else "") + ", alguém interessado?"),
        ]
    else:  # F4 campos/lista (RESERVADA)
        va = val if val else rng.choice(["-", "não informada", "não consta"])
        opts = [
            ("F4-1", lambda: f"Produto: {prod}\nQuantidade: {q}\nValidade: {va}" + (f"\nConservação: {temp}" if temp else "") + (f"\nObs: {allerg}" if allerg else "")),
            ("F4-2", lambda: f"item: {prod} | qtd: {q} | validade: {va}" + (f" | armazenamento: {temp}" if temp else "")),
            ("F4-3", lambda: f"PRODUTO={prod} QTD={q} VAL={va}" + (f" TEMP={temp}" if temp else "")),
            ("F4-4", lambda: f"- {prod}; {q}; {va}" + (f"; {temp}" if temp else "") + (f"; {allerg}" if allerg else "")),
        ]
    tid, fn = opts[rng.randrange(len(opts))]
    return tid, fn()
