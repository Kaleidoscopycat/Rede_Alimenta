"""Área "Visão técnica (admin)" (Fase 3 Parte 1 · Etapa B): preserva as telas técnicas da Fase 2 — ranking, scores, explicações, regras eliminatórias, match_events — e acrescenta o aviso de LOTE MISTO.
Somente o ADMIN chega aqui (a barreira é a API: /matches/{id}/ranking e /model/info respondem 403 aos demais perfis; cada acesso é auditado como `admin.access`).
O dashboard completo do administrador é a Fase 3 Parte 2."""
from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st

from app.api_client import ApiClient, ApiError
from app.ui_common import fmt_date, fmt_datetime, fmt_kg, selo_origem

LIMITACAO_LOTE_MISTO = ("Lote misto: o modelo de ranking foi treinado e avaliado somente com lotes SIMULADOS de uma única categoria; o desempenho em lotes de várias categorias é DESCONHECIDO. "
                        "O ML_SCORE usa a categoria predominante (maior peso); a elegibilidade exige que a ONG aceite TODAS as categorias do lote.")


def score_table(ranking: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{"#": r["posicao"], "ONG (pseudônimo)": r["ong_id"], "tipo": r["ong_tipo"], "UF": r["uf"], "dist. linha reta (km)": r["dist_km"],
                          "precisão da localização": r["location_precision"] + (" ⚠ aproximada" if r["distancia_aproximada"] else ""),
                          "ML_SCORE": r["ML_SCORE"], "BUSINESS_RULE_SCORE": r["BUSINESS_RULE_SCORE"], "DISTANCE_SCORE": r["DISTANCE_SCORE"], "FINAL_SCORE": r["FINAL_SCORE"]}
                         for r in ranking])


def aviso_lote_misto(mt: dict) -> None:
    don = mt.get("donation") or {}
    rs = don.get("resumo") or {}
    if rs.get("is_mixed_batch"):
        st.warning(f"⚠ **LOTE MISTO** ({', '.join(rs.get('categories', []))}). {LIMITACAO_LOTE_MISTO}")


def render_ranking(mt: dict) -> None:
    st.markdown(f"**Match** `{mt['id']}` — estado **{mt['status']}** — {selo_origem(mt.get('data_origin'))}")
    aviso_lote_misto(mt)
    don = mt.get("donation") or {}
    rs = don.get("resumo") or {}
    if rs:
        st.write(f"Lote: **{', '.join(rs.get('categories', []))}** · {fmt_kg(rs.get('quantity_kg'))} · {rs.get('n_items')} item(ns) · validade mais próxima {fmt_date(rs.get('expires_at'))}")
    if mt.get("current_org"):
        st.write(f"Proposta atual: **{mt['current_org']}** (posição {mt.get('current_position')})" + (f" — responder até {fmt_datetime(mt['proposal_expires_at'])}" if mt.get("proposal_expires_at") else ""))
    lat = mt.get("latency_ms") or {}
    if lat:
        st.caption(f"Latência do ranking: {lat.get('total_ms')} ms (busca espacial {lat.get('busca_espacial_ms')} ms · elegibilidade {lat.get('elegibilidade_ms')} ms · ML {lat.get('ml_ms')} ms)")
    el = mt.get("eligibility") or {}
    st.markdown("**Regras eliminatórias aplicadas** (contagens por regra no raio; uma ONG pode reprovar em mais de uma)")
    st.write(f"No raio: {el.get('n_in_radius')} · elegíveis: {el.get('n_eligible')}")
    if el.get("por_regra"):
        cat = el.get("rules_catalog", {})
        st.dataframe(pd.DataFrame([{"regra": k, "descrição": cat.get(k, ""), "ONGs reprovadas": v} for k, v in el["por_regra"].items()]), hide_index=True, use_container_width=True)
    for a in el.get("alertas", []):
        st.info(a)
    if mt.get("ranking"):
        st.markdown("**Ranking explicado** — scores separados (FINAL = ponderação de ML + regras + distância; pesos são premissas)")
        st.dataframe(score_table(mt["ranking"]), hide_index=True, use_container_width=True)
        for r in mt["ranking"]:
            with st.expander(f"#{r['posicao']} {r['ong_id']} — FINAL {r['FINAL_SCORE']}"):
                for line in r["explicacao"]:
                    st.write("• " + line)
                st.caption(f"location_precision={r['location_precision']} · platform_status={r['platform_status']} · declarado: {r['profile_origin']}")
    else:
        st.info("Nenhuma ONG elegível/candidata.")
    st.caption(mt.get("aviso", ""))


def detalhes_da_doacao(mt: dict) -> None:
    don = mt.get("donation") or {}
    with st.expander("Doação — itens e saída do parser (técnico)"):
        for a in don.get("alertas", []):
            st.info(a)
        itens = don.get("items", [])
        if itens:
            st.dataframe(pd.DataFrame([{"produto": i.get("produto"), "categoria": i.get("categoria"), "kg": i.get("quantity_kg"), "base do peso": i.get("weight_basis"), "origem da entrada": i.get("entry_source"),
                                        "validade": i.get("expires_at"), "pendências": ", ".join(i.get("pending_fields") or [])} for i in itens]), hide_index=True, use_container_width=True)
        if don.get("fields"):
            st.caption(f"Fluxo de lote único — saída do parser (versão {don.get('parser_version')}): visível apenas ao ADMIN.")
            st.json(don["fields"], expanded=False)


def pagina_tecnica(cli: ApiClient, me: dict) -> None:
    st.header("Visão técnica (admin)")
    st.caption("Área técnica: scores, ranking e explicações. Cada consulta fica registrada em auditoria (`admin.access`).")
    try:
        lista = cli.list_matches(None, limit=100)
    except ApiError as e:
        st.error(e.friendly)
        return
    except httpx.HTTPError:
        st.error("Não conseguimos atualizar agora. Tente de novo.")
        return
    if not lista:
        st.info("Ainda não há matches. Gere um pelo fluxo do doador (ou pela API).")
    else:
        opcoes = {m["id"]: f"{fmt_datetime(m.get('created_at'))} · {m['status']} · {m['id'][:8]}" for m in lista}
        mid = st.selectbox("Match", list(opcoes), format_func=opcoes.get, key="adm_match")
        if st.button("Atualizar", key="adm_refresh"):
            st.rerun()
        try:
            mt = cli.ranking(mid)
            render_ranking(mt)
            detalhes_da_doacao(mt)
            ev = cli.events(mid)
            st.markdown("**Histórico de estados (match_events)**")
            st.dataframe(pd.DataFrame([{"quando": e["at"], "evento": e["event_type"], "ONG": e.get("ong_id"), "pos.": e.get("rank_position"), "s desde o anterior": e["seconds_since_previous"],
                                        "ator": e["actor_type"]} for e in ev["events"]]), hide_index=True, use_container_width=True)
        except ApiError as e:
            st.error(e.friendly)
    with st.expander("Modelo e parser (técnico)"):
        try:
            st.json(cli.model_info(), expanded=False)
        except ApiError as e:
            st.error(e.friendly)
