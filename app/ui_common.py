"""Apoio da interface Streamlit (Fase 3 Parte 1 · Etapa B): textos em português simples, formatação e estados. Sem acesso ao banco e sem importar código da API (a interface só fala HTTP).

Regra de linguagem: para DOADOR e ONG não aparecem termos como "parser", "confiança", "match", "score" ou "τ". O ADMIN mantém os termos técnicos na "Visão técnica"."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # imagem sem base de fusos: o Brasil não tem horário de verão desde 2019 → UTC−3 fixo
    TZ = dt.timezone(dt.timedelta(hours=-3))

CATEGORIAS: dict[str, str] = {
    "HORT_FOLHOSAS": "Hortaliças folhosas", "HORT_RAIZES": "Raízes e tubérculos", "HORT_FRUTOS": "Legumes e frutos de hortaliças", "FRUTAS": "Frutas",
    "PANIFICADOS": "Pães e panificados", "CARNES_PESCADOS": "Carnes e pescados", "LATICINIOS_OVOS": "Laticínios e ovos", "REFEICOES_PRONTAS": "Refeições prontas",
    "GRAOS_CEREAIS": "Grãos e cereais", "INDUSTRIALIZADOS": "Industrializados", "BEBIDAS": "Bebidas"}
EMBALAGENS = ["pacote", "caixa", "garrafa", "lata", "saco", "unidade", "bandeja", "pote", "fardo", "frasco"]
UNIDADES_PESO = {"kg": "kg (quilo)", "g": "g (grama)", "l": "l (litro)", "ml": "ml (mililitro)"}
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]  # índice 0 = segunda … 6 = domingo (convenção da API)
CAMPO_PT = {"categoria": "categoria", "quantidade": "quantidade de unidades", "peso_por_unidade": "peso ou volume por unidade", "validade": "validade",
            "exige_refrigeracao": "refrigeração", "revisao_do_item": "conferência do item", "itens": "itens"}

# Situações da doação (texto da API → rótulo curto e cor). A API devolve `situacao` em linguagem simples; aqui só se escolhe o destaque.
SITUACAO_DESTAQUE: list[tuple[str, str, str]] = [  # (início do texto da API, rótulo, cor do Streamlit)
    ("Aguardando resposta de uma ONG", "Pendente", "orange"), ("Recusada; buscando outra ONG", "Pendente", "orange"), ("Sem resposta; buscando outra ONG", "Pendente", "orange"),
    ("Buscando ONG", "Pendente", "orange"), ("Uma ONG aceitou", "Aceita", "green"), ("Coleta concluída", "Coletada", "green"),
    ("Coleta não concluída", "Coleta não concluída", "red"), ("Nenhuma ONG disponível", "Recusada", "red"),
    ("Rascunho", "Rascunho", "gray"), ("Aguardando a sua confirmação", "Rascunho", "gray"), ("Pronta", "Rascunho", "gray"), ("Bloqueada", "Rascunho", "gray"),
    ("Registro histórico", "Histórico", "gray")]
EVENTO_DOADOR = {"PROPOSED": "Enviada a uma ONG", "DECLINED": "Uma ONG recusou; buscamos outra", "EXPIRED": "Sem resposta no prazo; buscamos outra ONG", "ACCEPTED": "Uma ONG aceitou a doação",
                 "EXHAUSTED": "Nenhuma ONG disponível no momento", "COLLECTED": "Coleta concluída", "FAILED": "Coleta não concluída"}
EVENTO_ONG = {"PROPOSED": "Proposta recebida", "ACCEPTED": "Você aceitou", "DECLINED": "Você recusou", "EXPIRED": "Sem resposta (prazo encerrado)", "COLLECTED": "Coleta concluída",
              "FAILED": "Coleta não concluída"}
HISTORICO_ONG = {"ACCEPTED": ("Aceita", "green"), "DECLINED": ("Recusada", "red"), "EXPIRED": ("Sem resposta", "gray"), "COLLECTED": ("Coletada", "green"), "FAILED": ("Coleta não concluída", "red"),
                 "PROPOSED": ("Aguardando você", "orange")}


def parse_dt(v: Any) -> dt.datetime | None:
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def local(v: Any) -> dt.datetime | None:
    d = parse_dt(v)
    if d is None:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(TZ)


def fmt_date(v: Any) -> str:
    d = local(v)
    return d.strftime("%d/%m/%Y") if d else "—"


def fmt_datetime(v: Any) -> str:
    d = local(v)
    return d.strftime("%d/%m/%Y %H:%M") if d else "—"


def fmt_num(x: Any, nd: int = 2) -> str:
    if x is None:
        return "—"
    s = f"{float(x):,.{nd}f}".rstrip("0").rstrip(".") if nd else f"{float(x):,.0f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_kg(x: Any) -> str:
    return f"{fmt_num(x, 3)} kg" if x is not None else "—"


def fmt_hour(h: Any) -> str:
    if h is None:
        return "—"
    h = float(h)
    return f"{int(h):02d}:{int(round((h - int(h)) * 60)):02d}"


def dias_ate(v: Any, agora: dt.datetime | None = None) -> int | None:
    d = local(v)
    if d is None:
        return None
    hoje = (agora or dt.datetime.now(TZ)).astimezone(TZ).date()
    return (d.date() - hoje).days


def prazo_texto(v: Any, agora: dt.datetime | None = None) -> str:
    """'vence hoje' / 'vence em 3 dias (dd/mm/aaaa)' / 'vencido'."""
    n = dias_ate(v, agora)
    if n is None:
        return "sem validade informada"
    quando = {0: "vence hoje", 1: "vence amanhã"}.get(n) or (f"vence em {n} dias" if n > 1 else "VENCIDO")
    return f"{quando} ({fmt_date(v)})"


def janela_texto(j: dict[str, Any] | None) -> str:
    if not j:
        return "—"
    mask = int(j.get("dias_mask") or 0)
    dias = [DIAS[i][:3] for i in range(7) if (mask >> i) & 1]
    return f"{', '.join(dias) if dias else 'sem dias definidos'} · {fmt_hour(j.get('inicio_h'))} às {fmt_hour(j.get('fim_h'))}"


def item_linha(it: dict[str, Any]) -> str:
    """'3 × pacote de 5 kg = 15 kg' (com 'peso estimado' quando o kg vem de conversão por premissa)."""
    emb = it.get("unit") or "unidade"
    base = f"{fmt_num(it.get('quantity'), 3)} × {emb}"
    if it.get("unit_weight") is not None and it.get("unit_weight_unit"):
        base += f" de {fmt_num(it['unit_weight'], 3)} {it['unit_weight_unit']}"
    kg = it.get("quantity_kg")
    return base + (f" = {fmt_kg(kg)}" + (" (peso estimado)" if it.get("weight_estimated") else "") if kg is not None else " = peso a informar")


def item_validade(it: dict[str, Any]) -> str:
    if not it.get("expires_at"):
        return "validade a informar"
    return f"validade {fmt_date(it['expires_at'])}" + (" (último dia do mês informado)" if it.get("validity_precision") == "MONTH" else "")


def nomes_campos(campos: list[str] | None) -> str:
    return ", ".join(CAMPO_PT.get(c, c) for c in (campos or [])) or "—"


def esc(txt: Any) -> str:
    """Neutraliza Markdown/LaTeX/emoji-shortcode em TEXTO DIGITADO POR OUTRA PESSOA (ex.: nome do alimento que a ONG vê): sem links, imagens externas, negrito, `$..$` nem `:cor[..]`."""
    return re.sub(r"([\\`*_\[\]()#!|<>$~:&])", r"\\\1", "" if txt is None else str(txt))


def limpar(txt: str | None) -> str:
    """Texto vindo da API para exibição: sem códigos internos de regra e sem Markdown ativo."""
    return esc(sem_codigo_interno(txt))


def sem_codigo_interno(txt: str | None) -> str:
    """Remove referências a regras internas (ex.: '(R-VAL-2)') dos textos da API antes de mostrar ao doador."""
    return re.sub(r"\s*\((?:R-[A-Z]+-\d+|[A-Z]{2,}-\d+)\)", "", txt or "").strip()


def destaque_situacao(situacao: str | None) -> tuple[str, str]:
    s = situacao or ""
    for ini, rotulo, cor in SITUACAO_DESTAQUE:
        if s.startswith(ini):
            return rotulo, cor
    return (s or "—"), "gray"


def selo_origem(origin: str | None) -> str:
    """Selo discreto: SIMULADO ou USER_ENTERED (entrada real)."""
    return {"SIMULATED": "🟧 Simulado", "USER_ENTERED": "🟩 Entrada real (USER_ENTERED)", "PUBLIC": "🟦 Fonte pública"}.get(origin or "", origin or "")


def colorir(rotulo: str, cor: str) -> str:
    return f":{cor}[**{rotulo}**]"


def doacao_pendente_envio(d: dict[str, Any]) -> bool:
    return d.get("status") in ("DRAFT", "PENDING_CONFIRMATION", "BLOCKED_EXPIRED", "BLOCKED_NO_VALIDITY", "READY") and not d.get("match_id")


SELO_DASH = {"PÚBLICO": "🟦 PÚBLICO", "SIMULADO": "🟧 SIMULADO", "MEDIDO": "🟩 MEDIDO"}


def selo_dash(selo: str | None) -> str:
    """Selo de origem do dashboard do ADMIN: PÚBLICO (fonte oficial), SIMULADO (simulador documentado) ou MEDIDO (entrada real na plataforma)."""
    return SELO_DASH.get(selo or "", selo or "")


AVISO_ACADEMICO = "Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais"


def aviso_academico() -> None:
    """Aviso visível em TODAS as telas (chamado uma vez pelo ponto de entrada, antes de qualquer página): dados públicos de licença não confirmada e dados simulados, só para a apresentação acadêmica."""
    import streamlit as st
    st.markdown(f"<div style='border-left:4px solid #dd8a1f;padding:.35rem .75rem;margin:.25rem 0 .75rem 0;font-size:.9rem'>⚠️ <b>{AVISO_ACADEMICO}.</b></div>", unsafe_allow_html=True)
