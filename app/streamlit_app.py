"""Interface Streamlit por perfil (Fase 3 Parte 1 · Etapa B). Fala SOMENTE com a API HTTP (nunca com o banco); a barreira de segurança é a API, a tela só apresenta.

DOADOR → "Nova doação" (passos: Itens → Retirada → Revisar e enviar) e "Minhas doações".
ONG    → "Propostas recebidas" (Aceitar/Recusar com confirmação, "Análise da IA" recolhível) e "Histórico".
ADMIN  → dashboard completo (Fase 3 Parte 2): Overview, Doações e matches, Mapa, Organizações, Doadores, Dados públicos, Indicadores territoriais, IA, Recomendações, Logística,
         Segurança/Sistema e "Visão técnica (admin)" (ranking, scores, explicações, match_events e aviso de lote misto).

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

import streamlit as st  # noqa: E402

from app.api_client import ApiClient, ApiError  # noqa: E402
from app.ui_common import aviso_academico  # noqa: E402

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
AVISO_SIM = ("⚠️ **Dados simulados com limitações conhecidas.** Capacidade, horários e refrigeração das ONGs, doadores, lotes e desfechos são SIMULADOS (R1 – volume por banco – não passa; "
             "R6 – o simulador é pessimista). Taxas, volumes e tempos simulados **não representam o mundo real**. Entidades listadas são registros de fontes públicas (licenças em revisão) e "
             "**não são clientes** da plataforma.")
AVISO_PARSER = "ℹ️ Parser treinado em **texto simulado**; limiar de confiança calibrado sobre texto simulado; **sem conjunto MANUALLY_LABELED** (o rascunho de IA não é rotulagem manual)."
AVISO_AUTH = "🔐 Autenticação mínima: token estático por usuário (expiração opcional); TLS fornecido pela plataforma; em produção há limite de tentativas inválidas por IP, mas não há rate limit global nem rotação automática de tokens (Fase 4)."
AVISO_LICENCA = "dados públicos usados para fins acadêmicos; licença de reutilização não confirmada"
AVISO_DEMO = ("🟧 Ambiente de demonstração: os doadores, as doações e as respostas das ONGs aqui são **simulados** e não representam o uso real. "
              "As ONGs listadas são registros de fontes públicas e **não são clientes** da plataforma.")
MENUS = {"DONOR": ["Nova doação", "Minhas doações"], "ORG": ["Propostas recebidas", "Histórico"], "ADMIN": ["Overview", "Doações e matches", "Mapa", "Organizações", "Doadores", "Dados públicos", "Indicadores territoriais", "IA", "Recomendações", "Logística",
                                                                      "Segurança e sistema", "Visão técnica (admin)"]}


def make_client(token: str, aviso: Any = None) -> ApiClient:
    """`aviso` (st.empty) recebe a mensagem amigável enquanto o servidor gratuito acorda (API_WAKE_MAX_S > 0)."""
    def esperando(seg: float) -> None:
        if aviso is not None:
            aviso.info(f"⏳ Acordando o servidor… no plano gratuito isso leva cerca de 1 minuto ({seg:.0f} s). Aguarde, não feche a página.")
    return ApiClient(API_BASE_URL, token, on_wait=esperando)


def rodape() -> None:
    st.caption(f"📄 Registros de ONGs, municípios e indicadores: bases públicas (atribuição em docs/data/DATA_LICENSES.md) — **{AVISO_LICENCA}.**")


def banner_tecnico() -> None:
    """Só o ADMIN vê os avisos técnicos completos (limitações do simulador, do parser e da autenticação)."""
    st.warning(AVISO_SIM)
    st.caption(AVISO_PARSER)
    st.caption(AVISO_AUTH)


def main() -> None:
    st.set_page_config(page_title="Rede Alimenta IA", page_icon="🥕", layout="wide")
    st.title("Rede Alimenta IA")
    aviso_academico()
    token = st.sidebar.text_input("Código de acesso (token)", type="password", help="Cole o código entregue pelo administrador. Não é gravado em arquivo.")
    st.sidebar.caption(f"Serviço: {API_BASE_URL}")
    if not token:
        st.info("Informe o seu código de acesso na barra lateral para continuar.")
        st.caption(AVISO_DEMO)
        rodape()
        return
    aviso = st.empty()
    cli = make_client(token, aviso)
    try:
        me = cli.me()
        aviso.empty()
    except ApiError as e:
        aviso.empty()
        st.error(e.friendly)
        rodape()
        return
    except Exception:  # serviço fora do ar (nunca mostra traceback)
        aviso.empty()
        st.error("Não conseguimos falar com o serviço agora. Verifique se ele está ligado e tente de novo.")
        rodape()
        return
    papel = {"DONOR": "Doador", "ORG": "ONG", "ADMIN": "Administrador"}.get(me["role"], me["role"])
    st.sidebar.success(f"{papel} · {me['label']}")
    st.sidebar.caption(f"Dados: **{'simulados' if me['data_origin_scope'] == 'SIMULATED' else 'todos' if me['data_origin_scope'] == 'ALL' else 'reais (USER_ENTERED)'}**"
                       + (" — conta de demonstração" if me.get("is_demo") else ""))
    menu = MENUS.get(me["role"], [])
    if "ir_para" in st.session_state:  # pedido de navegação feito por um botão (aplicado ANTES de criar o seletor de menu)
        alvo = st.session_state.pop("ir_para")
        if alvo in menu:
            st.session_state["menu"] = alvo
    pagina = st.sidebar.radio("Menu", menu, key="menu") if len(menu) > 1 else (menu[0] if menu else None)
    if me["role"] != "ADMIN":  # DOADOR e ONG mantêm a leitura confortável em coluna estreita; só o ADMIN usa a largura total do dashboard
        st.markdown("<style>.block-container{max-width:46rem;margin-left:auto;margin-right:auto}</style>", unsafe_allow_html=True)
    if me["role"] == "ADMIN":
        banner_tecnico()
    elif me["data_origin_scope"] == "SIMULATED":
        st.caption(AVISO_DEMO)
    if me["role"] == "DONOR":
        from app import page_donor
        {"Nova doação": page_donor.pagina_nova, "Minhas doações": page_donor.pagina_minhas}[pagina](cli, me)
    elif me["role"] == "ORG":
        from app import page_org
        {"Propostas recebidas": page_org.pagina_propostas, "Histórico": page_org.pagina_historico}[pagina](cli, me)
    elif me["role"] == "ADMIN":
        from app import page_admin, page_dashboard
        if pagina == "Visão técnica (admin)":
            page_admin.pagina_tecnica(cli, me)
        else:
            page_dashboard.TELAS[pagina](cli, me)
    else:
        st.warning("Perfil sem telas disponíveis.")
    rodape()


if __name__ == "__main__":
    main()
