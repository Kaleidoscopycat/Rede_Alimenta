"""Interface operacional mínima (Streamlit) — Fase 2 Parte 1. Fala SOMENTE com a API HTTP (nunca com o banco).
Página A: doador cadastra doação (texto livre → parser → confirmação → match → ranking explicado).
Página B: ONG responde propostas (aceitar/recusar), com atualização periódica (polling) e histórico de estados.
Dashboards/mapas/KPIs ficam para a Fase 3.
Autenticação: cole o TOKEN do seu usuário na barra lateral (nada é gravado no código/repositório). Limitação: token estático, sem TLS/rate limit nesta fase."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Portabilidade (Windows/Linux/Docker): o Streamlit/`python scripts/x.py` só põem a pasta do script em sys.path; a raiz do projeto
# precisa estar lá para `from app...`/`from database...`. Sem depender de PYTHONPATH nem de `python -m`. Não duplica a entrada.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.api_client import ApiClient, ApiError  # noqa: E402

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
CATEGORIAS = ["HORT_FOLHOSAS", "HORT_RAIZES", "HORT_FRUTOS", "FRUTAS", "PANIFICADOS", "CARNES_PESCADOS", "LATICINIOS_OVOS", "REFEICOES_PRONTAS", "GRAOS_CEREAIS", "INDUSTRIALIZADOS", "BEBIDAS"]
PERECIBILIDADES = ["NAO_PERECIVEL", "PERECIVEL_BAIXO_RISCO", "PERECIVEL_REFRIGERADO_CONGELADO", "PRONTO_ALTO_RISCO"]
AVISO_SIM = ("⚠️ **Dados simulados com limitações conhecidas.** Capacidade, horários e refrigeração das ONGs, doadores, lotes e desfechos são SIMULADOS (R1 – volume por banco – não passa; "
             "R6 – o simulador é pessimista). Taxas, volumes e tempos simulados **não representam o mundo real**. Entidades listadas são registros de fontes públicas (licenças em revisão) e "
             "**não são clientes** da plataforma.")
AVISO_PARSER = "ℹ️ Parser treinado em **texto simulado**; limiar de confiança calibrado sobre texto simulado; **sem conjunto MANUALLY_LABELED** (o rascunho de IA não é rotulagem manual)."
AVISO_AUTH = "🔐 Autenticação mínima: token estático por usuário; sem TLS nem limite de requisições nesta fase."
AVISO_LICENCA = "dados públicos usados para fins acadêmicos; licença de reutilização não confirmada"
PEND = "PENDING_CONFIRMATION"


def make_client(token: str) -> ApiClient:
    return ApiClient(API_BASE_URL, token)


def origin_badge(origin: str | None) -> str:
    return {"SIMULATED": "🟧 SIMULADO (data_origin=SIMULATED)", "USER_ENTERED": "🟩 USER_ENTERED (entrada real)", "PUBLIC": "🟦 PUBLIC (fonte pública)"}.get(origin or "", origin or "—")


def show_error(e: ApiError) -> None:
    st.error(f"Erro da API ({e.status}): {e.message}")


def banner() -> None:
    st.warning(AVISO_SIM)
    st.caption(f"📄 Fonte dos registros de ONGs, municípios e indicadores: bases públicas (atribuição às fontes em docs/data/DATA_LICENSES.md). **{AVISO_LICENCA.capitalize()}.**")
    st.caption(AVISO_PARSER)
    st.caption(AVISO_AUTH)


def score_table(ranking: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{"#": r["posicao"], "ONG (pseudônimo)": r["ong_id"], "tipo": r["ong_tipo"], "UF": r["uf"], "dist. linha reta (km)": r["dist_km"],
                          "precisão da localização": r["location_precision"] + (" ⚠ aproximada" if r["distancia_aproximada"] else ""),
                          "ML_SCORE": r["ML_SCORE"], "BUSINESS_RULE_SCORE": r["BUSINESS_RULE_SCORE"], "DISTANCE_SCORE": r["DISTANCE_SCORE"], "FINAL_SCORE": r["FINAL_SCORE"]}
                         for r in ranking])


def render_match(mt: dict) -> None:
    st.markdown(f"**Match** `{mt['id']}` — estado **{mt['status']}** — {origin_badge(mt['data_origin'])}")
    if mt.get("situacao"):  # visão do DOADOR: só a situação (nunca ranking, scores ou ONGs não escolhidas)
        st.write(f"Situação: **{mt['situacao']}**" + (f" — ONG que aceitou: **{mt['ong_aceita']}**" if mt.get("ong_aceita") else ""))
    if mt.get("current_org"):
        st.write(f"Proposta atual: **{mt['current_org']}** (posição {mt['current_position']})" + (f" — responder até {mt['proposal_expires_at']}" if mt.get("proposal_expires_at") else ""))
    lat = mt.get("latency_ms", {})
    if lat:
        st.caption(f"Latência do ranking: {lat.get('total_ms')} ms (busca espacial {lat.get('busca_espacial_ms')} ms · elegibilidade {lat.get('elegibilidade_ms')} ms · ML {lat.get('ml_ms')} ms)")
    if "ranking" in mt:
        el = mt.get("eligibility", {})
        st.markdown("**Regras eliminatórias aplicadas** (contagens por regra no raio; uma ONG pode reprovar em mais de uma)")
        st.write(f"No raio: {el.get('n_in_radius')} · elegíveis: {el.get('n_eligible')}")
        if el.get("por_regra"):
            cat = mt.get("eligibility", {}).get("rules_catalog", {})
            st.dataframe(pd.DataFrame([{"regra": k, "descrição": cat.get(k, ""), "ONGs reprovadas": v} for k, v in el["por_regra"].items()]), hide_index=True, use_container_width=True)
        for a in el.get("alertas", []):
            st.info(a)
        if mt["ranking"]:
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


def fragment_poll(fn, seconds: int = 5):
    return st.fragment(run_every=seconds)(fn)


# ------------------------------------------------------------------ Página A — doador
def page_donor(cli: ApiClient, me: dict) -> None:
    st.header("A · Cadastrar doação (doador)")
    texto = st.text_area("Descreva o lote em texto livre (até 500 caracteres)", max_chars=500, key="texto_lote", height=90)
    if st.button("Analisar texto (parser)", disabled=not texto.strip()):
        try:
            st.session_state["parse"] = cli.parse(texto)
            st.session_state.pop("donation", None)
            st.session_state.pop("match_id", None)
        except ApiError as e:
            show_error(e)
    p = st.session_state.get("parse")
    if p:
        st.caption(f"parser_version `{p['parser_version']}` · τ={p['confidence_threshold']} ({p['threshold_note']}) · dados de treino: **{p['training_data_origin']}**")
        st.caption(p["aviso"])
        for a in p["alerts"]:
            st.warning(a)
        rows = [{"campo": k, "valor extraído": f["value"], "confiança": f["confidence"], "situação": ("🔶 PENDENTE" if f["status"] == PEND else "❌ AUSENTE" if f["status"] == "MISSING" else "✅ OK"),
                 "observação": f.get("note")} for k, f in p["fields"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        f = p["fields"]
        st.markdown("**Campos editáveis** — você pode corrigir qualquer valor extraído")
        c1, c2 = st.columns(2)
        cat0 = f["categoria"]["value"]
        categoria = c1.selectbox("Categoria", CATEGORIAS, index=CATEGORIAS.index(cat0) if cat0 in CATEGORIAS else 0, key="e_cat")
        refrig = c2.checkbox("Exige refrigeração", value=bool(f["exige_refrigeracao"]["value"]), key="e_ref")
        dias0 = f["dias_ate_validade"]["value"]
        dias = c1.number_input("Dias até a validade (vazio/0 = vence hoje; negativo = vencido)", value=int(dias0) if dias0 is not None else 0, step=1, key="e_dias",
                               help="Se o texto não traz validade, o match fica BLOQUEADO até você informar.")
        kg0 = f["quantidade_kg"]["value"]
        kg = c2.number_input("Quantidade (kg)", min_value=0.0, value=float(kg0) if kg0 is not None else 0.0, step=1.0, key="e_kg")
        if st.button("Cadastrar doação"):
            payload: dict[str, Any] = {"texto": texto}
            # só envia como decisão do doador o que ele alterou em relação ao extraído
            if categoria != cat0:
                payload["categoria"] = categoria
            if refrig != bool(f["exige_refrigeracao"]["value"]):
                payload["exige_refrigeracao"] = refrig
            if dias0 is None and f["dias_ate_validade"]["status"] == "MISSING":
                pass
            elif int(dias) != int(dias0):
                payload["dias_ate_validade"] = int(dias)
            if kg and (kg0 is None or abs(kg - float(kg0)) > 1e-9):
                payload["quantidade_kg"] = float(kg)
            if dias0 is None and int(dias) != 0:
                payload["dias_ate_validade"] = int(dias)
            if kg0 is None and kg:
                payload["quantidade_kg"] = float(kg)
            try:
                st.session_state["donation"] = cli.create_donation(payload)
            except ApiError as e:
                show_error(e)
    d = st.session_state.get("donation")
    if d:
        st.divider()
        st.markdown(f"**Doação** `{d['id']}` — estado **{d['status']}** — {origin_badge(d['data_origin'])}")
        if d["block_reason"]:
            st.error(d["block_reason"])
        if d["quantity_kg"]:
            st.caption(f"≈ {d['refeicoes_equivalentes']} refeições (kg ÷ {d['premissa_kg_por_refeicao']}; premissa da equipe, configurável" + ("; em dados SIMULADOS isto é simulação)" if d["data_origin"] == "SIMULATED" else ")"))
        if d["status"] in ("PENDING_CONFIRMATION", "BLOCKED_NO_VALIDITY", "BLOCKED_EXPIRED"):
            st.markdown("**Confirmação do doador** — campos destacados abaixo exigem sua confirmação/correção antes do match")
            pend = d["pending_fields"]
            acc = [k for k in pend if st.checkbox(f"Confirmo o valor extraído de **{k}**: {d['fields'][k].get('final')}", key=f"acc_{k}", disabled=d['fields'][k].get('final') is None)]
            c1, c2 = st.columns(2)
            nv = c1.number_input("Corrigir dias até a validade", value=int(d["validity_days"]) if d["validity_days"] is not None else 0, step=1, key="c_dias")
            nk = c2.number_input("Corrigir quantidade (kg)", min_value=0.0, value=float(d["quantity_kg"] or 0.0), key="c_kg")
            if st.button("Confirmar / corrigir"):
                body: dict[str, Any] = {"accept_fields": [a for a in acc if d["fields"][a].get("final") is not None]}
                if d["validity_days"] is None or int(nv) != int(d["validity_days"]):
                    body["dias_ate_validade"] = int(nv)
                if nk and (d["quantity_kg"] is None or abs(nk - d["quantity_kg"]) > 1e-9):
                    body["quantidade_kg"] = float(nk)
                try:
                    st.session_state["donation"] = cli.confirm(d["id"], body)
                    st.rerun()
                except ApiError as e:
                    show_error(e)
        if d["status"] in ("READY", "NO_MATCH"):
            if st.button("Gerar match"):
                try:
                    mt = cli.create_match(d["id"], 5)
                    st.session_state["match_id"] = mt["id"]
                    st.session_state["donation"] = cli.get_donation(d["id"])
                except ApiError as e:
                    show_error(e)
    mid = st.session_state.get("match_id")
    if mid:
        st.divider()

        def poll():
            try:
                mt = cli.get_match(mid)
                render_match(mt)
                ev = cli.events(mid)
                st.markdown("**Histórico de estados (match_events)**")
                st.dataframe(pd.DataFrame([{"quando": e["at"], "evento": e["event_type"], "ONG": e.get("ong_id"), "pos.": e.get("rank_position"), "s desde o anterior": e["seconds_since_previous"],
                                            "ator": e["actor_type"]} for e in ev["events"]]), hide_index=True, use_container_width=True)
            except ApiError as e:
                show_error(e)
        fragment_poll(poll)()


# ------------------------------------------------------------------ Página B — ONG
def page_org(cli: ApiClient, me: dict) -> None:
    st.header("B · Responder proposta (ONG)")

    def poll():
        try:
            props = cli.list_matches("PROPOSED")
        except ApiError as e:
            show_error(e)
            return
        st.caption("Atualização automática a cada 5 s (polling).")
        if not props:
            st.info("Nenhuma proposta pendente para a sua organização.")
        for mt in props:
            d = mt["donation"]
            rs = d["resumo"]
            with st.container(border=True):
                st.markdown(f"**Proposta** `{mt['id']}` — {origin_badge(mt['data_origin'])}")
                st.write(f"Lote: **{', '.join(rs['categories'])}** · **{rs['quantity_kg']} kg** (≈ {rs['refeicoes_equivalentes']} refeições, kg ÷ {rs['premissa_kg_por_refeicao']}) · refrigeração: "
                         f"{'sim' if rs['exige_refrigeracao'] else 'não'} · validade mais próxima até {rs['expires_at']} · alérgenos: {'sim' if d['contem_alergenico'] else 'não/inf.'}")
                for it in d["items"]:
                    st.caption(f"• {it['produto']} — {it['quantity']} × {it['unit'] or 'un.'} de {it['unit_weight']} {it['unit_weight_unit']} = {it['quantity_kg']} kg · validade {it['expires_at']}")
                for line in d["analise"]:
                    st.write("🛈 " + line)
                st.caption(f"Doador: {d['doador']['tipo']} (município IBGE {d['doador']['municipio_ibge']}) · responder até {mt['proposal_expires_at']}")
                my = mt.get("my_candidacy")
                if my:
                    st.write(f"Distância em linha reta: {my['dist_km']} km" + (" (aproximada)" if my["distancia_aproximada"] else "") + f" · espera pela janela {my['espera_janela_h']} h · folga até a validade {my['folga_validade_h']} h")
                st.caption(d["aviso"])
                c1, c2, _ = st.columns([1, 1, 4])
                if c1.button("Aceitar", key=f"ok_{mt['id']}"):
                    try:
                        cli.respond(mt["id"], True)
                        st.rerun()
                    except ApiError as e:
                        show_error(e)
                if c2.button("Recusar", key=f"no_{mt['id']}"):
                    try:
                        cli.respond(mt["id"], False)
                        st.rerun()
                    except ApiError as e:
                        show_error(e)
                try:
                    ev = cli.events(mt["id"])
                    st.dataframe(pd.DataFrame([{"quando": e["at"], "evento": e["event_type"], "ator": e["actor_type"]} for e in ev["events"]]), hide_index=True,
                                 use_container_width=True)
                except ApiError:
                    pass
        acc = []
        try:
            acc = cli.list_matches("ACCEPTED")
        except ApiError:
            pass
        if acc:
            st.subheader("Aceitas — aguardando coleta")
            for mt in acc:
                with st.container(border=True):
                    st.write(f"`{mt['id']}` — {', '.join(mt['donation']['resumo']['categories'])} · {mt['donation']['resumo']['quantity_kg']} kg — {origin_badge(mt['data_origin'])}")
                    c1, c2, _ = st.columns([1, 1, 4])
                    if c1.button("Coleta concluída", key=f"col_{mt['id']}"):
                        cli.outcome(mt["id"], "COLLECTED")
                        st.rerun()
                    if c2.button("Coleta falhou", key=f"fal_{mt['id']}"):
                        cli.outcome(mt["id"], "FAILED")
                        st.rerun()
    fragment_poll(poll)()


def main() -> None:
    st.set_page_config(page_title="Rede Alimenta IA — operação", page_icon="🥕", layout="wide")
    st.title("Rede Alimenta IA — interface operacional mínima")
    banner()
    token = st.sidebar.text_input("Token do usuário", type="password", help="Cole o token entregue pelo administrador. Não é gravado em arquivo.")
    st.sidebar.caption(f"API: {API_BASE_URL}")
    if not token:
        st.info("Informe o token na barra lateral para continuar.")
        return
    cli = make_client(token)
    try:
        me = cli.me()
    except ApiError as e:
        show_error(e)
        return
    except Exception as e:  # API fora do ar
        st.error(f"API indisponível em {API_BASE_URL}: {type(e).__name__}")
        return
    st.sidebar.success(f"{me['role']} · {me['label']}")
    st.sidebar.caption(f"Escopo de dados: **{me['data_origin_scope']}**" + (" (conta de demonstração: opera só sobre dados SIMULADOS)" if me["is_demo"] else ""))
    if me["role"] == "DONOR":
        page_donor(cli, me)
    elif me["role"] == "ORG":
        page_org(cli, me)
    else:
        st.info("Perfil ADMIN: use a API (Swagger em /docs). As páginas operacionais são para DONOR e ORG.")


if __name__ == "__main__":
    main()
