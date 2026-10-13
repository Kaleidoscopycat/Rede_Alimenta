"""Dashboard do ADMIN (Fase 3 Parte 2 · Etapa A). A interface só fala HTTP com `/api/v1/admin/stats/*` (a barreira é a API: DONOR/ORG recebem 403; cada consulta é auditada).

Regras de apresentação (ver docs/DASHBOARD.md):
* todo número leva o selo da sua ORIGEM — 🟦 PÚBLICO (fonte oficial) · 🟧 SIMULADO (simulador documentado) · 🟩 MEDIDO (entrada real na plataforma); origens nunca são somadas;
* "refeições" = kg ÷ premissa da equipe (exibida na tela; não é dado público);
* métricas de IA aparecem com os nomes reais e rotuladas "calculadas sobre dados simulados"; baselines ao lado;
* mapa SEM mapa-base de terceiros (sem chave, sem licença extra): pontos, calor e rotas sobre fundo neutro; distâncias são linha reta/estimativas, nunca rota viária."""
from __future__ import annotations

import datetime as dt
from typing import Any

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from app.api_client import ApiClient, ApiError
from app.ui_common import CATEGORIAS, fmt_datetime, fmt_num, selo_dash

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
ORIGENS = {"": "Todas", "PUBLIC": "PÚBLICO", "SIMULATED": "SIMULADO", "USER_ENTERED": "MEDIDO"}
COR_SELO = {"PÚBLICO": "#2b6cb0", "SIMULADO": "#dd8a1f", "MEDIDO": "#2f9e44"}
SEM_REAL = "Nenhuma doação real registrada."
AVISO_SIM = "Doadores, lotes e desfechos são SIMULADOS (simulador documentado) e não representam o mundo real."


# ------------------------------------------------------------------------------------------------ utilidades
def _call(cli: ApiClient, tela: str, **params: Any) -> dict | None:
    try:
        return cli.stats(tela, **params)
    except ApiError as e:
        st.error(e.friendly)
    except Exception:  # serviço fora do ar: nunca mostra traceback
        st.error("Não conseguimos carregar esta tela agora. Tente de novo em instantes.")
    return None


def _num(x: Any, nd: int = 1) -> str:
    return fmt_num(x, nd) if x is not None else "—"


def _pct(x: Any) -> str:
    return f"{float(x) * 100:.1f}%".replace(".", ",") if x is not None else "—"


def _seg(s: Any) -> str:
    if s is None:
        return "—"
    s = float(s)
    return f"{s:.0f} s" if s < 120 else f"{s / 60:.1f} min".replace(".", ",") if s < 7200 else f"{s / 3600:.1f} h".replace(".", ",")


def _df(rows: list[dict], cols: dict[str, str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "selo" in df.columns:
        df["selo"] = df["selo"].map(selo_dash)
    if "data_origin" in df.columns:
        df = df.drop(columns=["data_origin"])
    return df.rename(columns=cols) if cols else df


def _tabela(rows: list[dict], cols: dict[str, str] | None = None, vazio: str = "Sem registros para os filtros escolhidos.") -> None:
    if not rows:
        st.caption(vazio)
        return
    st.dataframe(_df(rows, cols), hide_index=True, use_container_width=True)


def _barras(rows: list[dict], x: str, y: str, titulo: str, horizontal: bool = False) -> None:
    if not rows:
        st.caption("Sem dados para os filtros escolhidos.")
        return
    df = pd.DataFrame(rows)
    scale = alt.Scale(domain=list(COR_SELO), range=list(COR_SELO.values()))
    enc_x, enc_y = (alt.X(f"{y}:Q", title=titulo), alt.Y(f"{x}:N", sort="-x", title=None)) if horizontal else (alt.X(f"{x}:N", sort=None, title=None), alt.Y(f"{y}:Q", title=titulo))
    ch = alt.Chart(df).mark_bar().encode(x=enc_x, y=enc_y, color=alt.Color("selo:N", scale=scale, legend=alt.Legend(title="Origem")), tooltip=list(df.columns)).properties(height=320)
    st.altair_chart(ch, use_container_width=True)


def _selo_legenda() -> None:
    st.caption("Selos de origem: 🟦 PÚBLICO = fonte oficial · 🟧 SIMULADO = simulador documentado · 🟩 MEDIDO = entrada real na plataforma. Origens diferentes nunca são somadas.")


def _cabecalho(titulo: str, legenda: str | None = None) -> None:
    st.header(titulo)
    if legenda:
        st.caption(legenda)


def _premissa(p: dict | None) -> None:
    if p:
        st.info(f"**Premissa da equipe (configurável):** {p['descricao']}")


def _sem_real(flag: bool) -> None:
    if flag:
        st.info(SEM_REAL)


# ------------------------------------------------------------------------------------------------ filtros
def _opcoes(cli: ApiClient, chave: str, tela: str, campo: str) -> list[str]:
    ck = f"_opt_{chave}"
    if ck not in st.session_state:
        try:
            j = cli.stats(tela, limit=1)
            st.session_state[ck] = sorted(x["chave"] for x in j.get(campo, []) if x.get("chave"))
        except Exception:
            st.session_state[ck] = []
    return st.session_state[ck]


def filtros(cli: ApiClient, chave: str, mostrar: tuple[str, ...] = ("uf", "municipio", "tipo_ong", "tipo_doador", "categoria", "origem", "periodo")) -> dict[str, Any]:
    """Filtros comuns (UF, município, tipo ONG/doador, categoria, origem, período). Devolve só os parâmetros preenchidos."""
    out: dict[str, Any] = {}
    with st.expander("Filtros", expanded=False):
        c = st.columns(4)
        if "uf" in mostrar:
            uf = c[0].selectbox("UF", [""] + UFS, key=f"{chave}_uf", format_func=lambda x: x or "Todas")
            out["uf"] = uf or None
        if "municipio" in mostrar:
            mun = c[1].text_input("Município (código IBGE)", key=f"{chave}_mun", max_chars=7, help="Código de 7 dígitos do IBGE")
            if mun.strip():
                if mun.strip().isdigit() and len(mun.strip()) == 7:
                    out["municipio_ibge"] = int(mun)
                else:
                    c[1].caption("⚠ informe 7 dígitos")
        if "tipo_ong" in mostrar:
            op = [""] + _opcoes(cli, "tipo_ong", "organizations", "por_tipo")
            out["tipo_ong"] = c[2].selectbox("Tipo de ONG", op, key=f"{chave}_to", format_func=lambda x: x or "Todos") or None
        if "tipo_doador" in mostrar:
            op = [""] + _opcoes(cli, "tipo_doador", "donors", "por_tipo")
            out["tipo_doador"] = c[3].selectbox("Tipo de doador", op, key=f"{chave}_td", format_func=lambda x: x or "Todos") or None
        c2 = st.columns(3)
        if "categoria" in mostrar:
            out["categoria"] = c2[0].selectbox("Categoria", [""] + list(CATEGORIAS), key=f"{chave}_cat", format_func=lambda x: CATEGORIAS.get(x, "Todas")) or None
        if "origem" in mostrar:
            out["origem"] = c2[1].selectbox("Origem", list(ORIGENS), key=f"{chave}_or", format_func=ORIGENS.get) or None
        if "periodo" in mostrar and c2[2].checkbox("Filtrar por período", key=f"{chave}_per"):
            hoje = dt.date.today()
            ini = c2[2].date_input("De", value=hoje - dt.timedelta(days=365), key=f"{chave}_ini")
            fim = c2[2].date_input("Até", value=hoje, key=f"{chave}_fim")
            out["inicio"], out["fim"] = ini.isoformat(), fim.isoformat()
    return {k: v for k, v in out.items() if v}


# ------------------------------------------------------------------------------------------------ telas
def tela_overview(cli: ApiClient, me: dict) -> None:
    _cabecalho("Overview", "Visão geral da plataforma. Cada bloco traz o selo da origem dos dados.")
    f = filtros(cli, "ov")
    j = _call(cli, "overview", **f)
    if not j:
        return
    _selo_legenda()
    _premissa(j["premissa"])
    _sem_real(j["nenhuma_doacao_real"])
    cat = j["catalogo"]
    st.subheader(f"Catálogo público de ONGs · {selo_dash(cat['selo'])}")
    c = st.columns(4)
    c[0].metric("ONGs catalogadas", _num(cat["ongs_catalogadas"], 0))
    c[1].metric("Bancos de alimentos (RBBA)", _num(cat["bancos_de_alimentos_rbba"], 0))
    c[2].metric("Municípios cobertos", _num(cat["municipios_cobertos"], 0))
    c[3].metric("UFs cobertas", _num(cat["ufs_cobertas"], 0))
    st.caption(cat["nota"] + (f" Última atualização dos datasets: {fmt_datetime(cat['ultima_atualizacao_datasets'])}." if cat.get("ultima_atualizacao_datasets") else ""))

    st.subheader("A · Quilos ofertados e coletados")
    st.caption("Não usamos “kg salvos”: mostramos o que foi ofertado (lotes cadastrados) e o que foi coletado (match com coleta concluída), cada um por origem.")
    for bloco, nome in ((j["doacoes_ofertadas"], "Ofertado"), (j["doacoes_coletadas"], "Coletado")):
        for b in bloco:
            c = st.columns(4)
            c[0].markdown(f"**{nome}** · {selo_dash(b['selo'])}")
            c[1].metric("Doações", _num(b["n_doacoes"], 0))
            c[2].metric("kg", _num(b["kg"], 1))
            c[3].metric("Refeições estimadas", _num(b["refeicoes_estimadas"], 0), help=j["premissa"]["descricao"])
            st.caption(b["legenda"])
    if not any(b["n_doacoes"] for b in j["doacoes_ofertadas"] + j["doacoes_coletadas"]):
        st.caption("Sem doações para os filtros escolhidos.")

    st.subheader("Matches")
    for b in j["matches"]:
        c = st.columns(5)
        c[0].markdown(f"{selo_dash(b['selo'])}")
        c[1].metric("Matches", _num(b["n_matches"], 0))
        c[2].metric("Aceitos", _num(b["aceitas"], 0))
        c[3].metric("Coletados", _num(b["coletadas"], 0))
        c[4].metric("Taxa de aceite", _pct(b["taxa_aceite"]), help="aceites ÷ (aceites + recusas + expirações)")
    st.subheader("D · Tempo médio de match")
    for b in j["tempo_match"]:
        c = st.columns(4)
        c[0].markdown(f"{selo_dash(b['selo'])}")
        c[1].metric("Registro → 1ª proposta", _seg(b["registro_ate_primeira_proposta_s"]))
        c[2].metric("Proposta → resposta", _seg(b["proposta_ate_resposta_s"]))
        c[3].metric("Registro → aceite", _seg(b["registro_ate_aceite_s"]))
        st.caption(b["origem_texto"])
    for b in j["latencia_ranking"]:
        st.caption(f"Latência do ranking · {selo_dash(b['selo'])}: média {_num(b['media_ms'])} ms · p50 {_num(b['p50_ms'])} ms · p95 {_num(b['p95_ms'])} ms (n={b['n']})")
    ia = j["ia"]
    st.subheader("C · IA (resumo)")
    if ia["disponivel"]:
        c = st.columns(4)
        c[0].metric("MRR", _num(ia["mrr"], 3))
        c[1].metric("Top-1", _pct(ia["top1_hit_rate"]))
        c[2].metric("Top-3", _pct(ia["top3_hit_rate"]))
        c[3].metric("MRR da ONG mais próxima", _num(ia["mrr_baseline_ong_mais_proxima"], 3))
    st.caption(ia["rotulo"] + " " + ia["nota_nomes"])
    sg = j["seguranca"]
    st.subheader(f"E · Vulnerabilidades mitigadas (SAST) · {selo_dash(sg['selo'])}")
    st.metric("Mitigadas e comprovadas por relatório (antes × depois)", _num(sg["total_mitigadas_comprovadas"], 0))
    for p in sg["pendencias"]:
        st.caption("⏳ " + p)
    if j.get("filtros_aplicados"):
        st.caption(f"Filtros aplicados: {j['filtros_aplicados']}")


def tela_doacoes(cli: ApiClient, me: dict) -> None:
    _cabecalho("Doações e matches")
    f = filtros(cli, "dm")
    j = _call(cli, "donations-matches", **f)
    if not j:
        return
    _selo_legenda()
    st.caption(j["legenda"])
    _premissa(j["premissa"])
    _sem_real(j["nenhuma_doacao_real"])
    st.subheader("Doações por mês")
    _barras(j["serie_mensal"], "mes", "kg", "kg ofertados")
    _tabela(j["serie_mensal"], {"mes": "mês", "n_doacoes": "doações", "refeicoes_estimadas": "refeições estimadas"})
    c = st.columns(2)
    with c[0]:
        st.subheader("Doações por status")
        _tabela(j["por_status"], {"chave": "status", "n": "doações"})
        st.subheader("Matches por status")
        _tabela(j["matches_por_status"], {"chave": "status", "n": "matches"})
    with c[1]:
        st.subheader("Por categoria")
        _barras(j["por_categoria"], "chave", "kg", "kg", horizontal=True)
        st.subheader("Ciclo do match (eventos)")
        _tabela(j["ciclo_do_match"], {"chave": "evento", "n": "ocorrências"})
    for b in j["latencia_ranking"]:
        st.caption(f"Latência do ranking · {selo_dash(b['selo'])}: média {_num(b['media_ms'])} ms · p95 {_num(b['p95_ms'])} ms")
    st.subheader("B · Refeições estimadas por região")
    c = st.columns(2)
    nivel = c[0].radio("Nível", ["macro", "uf", "municipio"], horizontal=True, key="rr_nivel", format_func={"macro": "Macrorregião", "uf": "UF", "municipio": "Município"}.get)
    base = c[1].radio("Base", ["ofertado", "coletado"], horizontal=True, key="rr_base", format_func=str.capitalize)
    r = _call(cli, "meals-by-region", nivel=nivel, base=base, **f)
    if r:
        st.caption(r["legenda"])
        _premissa(r["premissa"])
        _sem_real(r["nenhuma_doacao_real"])
        rows = r["linhas"]
        for x in rows:
            x["rotulo"] = x.get("nome") or x.get("uf") or x["regiao"]
        _barras(rows, "rotulo", "refeicoes_estimadas", "refeições estimadas", horizontal=True)
        _tabela(rows, {"regiao": "região", "n_doacoes": "doações", "refeicoes_estimadas": "refeições estimadas", "rotulo": "local"})


def _camada_pontos(rows: list[dict], cor: list[int], raio: int, nome: str) -> pdk.Layer:
    df = pd.DataFrame(rows)
    return pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_radius=raio, radius_min_pixels=3, radius_max_pixels=18, get_fill_color=cor, pickable=True, auto_highlight=True, id=nome)


def tela_mapa(cli: ApiClient, me: dict) -> None:
    _cabecalho("Mapa")
    f = filtros(cli, "mp")
    j = _call(cli, "map", **f)
    if not j:
        return
    _selo_legenda()
    st.caption(j["legenda"])
    st.warning(j["aviso_localizacao"])
    st.caption(j["sem_mapa_base"])
    c = st.columns(5)
    sh_calor = c[0].checkbox("Calor de ONGs", True, key="mp_calor")
    sh_ong = c[1].checkbox("ONGs (pontos)", False, key="mp_ong")
    sh_doa = c[2].checkbox("Doadores", True, key="mp_doa")
    sh_don = c[3].checkbox("Doações (kg)", True, key="mp_don")
    sh_rota = c[4].checkbox("Rotas de coleta", True, key="mp_rota")
    layers: list[pdk.Layer] = []
    pts = j["ongs_por_municipio"]
    if sh_calor and pts:
        layers.append(pdk.Layer("HeatmapLayer", pd.DataFrame(pts), get_position="[lon, lat]", get_weight="n", radius_pixels=45, opacity=0.8, id="calor"))
    if sh_ong and j["ongs_pontos"]:
        layers.append(_camada_pontos(j["ongs_pontos"], [43, 108, 176, 170], 1500, "ongs"))
        if j["ongs_pontos_truncado"]:
            st.caption("Pontos de ONGs limitados para manter a tela leve; use filtros de UF/município para ver todos.")
    if sh_doa and j["doadores_por_municipio"]:
        layers.append(_camada_pontos(j["doadores_por_municipio"], [221, 138, 31, 190], 5000, "doadores"))
    if sh_don and j["doacoes_por_municipio"]:
        layers.append(_camada_pontos(j["doacoes_por_municipio"], [47, 158, 68, 190], 7000, "doacoes"))
    if sh_rota and j["rotas"]:
        segs = []
        for r in j["rotas"]:
            ps = sorted(r["paradas"], key=lambda p: p["seq"])
            segs.append({"path": [[p["lon"], p["lat"]] for p in ps], "nome": f"{r['ong_id']} · {r['algoritmo']} · {r['total_km_est']} km"})
        layers.append(pdk.Layer("PathLayer", segs, get_path="path", get_color=[190, 40, 40, 220], width_min_pixels=3, pickable=True, id="rotas"))
    todos = pts + j["doadores_por_municipio"] + j["doacoes_por_municipio"]
    lat = sum(p["lat"] for p in todos) / len(todos) if todos else -14.2
    lon = sum(p["lon"] for p in todos) / len(todos) if todos else -51.9
    zoom = 3.4 if len(todos) > 200 else 5
    if layers:
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom), map_style=None, tooltip={"text": "{nome} {uf}\n{n} registros"}), use_container_width=True)
    else:
        st.info("Nada para desenhar com os filtros e camadas escolhidos.")
    st.caption("Legenda: 🔥 calor = densidade de ONGs (🟦 PÚBLICO) · laranja = doadores (🟧 SIMULADO) · verde = doações (kg) · vermelho = rotas planejadas (estimativa em linha reta × desvio, não rota viária).")
    if j["rotas"]:
        st.subheader("Rotas de coleta planejadas")
        _tabela([{k: r[k] for k in ("id", "ong_id", "algoritmo", "status", "total_km_est", "total_minutos_est", "selo", "aviso_distancia")} for r in j["rotas"]],
                {"total_km_est": "km (est.)", "total_minutos_est": "min (est.)", "aviso_distancia": "aviso"})
    else:
        st.caption("Ainda não há rotas planejadas para os filtros escolhidos (rotas são geradas pelo planejamento de coleta).")


def tela_organizacoes(cli: ApiClient, me: dict) -> None:
    _cabecalho("Organizações")
    f = filtros(cli, "og", ("uf", "municipio", "tipo_ong"))
    pag = st.number_input("Página", 1, 10_000, 1, key="og_pag")
    j = _call(cli, "organizations", limit=50, offset=(int(pag) - 1) * 50, **f)
    if not j:
        return
    _selo_legenda()
    st.caption(j["legenda"])
    st.metric("ONGs (registros públicos)", _num(j["total"], 0))
    c = st.columns(2)
    with c[0]:
        st.subheader("Por tipo")
        _barras(j["por_tipo"], "chave", "n", "ONGs", horizontal=True)
        st.subheader("Precisão da localização")
        _tabela(j["por_precisao_localizacao"], {"chave": "precisão", "n": "ONGs"})
    with c[1]:
        st.subheader("Por UF")
        _barras(j["por_uf"], "chave", "n", "ONGs", horizontal=True)
        st.subheader("Status na plataforma")
        _tabela(j["por_status_plataforma"], {"chave": "status", "n": "ONGs"})
    st.subheader("Perfil declarado (capacidade, frota, câmara fria)")
    _tabela(j["perfil_declarado"], {"chave": "origem do perfil", "n": "ONGs"})
    st.caption("ONGs aparecem por pseudônimo (ong_id); capacidade, horários e frota são declarados/simulados, nunca medidos.")
    st.subheader("Lista (50 por página)")
    _tabela(j["linhas"], {"ong_id": "ONG (pseudônimo)", "ong_tipo": "tipo", "municipio": "município", "location_precision": "precisão", "platform_status": "status",
                          "licenca": "licença", "perfil_origin": "perfil", "capacidade_max_kg_dia": "capac. máx. kg/dia", "camara_fria": "câmara fria", "tem_frota": "frota"})


def tela_doadores(cli: ApiClient, me: dict) -> None:
    _cabecalho("Doadores")
    f = filtros(cli, "dd", ("uf", "municipio", "tipo_doador", "origem"))
    pag = st.number_input("Página", 1, 10_000, 1, key="dd_pag")
    j = _call(cli, "donors", limit=50, offset=(int(pag) - 1) * 50, **f)
    if not j:
        return
    _selo_legenda()
    st.caption(j["legenda"])
    _sem_real(j["nenhuma_doacao_real"])
    _tabela(j["total"], {"chave": "origem", "n": "doadores"})
    c = st.columns(2)
    with c[0]:
        st.subheader("Por tipo")
        _barras(j["por_tipo"], "chave", "n", "doadores", horizontal=True)
    with c[1]:
        st.subheader("Por porte")
        _barras(j["por_porte"], "chave", "n", "doadores", horizontal=True)
    st.subheader("Lista (50 por página)")
    _tabela(j["linhas"], {"external_id": "doador (id simulado)", "donor_type": "tipo", "donor_size": "porte", "municipio": "município", "n_doacoes": "doações", "kg": "kg ofertados"})


def tela_publicos(cli: ApiClient, me: dict) -> None:
    _cabecalho("Dados públicos")
    j = _call(cli, "public-data")
    if not j:
        return
    _selo_legenda()
    st.caption(j["legenda"])
    st.warning(j["aviso_licenca"])
    c = st.columns(2)
    c[0].metric("Registros processados", _num(j["registros_processados"], 0))
    c[1].metric("Última atualização", fmt_datetime(j["ultima_atualizacao"]))
    _tabela(j["fontes"], {"nome": "fonte", "organizacao": "órgão", "licenca": "licença", "revisao": "revisão", "uso_comercial": "uso comercial", "liberada_para_publicacao": "liberada p/ publicar",
                          "n_registros": "registros", "versao": "versão", "ingerida_em": "ingerida em", "atualizada_na_fonte": "atualizada na fonte", "url": "endereço"})
    with st.expander("Indicadores territoriais disponíveis"):
        _tabela(j["indicadores_por_codigo"])


def tela_territorial(cli: ApiClient, me: dict) -> None:
    _cabecalho("Indicadores territoriais", "Indicadores públicos por UF ou município (fonte oficial); não são dados da plataforma.")
    c = st.columns(3)
    nivel = c[0].radio("Nível", ["uf", "municipio"], horizontal=True, key="tr_nivel", format_func={"uf": "UF", "municipio": "Município"}.get)
    uf = c[1].selectbox("UF", [""] + UFS, key="tr_uf", format_func=lambda x: x or "Todas")
    j = _call(cli, "territorial", nivel=nivel, uf=uf or None)
    if not j:
        return
    codigos = j["codigos_disponiveis"]
    if codigos:
        op = {x["codigo"]: f"{x['codigo']} ({x.get('unidade') or '—'})" for x in codigos}
        cod = c[2].selectbox("Indicador", list(op), key="tr_cod", format_func=op.get, index=list(op).index(j["codigo"]) if j["codigo"] in op else 0)
        if cod != j["codigo"]:
            j = _call(cli, "territorial", nivel=nivel, uf=uf or None, codigo=cod) or j
    st.caption(f"{selo_dash(j['selo'])} · {j['legenda']} · unidade: {j['unidade'] or '—'} · referência: {j['periodo_referencia'] or '—'}")
    rows = [{**r, "selo": j["selo"]} for r in j["linhas"]]
    for r in rows:
        r["rotulo"] = r.get("nome") or r["chave"]
    _barras(rows[:30], "rotulo", "valor", j["codigo"], horizontal=True)
    _tabela(rows, {"chave": "código", "nome": "nome", "valor": "valor", "por_100mil_habitantes": "por 100 mil hab.", "populacao": "população", "rotulo": "local"})
    st.caption(j["nota"])


def tela_ia(cli: ApiClient, me: dict) -> None:
    _cabecalho("IA — modelos, métricas e limitações")
    j = _call(cli, "ai")
    if not j:
        return
    st.info(j["rotulo"])
    rk, pa = j["ranker"], j["parser"]
    st.subheader("Ranker de ONGs (aceite e coleta dentro da validade)")
    if not rk.get("disponivel"):
        st.warning(rk.get("motivo", "Artefatos do ranker indisponíveis."))
    else:
        st.caption(f"Versão {rk.get('versao')} · modelo {rk.get('modelo')} · métricas {rk['rotulo']}")
        tab = pd.DataFrame(rk["tabela_comparacao"]).rename(columns={"modelo": "modelo", "tipo": "tipo", "mrr": "MRR", "top1_hit_rate": "Top-1", "top3_hit_rate": "Top-3", "ndcg@3": "NDCG@3", "escolhido": "escolhido"})
        st.dataframe(tab, hide_index=True, use_container_width=True)
        st.caption("Linhas “Baseline” são as referências de comparação (aleatório, ONG mais próxima, regra); o modelo só vale se superar a ONG mais próxima.")
        cl = rk.get("classificacao_modelo_escolhido") or {}
        c = st.columns(4)
        c[0].metric("ROC-AUC", _num(cl.get("roc_auc"), 3))
        c[1].metric("PR-AUC", _num(cl.get("pr_auc"), 3))
        c[2].metric("F1", _num(cl.get("f1"), 3))
        c[3].metric("Limiar de decisão (validação)", _num(rk.get("limiar_decisao_validacao"), 3))
        if rk.get("importancia_permutacao_pr_auc"):
            st.markdown("**Importância dos atributos** (queda de PR-AUC ao embaralhar)")
            imp = pd.DataFrame(rk["importancia_permutacao_pr_auc"])
            st.altair_chart(alt.Chart(imp).mark_bar(color=COR_SELO["SIMULADO"]).encode(x=alt.X("queda_pr_auc:Q"), y=alt.Y("atributo:N", sort="-x", title=None), tooltip=list(imp.columns)).properties(height=320),
                            use_container_width=True)
            if rk.get("importancia_nota"):
                st.caption(rk["importancia_nota"])
        if rk.get("limitacao_circularidade"):
            st.warning(str(rk["limitacao_circularidade"]))
    st.subheader("Parser de texto (a “acurácia” só existe aqui)")
    if not pa.get("disponivel"):
        st.warning(pa.get("motivo", "Artefatos do parser indisponíveis."))
    else:
        st.caption(f"{pa['rotulo']} · limiar de confiança τ = {pa.get('limiar_confianca_tau')}")
        _tabela(pa["avaliacoes"], None)
        st.caption(f"Conjunto MANUALLY_LABELED: {pa.get('manually_labeled') or 'AUSENTE'}")
    st.subheader("Motor de match")
    st.json(j["engine"], expanded=False)
    st.subheader("Lote misto")
    st.json(j["lote_misto"], expanded=False)
    st.subheader("Limitações conhecidas")
    for x in j["limitacoes"]:
        st.markdown(f"- **{x.get('titulo', '')}** — {x.get('texto', '')}")
    with st.expander("Glossário das métricas"):
        for k, v in j["glossario"].items():
            st.markdown(f"**{k}** — {v}")
    with st.expander("Datasets de treino/avaliação"):
        _tabela(j["datasets"])


def tela_recomendacoes(cli: ApiClient, me: dict) -> None:
    _cabecalho("Recomendações — simulador de lote", "O doador informa um lote e o modelo ranqueia ONGs. Predição direta: não cria doação nem match. Resultado vem de modelo treinado em dados SIMULADOS.")
    d = _call(cli, "donors", limit=50, origem="SIMULATED")
    if not d or not d["linhas"]:
        st.info("Não há doadores SIMULADOS para a simulação.")
        return
    op = {x["donor_id"]: f"{x['external_id']} · {x['municipio']}/{x['uf']} · {x['donor_type']}" for x in d["linhas"]}
    with st.form("sim_lote"):
        did = st.selectbox("Doador (simulado)", list(op), format_func=op.get)
        c = st.columns(4)
        cat = c[0].selectbox("Categoria", list(CATEGORIAS), format_func=CATEGORIAS.get)
        kg = c[1].number_input("Quantidade (kg)", 1.0, 100000.0, 40.0)
        horas = c[2].number_input("Horas até a validade", 1.0, 8760.0, 48.0)
        frio = c[3].checkbox("Exige refrigeração")
        top = st.slider("ONGs no ranking", 1, 15, 5)
        ok = st.form_submit_button("Gerar recomendação")
    if ok:
        try:
            r = cli.predict({"donor_id": did, "categoria": cat, "quantidade_kg": kg, "horas_ate_validade": horas, "exige_refrigeracao": frio, "top_n": top,
                             "municipio_ibge": next(x["municipio_ibge"] for x in d["linhas"] if x["donor_id"] == did)})
        except ApiError as e:
            st.error(e.friendly)
            return
        st.session_state["sim_res"] = r
    r = st.session_state.get("sim_res")
    if r:
        st.caption(f"Modelo {r['model_version']} · origem do treino: {r['data_origin']} · confiança da melhor ONG: {r['confidence']:.2f} (probabilidade estimada, não garantia)")
        st.dataframe(pd.DataFrame(r["ranking"]).rename(columns={"posicao": "#", "ong_id": "ONG (pseudônimo)", "ong_tipo": "tipo", "dist_km": "km (linha reta)", "probabilidade": "P(aceite e coleta)",
                                                              "elegivel_regra": "elegível", "location_precision": "precisão"}), hide_index=True, use_container_width=True)
        for a in r.get("alertas", []):
            st.info(a)
        st.caption(r["aviso"])


def tela_logistica(cli: ApiClient, me: dict) -> None:
    _cabecalho("Logística — comparação de estratégias (simulação)", "ONG mais próxima × ranking híbrido × ranking híbrido com rota, sobre o mesmo conjunto de lotes SIMULADOS.")
    with st.form("logi"):
        c = st.columns(4)
        n = c[0].number_input("Lotes", 2, 24, 8)
        seed = c[1].number_input("Semente", 0, 2**31 - 1, 20261012)
        raio = c[2].number_input("Raio (km)", 5.0, 150.0, 40.0)
        tempo = c[3].number_input("Tempo do solver (s)", 1, 3, 1)
        ok = st.form_submit_button("Simular")
    if ok:
        try:
            st.session_state["logi_res"] = cli.logistics_strategies(int(n), int(seed), float(raio), int(tempo))
        except ApiError as e:
            st.error(e.friendly)
            return
    j = st.session_state.get("logi_res")
    if not j:
        st.caption("Escolha os parâmetros e clique em Simular. O mesmo valor de semente reproduz o mesmo cenário.")
        return
    st.warning(j["rotulo"])
    rows = [{k: v for k, v in e.items() if k not in ("motivos_nao_entrega", "rotas", "descricao")} for e in j["estrategias"]]
    df = pd.DataFrame(rows).rename(columns={"id": "estratégia", "lotes": "lotes", "lotes_entregues_no_prazo": "entregues no prazo", "lotes_nao_entregues": "não entregues", "kg_entregue": "kg entregues",
                                            "km_total_estimado": "km (est.)", "minutos_total_estimado": "min (est.)", "ongs_distintas": "ONGs distintas"})
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.altair_chart(alt.Chart(df).mark_bar(color=COR_SELO["SIMULADO"]).encode(x=alt.X("estratégia:N", title=None, sort=None), y=alt.Y("km (est.):Q"), tooltip=list(df.columns)).properties(height=260),
                    use_container_width=True)
    for e in j["estrategias"]:
        with st.expander(e["id"]):
            st.write(e["descricao"])
            if e["motivos_nao_entrega"]:
                st.json(e["motivos_nao_entrega"], expanded=False)
            if e.get("rotas"):
                _tabela(e["rotas"])
    for t in j["leitura"]:
        st.caption("• " + t)
    st.caption(f"Parâmetros: {j['parametros']}")


def tela_seguranca(cli: ApiClient, me: dict) -> None:
    _cabecalho("Segurança e sistema")
    j = _call(cli, "security")
    if not j:
        return
    rel, sis = j["relatorios"], j["sistema"]
    st.caption("🟦 PÚBLICO: relatórios gerados por ferramentas (Bandit, pip-audit, Trivy, Gitleaks) e versionados no repositório; só contamos o que há JSON de antes e de depois.")
    st.metric("Vulnerabilidades mitigadas e comprovadas", _num(rel["total_mitigadas_comprovadas"], 0))
    for p in rel["pendencias"]:
        st.warning("⏳ " + p)
    st.subheader("Fase 2 — antes × depois")
    for nome, v in rel["fase2"].items():
        if isinstance(v, dict):
            st.markdown(f"**{v.get('ferramenta', nome)}** — {v.get('situacao')}" + (f" · mitigadas: {v['mitigadas']}" if v.get("comprovado") else ""))
    st.subheader("Trivy da imagem (CI)")
    st.json(rel["trivy_imagem_ci"], expanded=False)
    st.subheader("Estado atual (Fase 3A)")
    st.json(rel["estado_atual_fase3a"], expanded=False)
    st.subheader("Sistema")
    c = st.columns(4)
    c[0].metric("Ambiente", sis["ambiente"])
    c[1].metric("Pronto", "sim" if sis["pronto"] else "não")
    c[2].metric("ONGs ranqueáveis", _num(sis["orgs_ranqueaveis"], 0))
    c[3].metric("Motor", sis["engine_version"])
    st.caption(f"Modelo {sis['model_version']} · parser {sis['parser_version']}")
    st.subheader("Auditoria nas últimas 24 h")
    st.json({"por_resultado": sis["auditoria_24h_por_resultado"], "principais_acoes": sis["auditoria_24h_principais_acoes"], "usuarios_ativos_por_perfil": sis["usuarios_ativos_por_perfil"]}, expanded=False)
    for x in sis["limitacoes"]:
        st.caption("• " + x)


TELAS = {"Overview": tela_overview, "Doações e matches": tela_doacoes, "Mapa": tela_mapa, "Organizações": tela_organizacoes, "Doadores": tela_doadores, "Dados públicos": tela_publicos,
         "Indicadores territoriais": tela_territorial, "IA": tela_ia, "Recomendações": tela_recomendacoes, "Logística": tela_logistica, "Segurança e sistema": tela_seguranca}
