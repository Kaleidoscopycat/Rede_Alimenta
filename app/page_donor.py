"""Telas do DOADOR (Fase 3 Parte 1 · Etapa B): "Nova doação" em passos (Itens → Retirada → Revisar e enviar) e "Minhas doações".
Consome só a API de rascunho/itens (Etapa A). Nenhuma nota, ranking ou termo técnico da IA: o doador vê campos de formulário, o total em kg e a situação da doação."""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable

import httpx
import streamlit as st

from app.api_client import ApiClient, ApiError
from app.ui_common import (CATEGORIAS, DIAS, EMBALAGENS, EVENTO_DOADOR, TZ, UNIDADES_PESO, colorir, destaque_situacao, dias_ate, doacao_pendente_envio, fmt_date, fmt_datetime, fmt_hour,
                           esc, fmt_kg, item_linha, item_validade, janela_texto, limpar, local, nomes_campos, prazo_texto, selo_origem)

PASSOS = ["Itens", "Retirada", "Revisar e enviar"]
MESES = [f"{m:02d}" for m in range(1, 13)]


# ------------------------------------------------------------------ utilidades
def chamar(fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    """Chama a API e mostra erros em linguagem simples (nunca traceback). Devolve None em caso de erro."""
    try:
        return fn(*args, **kw)
    except ApiError as e:
        if e.status == 409 and "alterad" in e.message:  # a API recusa alterar doação já enviada (itens só mudam antes de a ONG ser acionada)
            st.session_state["bloqueada"] = True
            st.rerun()  # a tela passa a explicar o bloqueio e a oferecer "Criar nova doação"
        st.error(e.friendly)
        return None
    except httpx.HTTPError:
        st.error("Não conseguimos falar com o serviço agora. Verifique sua conexão e tente de novo.")
        return None


def novo_rascunho() -> None:
    for k in ("draft", "bloqueada", "editando", "enviada", "texto_lote"):
        st.session_state.pop(k, None)
    st.session_state["passo"] = 1
    st.session_state["nonce"] = st.session_state.get("nonce", 0) + 1


def garantir_rascunho(cli: ApiClient) -> dict | None:
    if st.session_state.get("draft"):
        return st.session_state["draft"]
    d = chamar(cli.create_draft, {})
    if d:
        st.session_state["draft"] = d
    return d


def horas_opcoes() -> list[float]:
    return [h / 2 for h in range(0, 49)]


def hora_txt(h: float) -> str:
    return fmt_hour(h)


# ------------------------------------------------------------------ formulário de item
def campos_item(prefixo: str, it: dict | None = None) -> dict[str, Any]:
    """Desenha os campos do item (novo ou em edição) e devolve os valores crus."""
    it = it or {}
    hoje = dt.datetime.now(TZ).date()
    nome = st.text_input("Nome do alimento", value=it.get("produto") or "", max_chars=80, key=f"{prefixo}_nome", placeholder="Ex.: arroz, leite, maçã")
    cats = list(CATEGORIAS)
    categoria = st.selectbox("Categoria", cats, index=cats.index(it["categoria"]) if it.get("categoria") in cats else None, format_func=CATEGORIAS.get,
                             placeholder="Escolha a categoria", key=f"{prefixo}_cat")
    c1, c2 = st.columns(2)
    qtd = c1.number_input("Quantidade de unidades", min_value=0.0, max_value=100000.0, step=1.0, value=float(it["quantity"]) if it.get("quantity") else None, key=f"{prefixo}_qtd",
                          placeholder="Ex.: 3")
    embs = EMBALAGENS + ([it["unit"]] if it.get("unit") and it["unit"] not in EMBALAGENS else [])
    emb = c2.selectbox("Tipo de embalagem", embs, index=embs.index(it["unit"]) if it.get("unit") in embs else 0, key=f"{prefixo}_emb")
    c3, c4 = st.columns(2)
    peso = c3.number_input("Peso ou volume de cada unidade", min_value=0.0, max_value=100000.0, step=0.1, value=float(it["unit_weight"]) if it.get("unit_weight") else None,
                           key=f"{prefixo}_peso", placeholder="Ex.: 5")
    unidades = list(UNIDADES_PESO)
    un = c4.selectbox("Medida", unidades, index=unidades.index(it["unit_weight_unit"]) if it.get("unit_weight_unit") in unidades else 0, format_func=UNIDADES_PESO.get, key=f"{prefixo}_un")
    if un in ("l", "ml"):
        st.caption("Líquidos: o peso em kg será uma **estimativa** (volume convertido por uma média da categoria). Se souber o peso real, informe em kg ou g.")
    modo0 = 1 if it.get("validity_precision") == "MONTH" else 0
    modo = st.radio("Como você sabe a validade?", ["Data exata", "Só mês e ano"], index=modo0, horizontal=True, key=f"{prefixo}_modo")
    data_val = mes = ano = None
    exp = local(it.get("expires_at"))
    if modo == "Data exata":
        data_val = st.date_input("Data de validade", value=exp.date() if exp and modo0 == 0 else None, min_value=hoje - dt.timedelta(days=365), max_value=hoje + dt.timedelta(days=3650),
                                 format="DD/MM/YYYY", key=f"{prefixo}_data")
    else:
        anos = [str(a) for a in range(hoje.year, hoje.year + 11)]
        c5, c6 = st.columns(2)
        mes = c5.selectbox("Mês", MESES, index=MESES.index(f"{exp.month:02d}") if exp and modo0 == 1 else None, placeholder="Mês", key=f"{prefixo}_mes")
        ano = c6.selectbox("Ano", anos, index=anos.index(str(exp.year)) if exp and modo0 == 1 and str(exp.year) in anos else None, placeholder="Ano", key=f"{prefixo}_ano")
        st.caption("Com só o mês e o ano, usamos o **último dia do mês**; a validade real pode ser anterior — confirme a data exata se possível.")
    ref0 = it.get("exige_refrigeracao")
    refrig = st.radio("Exige refrigeração?", ["Sim", "Não"], index=None if ref0 is None else (0 if ref0 else 1), horizontal=True, key=f"{prefixo}_ref")
    return {"produto": nome.strip(), "categoria": categoria, "quantity": qtd, "unit": emb, "unit_weight": peso, "unit_weight_unit": un, "modo": modo, "data": data_val, "mes": mes, "ano": ano,
            "refrig": refrig}


def montar_payload(v: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    erros: list[str] = []
    if len(v["produto"]) < 2:
        erros.append("Informe o nome do alimento.")
    if not v["categoria"]:
        erros.append("Escolha a categoria.")
    if not v["quantity"]:
        erros.append("Informe a quantidade de unidades.")
    if not v["unit_weight"]:
        erros.append("Informe o peso ou volume de cada unidade.")
    if v["refrig"] is None:
        erros.append("Informe se o item exige refrigeração.")
    p: dict[str, Any] = {"produto": v["produto"], "categoria": v["categoria"], "quantity": v["quantity"], "unit": v["unit"], "unit_weight": v["unit_weight"],
                         "unit_weight_unit": v["unit_weight_unit"], "exige_refrigeracao": v["refrig"] == "Sim"}
    if v["modo"] == "Data exata":
        if v["data"] is None:
            erros.append("Informe a data de validade.")
        else:
            p["validade_data"] = v["data"].isoformat()
    else:
        if not v["mes"] or not v["ano"]:
            erros.append("Informe o mês e o ano da validade.")
        else:
            p["validade_mes_ano"] = f"{v['mes']}/{v['ano']}"
    return (None, erros) if erros else (p, [])


# ------------------------------------------------------------------ passo 1 · itens
def cartao_item(cli: ApiClient, did: str, it: dict, editavel: bool = True) -> None:
    sugerido = it.get("entry_source") == "TEXTO_SUGERIDO" and "revisao_do_item" in (it.get("pending_fields") or [])
    with st.container(border=True):
        st.markdown(f"**{esc(it.get('produto')) or 'Item sem nome'}** · {CATEGORIAS.get(it.get('categoria'), it.get('categoria') or 'categoria a informar')}")
        st.write(item_linha(it))
        refrig = {True: "exige refrigeração", False: "sem refrigeração", None: "refrigeração a informar"}[it.get("exige_refrigeracao")]
        st.caption(f"{item_validade(it)} · {refrig}")
        if sugerido:
            st.warning("Item sugerido a partir do seu texto: confira os dados e confirme.")
        faltam = [c for c in (it.get("missing_fields") or []) if c != "revisao_do_item"]
        if faltam:
            st.caption(f"Falta informar: {nomes_campos(faltam)}.")
        if editavel:
            b1, b2, _ = st.columns([2, 1, 1])
            if b1.button("Conferir e confirmar" if sugerido else "Editar", key=f"ed_{it['id']}"):
                st.session_state["editando"] = it["id"]
                st.rerun()
            if b2.button("Remover", key=f"rm_{it['id']}"):
                d = chamar(cli.delete_item, did, it["id"])
                if d:
                    st.session_state["draft"] = d
                    st.session_state.pop("editando", None)
                    st.rerun()


def formulario_edicao(cli: ApiClient, did: str, it: dict) -> None:
    sugerido = it.get("entry_source") == "TEXTO_SUGERIDO" and "revisao_do_item" in (it.get("pending_fields") or [])
    with st.container(border=True):
        st.markdown(f"**Editando:** {esc(it.get('produto')) or 'item'}")
        v = campos_item(f"ed{it['id']}", it)
        c1, c2, _ = st.columns([2, 1, 1])
        if c1.button("Salvar e confirmar item" if sugerido else "Salvar alterações", key=f"sv_{it['id']}", type="primary"):
            payload, erros = montar_payload(v)
            if erros:
                for e in erros:
                    st.error(e)
            else:
                if sugerido:
                    payload["confirm_item"] = True
                d = chamar(cli.patch_item, did, it["id"], payload)
                if d:
                    st.session_state["draft"] = d
                    st.session_state.pop("editando", None)
                    st.rerun()
        if c2.button("Cancelar", key=f"cc_{it['id']}"):
            st.session_state.pop("editando", None)
            st.rerun()


def bloco_texto(cli: ApiClient) -> None:
    with st.expander("Preencher a partir de um texto (opcional)"):
        st.caption("Cole uma lista com um item por linha (nome, quantidade, peso e validade). Vamos **sugerir** os itens; você confere cada um antes de enviar.")
        texto = st.text_area("Texto com os itens", max_chars=2000, height=120, key=f"texto_lote_{st.session_state.get('nonce', 0)}")
        if st.button("Sugerir itens a partir do texto", disabled=len(texto.strip()) < 3):
            d = garantir_rascunho(cli)
            if d:
                r = chamar(cli.items_from_text, d["id"], texto.strip())
                if r:
                    st.session_state["draft"] = r
                    st.session_state["nonce"] = st.session_state.get("nonce", 0) + 1
                    st.rerun()


def resumo_total(d: dict) -> None:
    r = d["resumo"]
    c1, c2 = st.columns(2)
    c1.metric("Total da doação", fmt_kg(r.get("quantity_kg")) if r.get("n_items") else "—")
    c2.metric("Validade mais próxima", fmt_date(r.get("expires_at")) if r.get("expires_at") else "—")
    if r.get("incomplete_weight"):
        st.caption("O total está incompleto: há item sem peso.")
    if any(i.get("weight_estimated") for i in d["items"]):
        st.caption("O total inclui **peso estimado** (líquidos convertidos em kg). Confira o peso real se souber.")
    for a in d.get("alertas", []):
        st.info(limpar(a))


def passo_itens(cli: ApiClient) -> None:
    d = st.session_state.get("draft")
    did = d["id"] if d else None
    bloco_texto(cli)
    d = st.session_state.get("draft")
    did = d["id"] if d else None
    itens = d["items"] if d else []
    st.subheader(f"Itens da doação ({len(itens)})" if itens else "Itens da doação")
    if not itens:
        st.caption("Nenhum item ainda. Adicione o primeiro item abaixo.")
    for it in itens:
        if st.session_state.get("editando") == it["id"]:
            formulario_edicao(cli, did, it)
        else:
            cartao_item(cli, did, it)
    if d and itens:
        resumo_total(d)
    st.subheader("Adicionar item")
    nonce = st.session_state.get("nonce", 0)
    v = campos_item(f"novo{nonce}")
    if st.button("Adicionar item", type="primary", key=f"add_{nonce}"):
        payload, erros = montar_payload(v)
        if erros:
            for e in erros:
                st.error(e)
        else:
            dr = garantir_rascunho(cli)
            if dr:
                r = chamar(cli.add_item, dr["id"], payload)
                if r:
                    st.session_state["draft"] = r
                    st.session_state["nonce"] = nonce + 1
                    st.rerun()
    st.divider()
    if st.button("Continuar para a retirada →", disabled=not itens):
        st.session_state["passo"] = 2
        st.rerun()


# ------------------------------------------------------------------ passo 2 · retirada
def passo_retirada(cli: ApiClient) -> None:
    d = st.session_state["draft"]
    j = d.get("janela_retirada") or {}
    st.subheader("Quando podemos retirar?")
    mask = int(j.get("dias_mask") or 0)
    dias_sel = st.multiselect("Dias da semana", DIAS, default=[DIAS[i] for i in range(7) if (mask >> i) & 1], key="ret_dias")
    ops = horas_opcoes()
    ini0 = min(ops, key=lambda h: abs(h - float(j.get("inicio_h") or 8)))
    fim0 = min(ops, key=lambda h: abs(h - float(j.get("fim_h") or 17)))
    c1, c2 = st.columns(2)
    ini = c1.selectbox("A partir de", ops, index=ops.index(ini0), format_func=hora_txt, key="ret_ini")
    fim = c2.selectbox("Até", ops, index=ops.index(fim0), format_func=hora_txt, key="ret_fim")
    alerg = st.checkbox("O lote pode conter alérgenos (ex.: glúten, leite, ovo, amendoim)", value=bool(d.get("contem_alergenico")), key="ret_alerg")
    b1, b2, _ = st.columns([1, 2, 1])
    if b1.button("← Itens"):
        st.session_state["passo"] = 1
        st.rerun()
    if b2.button("Salvar e continuar →", type="primary"):
        if not dias_sel:
            st.error("Escolha ao menos um dia da semana.")
        elif fim <= ini:
            st.error("O horário final precisa ser depois do inicial.")
        else:
            r = chamar(cli.patch_draft, d["id"], {"dias_retirada": [DIAS.index(x) for x in dias_sel], "janela_retirada_inicio_h": float(ini), "janela_retirada_fim_h": float(fim),
                                                  "contem_alergenico": alerg})
            if r:
                st.session_state["draft"] = r
                st.session_state["passo"] = 3
                st.rerun()


# ------------------------------------------------------------------ passo 3 · revisar e enviar
def pendencias(d: dict) -> list[str]:
    out = []
    for it in d["items"]:
        faltam = [c for c in (it.get("missing_fields") or [])]
        if faltam:
            out.append(f"**{esc(it.get('produto')) or 'Item'}**: falta {nomes_campos(faltam)}")
        if it.get("expires_at") and (dias_ate(it["expires_at"]) or 0) < 0:
            out.append(f"**{esc(it.get('produto')) or 'Item'}** está com a validade vencida: corrija ou remova o item.")
    return out


def passo_revisar(cli: ApiClient) -> None:
    d = st.session_state["draft"]
    r = d["resumo"]
    st.subheader("Revise antes de enviar")
    for it in d["items"]:
        st.markdown(f"• **{esc(it.get('produto'))}** — {item_linha(it)} · {item_validade(it)}")
    c1, c2 = st.columns(2)
    c1.metric("Total", fmt_kg(r.get("quantity_kg")))
    c2.metric("Validade mais próxima", fmt_date(r.get("expires_at")) if r.get("expires_at") else "—")
    if r.get("expires_at"):
        st.warning(f"A validade mais próxima define o prazo de **todo o lote**: {prazo_texto(r['expires_at'])}.")
    st.write(f"**Refrigeração:** {'sim, ao menos um item exige' if r.get('exige_refrigeracao') else 'não'}  \n**Retirada:** {janela_texto(d.get('janela_retirada'))}  \n"
             f"**Alérgenos:** {'o lote pode conter' if d.get('contem_alergenico') else 'não informado'}")
    for a in d.get("alertas", []):
        st.info(limpar(a))
    pend = pendencias(d)
    for p in pend:
        st.warning(p)
    if pend:
        st.caption("Volte ao passo 1 para conferir os itens indicados.")
    st.caption(d.get("aviso", ""))
    ok = st.checkbox("Confirmo que as informações estão corretas e que sou responsável por elas.", key="conf_envio")
    b1, b2 = st.columns([1, 2])
    if b1.button("← Voltar"):
        st.session_state["passo"] = 2
        st.rerun()
    if b2.button("Enviar doação", type="primary", disabled=not ok or not d["items"]):
        enviar(cli, d["id"])


def enviar(cli: ApiClient, did: str) -> None:
    """Revisar e enviar = finalizar + buscar ONG numa ação só (depois da confirmação marcada na tela)."""
    f = chamar(cli.finalize, did)
    if f is None:
        return
    st.session_state["draft"] = f
    if f["status"] != "READY":
        st.error("A doação ainda não pode ser enviada.")
        motivo = limpar(f.get("block_reason"))
        if motivo:
            st.write(motivo[:1].upper() + motivo[1:] + ("" if motivo.endswith(".") else "."))
        for p in pendencias(f):
            st.write("• " + p)
        st.caption("Volte ao passo 1, corrija os itens indicados e envie de novo.")
        return
    mt = chamar(cli.create_match, did, 5)
    if mt is None:
        st.info("Sua doação está pronta, mas não conseguimos buscar uma ONG agora. Tente enviar de novo em instantes.")
        return
    atual = chamar(cli.get_donation, did)
    st.session_state["enviada"] = {"donation": atual or f, "situacao": mt.get("situacao")}
    for k in ("draft", "editando", "bloqueada"):
        st.session_state.pop(k, None)
    st.session_state["passo"] = 1
    st.rerun()


# ------------------------------------------------------------------ página "Nova doação"
def pagina_nova(cli: ApiClient, me: dict) -> None:
    st.header("Nova doação")
    env = st.session_state.get("enviada")
    if env:
        st.success("Doação enviada! Procuramos uma ONG para receber.")
        st.write(f"Situação: **{env.get('situacao') or 'enviada'}**")
        st.caption("Acompanhe o andamento em **Minhas doações**.")
        c1, c2, _ = st.columns([1, 1, 1])
        c1.button("Criar outra doação", on_click=novo_rascunho)
        if c2.button("Ver minhas doações"):
            st.session_state["ir_para"] = "Minhas doações"
            st.session_state.pop("enviada", None)
            st.rerun()
        return
    if st.session_state.get("bloqueada"):
        st.warning("Esta doação já foi enviada e não pode mais ser alterada. Para mudar algo, crie uma nova doação.")
        st.button("Criar nova doação", on_click=novo_rascunho, type="primary")
        return
    passo = st.session_state.get("passo", 1)
    if passo > 1 and not st.session_state.get("draft"):
        passo = st.session_state["passo"] = 1
    st.markdown(" › ".join(f"**{i + 1}. {n}**" if i + 1 == passo else f"{i + 1}. {n}" for i, n in enumerate(PASSOS)))
    st.progress(passo / 3)
    {1: passo_itens, 2: passo_retirada, 3: passo_revisar}[passo](cli)


# ------------------------------------------------------------------ página "Minhas doações"
def evento_texto(e: dict) -> str | None:
    return EVENTO_DOADOR.get(e.get("event_type"))


def editavel_na_tela(d: dict) -> bool:
    """Só rascunhos do fluxo por itens abrem no editor (doações do fluxo antigo de lote único não têm itens detalhados e não são editáveis aqui)."""
    return doacao_pendente_envio(d) and (not d["items"] or any(i.get("entry_source") for i in d["items"]))


def cartao_doacao(cli: ApiClient, d: dict) -> None:
    rotulo, cor = destaque_situacao(d.get("situacao"))
    r = d["resumo"]
    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        c1.markdown(f"**Doação de {fmt_date(d.get('created_at'))}**")
        c2.markdown(colorir(rotulo, cor))
        for it in d["items"][:6]:
            st.caption(f"• {esc(it.get('produto')) or CATEGORIAS.get(it.get('categoria'), 'Item')} — {item_linha(it)}")
        if len(d["items"]) > 6:
            st.caption(f"… e mais {len(d['items']) - 6} item(ns)")
        st.write(f"Total: **{fmt_kg(r.get('quantity_kg'))}** · validade mais próxima: **{fmt_date(r.get('expires_at'))}**")
        st.caption(d.get("situacao") or "")
        if d.get("ong_aceita"):
            st.write(f"ONG que aceitou: **{d['ong_aceita']}**")
        st.caption(selo_origem(d.get("data_origin")))
        if editavel_na_tela(d):
            if st.button("Continuar editando", key=f"cont_{d['id']}"):
                st.session_state.update(draft=d, passo=1, ir_para="Nova doação")
                st.session_state.pop("bloqueada", None)
                st.session_state.pop("enviada", None)
                st.rerun()
        if d.get("match_id") and st.toggle("Ver histórico", key=f"hist_{d['id']}"):
            ev = chamar(cli.events, d["match_id"])
            linhas = [(e["at"], evento_texto(e)) for e in (ev or {}).get("events", []) if evento_texto(e)]
            for at, txt in linhas:
                st.caption(f"{fmt_datetime(at)} — {txt}")
            if not linhas:
                st.caption("Ainda sem movimentações.")


def pagina_minhas(cli: ApiClient, me: dict) -> None:
    st.header("Minhas doações")

    def corpo() -> None:
        try:
            lista = cli.list_donations(limit=50)
        except ApiError as e:
            st.error(e.friendly)
            return
        except httpx.HTTPError:
            st.error("Não conseguimos atualizar agora. Tentaremos de novo.")
            return
        st.caption("Atualização automática a cada 5 segundos.")
        if not lista:
            st.info("Você ainda não cadastrou doações. Use **Nova doação** no menu.")
        for d in lista:
            cartao_doacao(cli, d)

    st.fragment(run_every=5)(corpo)()
