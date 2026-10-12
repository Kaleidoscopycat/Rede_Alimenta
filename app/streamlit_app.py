"""Interface Streamlit por perfil (Fase 3 Parte 1 · Etapa B). Fala SOMENTE com a API HTTP (nunca com o banco); a barreira de segurança é a API, a tela só apresenta.

DOADOR → "Nova doação" (passos: Itens → Retirada → Revisar e enviar) e "Minhas doações".
ONG    → "Propostas recebidas" (Aceitar/Recusar com confirmação, "Análise da IA" recolhível) e "Histórico".
ADMIN  → "Visão técnica (admin)": ranking, scores, explicações, match_events e aviso de lote misto (o dashboard completo é a Fase 3 Parte 2).

Autenticação: cole o TOKEN do seu usuário na barra lateral (nada é gravado no código/repositório). Limitação: token estático, sem TLS/rate limit nesta fase."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Portabilidade (Windows/Linux/Docker): o Streamlit/`python scripts/x.py` só põem a pasta do script em sys.path; a raiz do projeto
# precisa estar lá para `from app...`/`from database...`. Sem depender de PYTHONPATH nem de `python -m`. Não duplica a entrada.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402

from app.api_client import ApiClient, ApiError  # noqa: E402

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
AVISO_SIM = ("⚠️ **Dados simulados com limitações conhecidas.** Capacidade, horários e refrigeração das ONGs, doadores, lotes e desfechos são SIMULADOS (R1 – volume por banco – não passa; "
             "R6 – o simulador é pessimista). Taxas, volumes e tempos simulados **não representam o mundo real**. Entidades listadas são registros de fontes públicas (licenças em revisão) e "
             "**não são clientes** da plataforma.")
AVISO_PARSER = "ℹ️ Parser treinado em **texto simulado**; limiar de confiança calibrado sobre texto simulado; **sem conjunto MANUALLY_LABELED** (o rascunho de IA não é rotulagem manual)."
AVISO_AUTH = "🔐 Autenticação mínima: token estático por usuário; sem TLS nem limite de requisições nesta fase."
AVISO_LICENCA = "dados públicos usados para fins acadêmicos; licença de reutilização não confirmada"
AVISO_DEMO = ("🟧 Ambiente de demonstração: os doadores, as doações e as respostas das ONGs aqui são **simulados** e não representam o uso real. "
              "As ONGs listadas são registros de fontes públicas e **não são clientes** da plataforma.")
MENUS = {"DONOR": ["Nova doação", "Minhas doações"], "ORG": ["Propostas recebidas", "Histórico"], "ADMIN": ["Visão técnica (admin)"]}


def make_client(token: str) -> ApiClient:
    return ApiClient(API_BASE_URL, token)


def rodape() -> None:
    st.caption(f"📄 Registros de ONGs, municípios e indicadores: bases públicas (atribuição em docs/data/DATA_LICENSES.md) — **{AVISO_LICENCA}.**")


def banner_tecnico() -> None:
    """Só o ADMIN vê os avisos técnicos completos (limitações do simulador, do parser e da autenticação)."""
    st.warning(AVISO_SIM)
    st.caption(AVISO_PARSER)
    st.caption(AVISO_AUTH)


def main() -> None:
    st.set_page_config(page_title="Rede Alimenta IA", page_icon="🥕", layout="centered")
    st.title("Rede Alimenta IA")
    token = st.sidebar.text_input("Código de acesso (token)", type="password", help="Cole o código entregue pelo administrador. Não é gravado em arquivo.")
    st.sidebar.caption(f"Serviço: {API_BASE_URL}")
    if not token:
        st.info("Informe o seu código de acesso na barra lateral para continuar.")
        st.caption(AVISO_DEMO)
        rodape()
        return
    cli = make_client(token)
    try:
        me = cli.me()
    except ApiError as e:
        st.error(e.friendly)
        rodape()
        return
    except Exception:  # serviço fora do ar (nunca mostra traceback)
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
        from app import page_admin
        page_admin.pagina_tecnica(cli, me)
    else:
        st.warning("Perfil sem telas disponíveis.")
    rodape()


if __name__ == "__main__":
    main()
