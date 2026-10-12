"""Telas da ONG (Fase 3 Parte 1 · Etapa B): "Propostas recebidas" e "Histórico".
A ONG vê a doação que lhe foi proposta (itens, validade, refrigeração, retirada), a própria distância e a "Análise da IA" em TEXTO — nunca scores, ranking nem outras ONGs."""
from __future__ import annotations

import httpx
import streamlit as st

from app.api_client import ApiClient, ApiError
from app.ui_common import (CATEGORIAS, EVENTO_ONG, HISTORICO_ONG, colorir, fmt_date, fmt_datetime, fmt_kg, esc, fmt_num, item_linha, janela_texto, limpar, prazo_texto, selo_origem)


def chamar(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ApiError as e:
        st.error(e.friendly)
    except httpx.HTTPError:
        st.error("Não conseguimos falar com o serviço agora. Tente de novo em instantes.")
    return None


def itens_e_lote(mt: dict) -> None:
    d = mt["donation"]
    r = d["resumo"]
    c1, c2 = st.columns(2)
    c1.metric("Total", fmt_kg(r.get("quantity_kg")))
    c2.metric("Validade mais próxima", fmt_date(r.get("expires_at")) if r.get("expires_at") else "—")
    if r.get("expires_at"):
        st.warning(f"Prazo: {prazo_texto(r['expires_at'])}. Todo o lote deve ser retirado antes dessa data.")
    for it in d["items"]:
        cat = CATEGORIAS.get(it.get("categoria"), it.get("categoria") or "")
        st.caption(f"• **{esc(it.get('produto')) or 'Item'}** ({cat}) — {item_linha(it)} · validade {fmt_date(it.get('expires_at'))}")
    refrig = "exige refrigeração" if r.get("exige_refrigeracao") else "sem refrigeração"
    st.write(f"**Refrigeração:** {refrig}  \n**Retirada:** {janela_texto(d.get('janela_retirada'))}  \n**Alérgenos:** {'o lote pode conter' if d.get('contem_alergenico') else 'não informado'}")
    doador = d.get("doador") or {}
    if doador.get("tipo"):
        st.caption(f"Doador: {doador['tipo'].lower()}{(' · porte ' + str(doador['porte']).lower()) if doador.get('porte') else ''}")


def distancia(mt: dict) -> None:
    my = mt.get("my_candidacy")
    if not my or my.get("dist_km") is None:
        return
    st.write(f"**Distância até o doador:** cerca de {fmt_num(my['dist_km'], 1)} km em linha reta")
    if my.get("distancia_aproximada"):
        st.caption("⚠ Distância aproximada: a localização do doador está no nível do município.")


def analise_ia(mt: dict) -> None:
    with st.expander("Análise da IA"):
        for linha in mt["donation"].get("analise", []):
            st.write("• " + limpar(linha))
        for linha in (mt.get("my_candidacy") or {}).get("explicacao", []):
            st.write("• " + esc(linha))
        st.caption(esc(mt["donation"].get("aviso", "")))


def acao_com_confirmacao(cli: ApiClient, mt: dict) -> None:
    mid = mt["id"]
    est = st.session_state.get(f"conf_{mid}")
    if est is None:
        c1, c2, _ = st.columns([1, 1, 1])
        if c1.button("Aceitar", key=f"ok_{mid}", type="primary"):
            st.session_state[f"conf_{mid}"] = "aceitar"
            st.rerun()
        if c2.button("Recusar", key=f"no_{mid}"):
            st.session_state[f"conf_{mid}"] = "recusar"
            st.rerun()
        return
    aceitar = est == "aceitar"
    st.warning("Confirmar que a sua ONG **aceita** esta doação?" if aceitar else "Confirmar que a sua ONG **recusa** esta doação? A proposta passará para outra ONG.")
    c1, c2, _ = st.columns([1, 1, 1])
    if c1.button("Sim, aceitar" if aceitar else "Sim, recusar", key=f"y_{mid}", type="primary"):
        r = chamar(cli.respond, mid, aceitar)
        st.session_state.pop(f"conf_{mid}", None)
        if r is not None:
            st.rerun()
    if c2.button("Voltar", key=f"n_{mid}"):
        st.session_state.pop(f"conf_{mid}", None)
        st.rerun()


def cartao_proposta(cli: ApiClient, mt: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**Nova proposta de doação** · {colorir('Aguardando você', 'orange')}")
        itens_e_lote(mt)
        distancia(mt)
        if mt.get("proposal_expires_at"):
            st.write(f"**Responder até:** {fmt_datetime(mt['proposal_expires_at'])}")
        analise_ia(mt)
        st.caption(selo_origem(mt.get("data_origin")))
        acao_com_confirmacao(cli, mt)


def cartao_coleta(cli: ApiClient, mt: dict) -> None:
    mid = mt["id"]
    with st.container(border=True):
        st.markdown(f"**Doação aceita — aguardando a coleta** · {colorir('Aceita', 'green')}")
        itens_e_lote(mt)
        est = st.session_state.get(f"out_{mid}")
        if est is None:
            c1, c2, _ = st.columns([1, 1, 1])
            if c1.button("Coleta concluída", key=f"col_{mid}", type="primary"):
                st.session_state[f"out_{mid}"] = "COLLECTED"
                st.rerun()
            if c2.button("Coleta não concluída", key=f"fal_{mid}"):
                st.session_state[f"out_{mid}"] = "FAILED"
                st.rerun()
        else:
            st.warning("Registrar que a coleta foi **concluída**?" if est == "COLLECTED" else "Registrar que a coleta **não foi concluída**?")
            c1, c2, _ = st.columns([1, 1, 1])
            if c1.button("Sim, registrar", key=f"oy_{mid}", type="primary"):
                r = chamar(cli.outcome, mid, est)
                st.session_state.pop(f"out_{mid}", None)
                if r is not None:
                    st.rerun()
            if c2.button("Voltar", key=f"on_{mid}"):
                st.session_state.pop(f"out_{mid}", None)
                st.rerun()


def pagina_propostas(cli: ApiClient, me: dict) -> None:
    st.header("Propostas recebidas")

    def corpo() -> None:
        try:
            props = [x for x in cli.list_matches("PROPOSED") if x.get("awaiting_my_response")]
            aceitas = [x for x in cli.list_matches("ACCEPTED") if x.get("mine_now")]
        except ApiError as e:
            st.error(e.friendly)
            return
        except httpx.HTTPError:
            st.error("Não conseguimos atualizar agora. Tentaremos de novo.")
            return
        st.caption("Atualização automática a cada 5 segundos.")
        if not props:
            st.info("Nenhuma proposta aguardando a sua resposta.")
        for mt in props:
            cartao_proposta(cli, mt)
        if aceitas:
            st.subheader("Aceitas — aguardando coleta")
            for mt in aceitas:
                cartao_coleta(cli, mt)

    st.fragment(run_every=5)(corpo)()


def pagina_historico(cli: ApiClient, me: dict) -> None:
    st.header("Histórico")

    def corpo() -> None:
        try:
            todas = cli.list_matches(None, limit=50)
        except ApiError as e:
            st.error(e.friendly)
            return
        except httpx.HTTPError:
            st.error("Não conseguimos atualizar agora. Tentaremos de novo.")
            return
        hist = [x for x in todas if not x.get("awaiting_my_response") and not (x.get("mine_now") and x.get("status") == "ACCEPTED")] + \
               [x for x in todas if x.get("mine_now") and x.get("status") == "ACCEPTED"]
        if not hist:
            st.info("Ainda não há propostas respondidas.")
        for mt in hist:
            rot, cor = HISTORICO_ONG.get(mt.get("my_last_event") or "", ("—", "gray"))
            if mt.get("mine_now") and mt.get("status") == "ACCEPTED":
                rot, cor = "Aceita — aguardando coleta", "green"
            with st.container(border=True):
                r = mt["donation"]["resumo"]
                c1, c2 = st.columns([3, 2])
                c1.markdown(f"**Proposta de {fmt_date(mt.get('created_at'))}**")
                c2.markdown(colorir(rot, cor))
                nomes = ", ".join(esc(i.get("produto")) or "item" for i in mt["donation"]["items"][:4])
                st.caption(f"{nomes} · total {fmt_kg(r.get('quantity_kg'))} · validade mais próxima {fmt_date(r.get('expires_at'))}")
                if mt.get("my_last_event_at"):
                    st.caption(f"Última movimentação sua: {fmt_datetime(mt['my_last_event_at'])}")
                st.caption(selo_origem(mt.get("data_origin")))
                if st.toggle("Ver movimentações", key=f"hv_{mt['id']}"):
                    ev = chamar(cli.events, mt["id"])
                    for e in (ev or {}).get("events", []):
                        if e["event_type"] in EVENTO_ONG:
                            st.caption(f"{fmt_datetime(e['at'])} — {EVENTO_ONG[e['event_type']]}")

    st.fragment(run_every=5)(corpo)()
