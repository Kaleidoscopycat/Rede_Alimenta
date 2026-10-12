"""Etapa B — AppTest do Streamlit POR PERFIL (a interface só fala HTTP com a API; aqui a API é o TestClient sobre o banco de teste).
Dados: contas de DEMONSTRAÇÃO sobre doadores SIMULADOS do simulador e ONGs reais; os itens digitados usam rótulos técnicos de teste ("item-tecnico-ui-N") e valores técnicos — nada é apresentado como real."""
import datetime as dt
from pathlib import Path

import pytest

from tests.helpers_p2 import admin_match, new_ready_donation, org_token
from tests.test_p3b_campos_ia_proibidos import proibidas

ROOT_APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
# termos que o DOADOR e a ONG não podem ver em NENHUM texto da tela (jargão de IA / saída do modelo)
PROIBIDOS_TELA = ("ml_score", "business_rule", "distance_score", "final_score", "ranking", "score", "confiança", "confianca", "parser", "match", "τ", "limiar", "threshold", "model_version")
LONGE = dt.date(2027, 12, 31)


def _run(monkeypatch, client, headers=None):
    import httpx
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    at = AppTest.from_file(ROOT_APP, default_timeout=90)
    at.run()
    if headers:
        at.sidebar.text_input[0].set_value(headers["Authorization"].split(" ", 1)[1])
        at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def textos(at) -> str:
    out = []
    for kind in ("markdown", "caption", "text", "info", "warning", "error", "success", "subheader", "header", "title", "code"):
        out += [str(e.value) for e in getattr(at, kind)]
    out += [f"{m.label} {m.value}" for m in at.metric]
    out += [b.label for b in at.button]
    out += [e.label for e in at.expander]
    return " ".join(out)


def sem_jargao(at):
    t = textos(at).lower()
    achados = [p for p in PROIBIDOS_TELA if p in t]
    assert not achados, achados
    assert len(at.dataframe) == 0, "doador/ONG não veem tabelas de scores"
    assert not at.exception, [e.value for e in at.exception]


def preenche_item(at, nonce, nome, cat, qtd, peso, un, refrig="Não", data=LONGE, mes_ano=None, emb=None):
    p = f"novo{nonce}"
    at.text_input(key=f"{p}_nome").set_value(nome)
    at.selectbox(key=f"{p}_cat").select(cat)
    at.number_input(key=f"{p}_qtd").set_value(qtd)
    if emb:
        at.selectbox(key=f"{p}_emb").select(emb)
    at.number_input(key=f"{p}_peso").set_value(peso)
    at.selectbox(key=f"{p}_un").select(un)
    if mes_ano:
        at.radio(key=f"{p}_modo").set_value("Só mês e ano")
        at.run()
        at.selectbox(key=f"{p}_mes").select(mes_ano[0])
        at.selectbox(key=f"{p}_ano").select(mes_ano[1])
    else:
        at.date_input(key=f"{p}_data").set_value(data)
    at.radio(key=f"{p}_ref").set_value(refrig)
    at.run()
    at.button(key=f"add_{nonce}").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def libera_capacidade(client, world, headers_doador):
    """Recusa (como ADMIN) as propostas abertas deste doador para não deixar capacidade reservada entre testes."""
    for mt in client.get("/api/v1/matches", headers=headers_doador).json():
        for _ in range(40):
            st = client.get(f"/api/v1/matches/{mt['id']}", headers=world["admin"]).json()["status"]
            if st != "PROPOSED":
                break
            client.post(f"/api/v1/matches/{mt['id']}/respond", headers=world["admin"], json={"accept": False})


# ================================================================== DOADOR
def test_doador_menu_e_ausencia_de_elementos_de_score(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["donor_a"])
    assert at.sidebar.radio(key="menu").options == ["Nova doação", "Minhas doações"]
    assert at.header[0].value == "Nova doação"
    sem_jargao(at)
    at.sidebar.radio(key="menu").set_value("Minhas doações")
    at.run()
    assert at.header[0].value == "Minhas doações"
    sem_jargao(at)


def test_doador_monta_doacao_com_varios_itens_confere_total_e_envia(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["donor_a"])
    # passo 1 · itens (entrada manual)
    preenche_item(at, 0, "item-tecnico-ui-1", "GRAOS_CEREAIS", 3.0, 5.0, "kg", emb="pacote")
    assert any(m.label == "Total da doação" and m.value == "15 kg" for m in at.metric)
    preenche_item(at, 1, "item-tecnico-ui-2", "INDUSTRIALIZADOS", 4.0, 900.0, "ml", mes_ano=("12", "2027"), emb="garrafa")
    assert any(m.label == "Total da doação" and m.value == "18,312 kg" for m in at.metric), [m.value for m in at.metric]
    t = textos(at)
    assert "peso estimado" in t and "último dia do mês" in t
    assert "3 × pacote de 5 kg = 15 kg" in t
    sem_jargao(at)
    # validação de campo obrigatório (sem chamar a API): refrigeração sem resposta
    p = "novo2"
    at.text_input(key=f"{p}_nome").set_value("item-tecnico-ui-3")
    at.button(key="add_2").click()
    at.run()
    assert any("Escolha a categoria" in e.value for e in at.error) and any("refrigeração" in e.value for e in at.error)
    # passo 2 · retirada
    [b for b in at.button if b.label.startswith("Continuar para a retirada")][0].click()
    at.run()
    assert not at.exception and "Quando podemos retirar" in textos(at)
    [b for b in at.button if b.label.startswith("Salvar e continuar")][0].click()
    at.run()
    # passo 3 · revisar e enviar (exige confirmação)
    assert "Revise antes de enviar" in textos(at)
    enviar = [b for b in at.button if b.label == "Enviar doação"][0]
    assert enviar.disabled
    sem_jargao(at)
    at.checkbox(key="conf_envio").check()
    at.run()
    [b for b in at.button if b.label == "Enviar doação"][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Doação enviada" in s.value for s in at.success), textos(at)
    sem_jargao(at)
    # Minhas doações: status em destaque, sem dados de IA
    at.sidebar.radio(key="menu").set_value("Minhas doações")
    at.run()
    t = textos(at)
    # a lista é ordenada por data de criação; outros testes da suíte avançam o relógio, então a doação nova pode não estar na 1ª página → confere via API
    minhas = [x for x in client.get("/api/v1/donations?limit=100", headers=world["donor_a"]).json() if any(i.get("produto") == "item-tecnico-ui-1" for i in x["items"])]
    assert minhas and minhas[0]["resumo"]["quantity_kg"] == pytest.approx(18.312) and minhas[0]["match_id"]
    assert "**Pendente**" in t or "**Recusada**" in t or "**Aceita**" in t or "**Rascunho**" in t
    sem_jargao(at)
    libera_capacidade(client, world, world["donor_a"])


def test_doador_texto_gera_itens_sugeridos_que_exigem_conferencia(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["donor_a"])
    texto = world["texts"]["ready"][5]  # texto do SIMULADOR (SIMULATED)
    at.text_area(key="texto_lote_0").set_value(texto)
    at.run()
    [b for b in at.button if b.label.startswith("Sugerir itens")][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    t = textos(at)
    assert "Item sugerido a partir do seu texto" in t and any(b.label == "Conferir e confirmar" for b in at.button)
    sem_jargao(at)
    # tentar enviar sem conferir: a doação não é enviada e o motivo vem em linguagem simples
    [b for b in at.button if b.label.startswith("Continuar para a retirada")][0].click()
    at.run()
    [b for b in at.button if b.label.startswith("Salvar e continuar")][0].click()
    at.run()
    at.checkbox(key="conf_envio").check()
    at.run()
    [b for b in at.button if b.label == "Enviar doação"][0].click()
    at.run()
    assert any("ainda não pode ser enviada" in e.value for e in at.error), textos(at)
    assert "R-VAL" not in textos(at)
    sem_jargao(at)


def test_doador_nao_edita_apos_o_envio_e_pode_criar_nova_doacao(monkeypatch, client, world, clock):
    from tests.test_p3a_rascunho_api import add, d_plus, fin, item, novo_rascunho
    d = novo_rascunho(client, world)
    d = add(client, world, d["id"], item(1, validade_data=d_plus(clock, 30)))
    d = fin(client, world, d["id"])
    assert d["status"] == "READY"
    assert client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5}).status_code == 201
    try:
        at = _run(monkeypatch, client, world["donor_a"])
        # estado de tela antigo (rascunho aberto) de uma doação que já foi enviada: a API recusa a alteração e a tela explica
        at.session_state["draft"] = client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()
        at.session_state["passo"] = 1
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        at.button(key=f"rm_{d['items'][0]['id']}").click()
        at.run()
        assert any("não pode mais ser alterada" in w.value for w in at.warning), textos(at)
        nova = [b for b in at.button if b.label == "Criar nova doação"]
        assert nova
        nova[0].click()
        at.run()
        assert not at.exception and "Itens da doação" in textos(at) and "draft" not in at.session_state
        sem_jargao(at)
    finally:
        libera_capacidade(client, world, world["donor_a"])


def test_doacao_do_fluxo_antigo_nao_abre_no_editor_de_itens(monkeypatch, client, world):
    d = new_ready_donation(client, world, "donor_a", "ready", 6)  # fluxo antigo (lote único), ainda sem envio
    at = _run(monkeypatch, client, world["donor_a"])
    at.sidebar.radio(key="menu").set_value("Minhas doações")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert f"cont_{d['id']}" not in [b.key for b in at.button], "doação sem itens detalhados não oferece 'Continuar editando'"
    assert "Item sem nome" not in textos(at)


# ================================================================== ONG
@pytest.fixture()
def proposta(client, world):
    d = new_ready_donation(client, world, "donor_a", "ready", 7)
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5})
    assert r.status_code == 201, r.text
    full = admin_match(client, world, r.json()["id"])
    assert full["status"] == "PROPOSED" and full["ranking"]
    org = org_token(client, world["admin"], full["ranking"][0]["org_id"])
    yield r.json()["id"], full, org
    libera_capacidade(client, world, world["donor_a"])


def test_ong_ve_proposta_com_analise_recolhivel_e_confirma_antes_de_aceitar(monkeypatch, client, world, proposta):
    mid, full, org = proposta
    at = _run(monkeypatch, client, org)
    assert at.sidebar.radio(key="menu").options == ["Propostas recebidas", "Histórico"]
    t = textos(at)
    assert "Nova proposta de doação" in t and "Responder até" in t and "Prazo:" in t and "km em linha reta" in t
    assert any(e.label == "Análise da IA" for e in at.expander), "bloco recolhível 'Análise da IA'"
    sem_jargao(at)
    aceitar = at.button(key=f"ok_{mid}")
    aceitar.click()
    at.run()
    assert any("aceita** esta doação" in w.value for w in at.warning), "confirmação antes de aceitar"
    assert client.get(f"/api/v1/matches/{mid}", headers=org).json()["status"] == "PROPOSED", "nada muda antes da confirmação"
    at.button(key=f"y_{mid}").click()
    at.run()
    assert client.get(f"/api/v1/matches/{mid}", headers=org).json()["status"] == "ACCEPTED"
    assert "Aceitas — aguardando coleta" in textos(at)
    sem_jargao(at)
    # o doador vê só a situação
    d = next(x for x in client.get("/api/v1/donations?limit=100", headers=world["donor_a"]).json() if x["match_id"] == mid)
    assert d["situacao"].startswith("Uma ONG aceitou") and d["ong_aceita"]
    # histórico da ONG
    at.sidebar.radio(key="menu").set_value("Histórico")
    at.run()
    assert "Aceita — aguardando coleta" in textos(at)
    sem_jargao(at)


def test_ong_recusa_com_confirmacao_e_historico_mostra_recusada(monkeypatch, client, world, proposta):
    mid, full, org = proposta
    at = _run(monkeypatch, client, org)
    at.button(key=f"no_{mid}").click()
    at.run()
    assert any("recusa** esta doação" in w.value for w in at.warning)
    at.button(key=f"n_{mid}").click()  # "Voltar": cancela
    at.run()
    assert client.get(f"/api/v1/matches/{mid}", headers=org).json()["awaiting_my_response"] is True
    at.button(key=f"no_{mid}").click()
    at.run()
    at.button(key=f"y_{mid}").click()
    at.run()
    assert client.get(f"/api/v1/matches/{mid}", headers=org).json()["awaiting_my_response"] is False
    assert "Nenhuma proposta aguardando" in textos(at)
    at.sidebar.radio(key="menu").set_value("Histórico")
    at.run()
    assert "**Recusada**" in textos(at)
    sem_jargao(at)


# ================================================================== ADMIN
def test_admin_ve_visao_tecnica_com_scores_e_aviso_de_lote_misto(monkeypatch, client, world, clock):
    from tests.test_p3a_rascunho_api import BASE, add, d_plus, fin, item, novo_rascunho
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1, validade_data=d_plus(clock, 60)))
    add(client, world, d["id"], item(2, categoria="LATICINIOS_OVOS", quantity=2, unit="caixa", unit_weight=6, unit_weight_unit="kg", validade_data=d_plus(clock, 20), exige_refrigeracao=True))
    d = fin(client, world, d["id"])
    assert d["status"] == "READY"
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    try:
        at = _run(monkeypatch, client, world["admin"])
        assert at.header[0].value == "Visão técnica (admin)"
        at.selectbox(key="adm_match").select(mid)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        t = textos(at)
        assert "LOTE MISTO" in t and "DESCONHECIDO" in t
        assert len(at.dataframe) >= 1 and any("FINAL_SCORE" in df.value.columns for df in at.dataframe), "ADMIN vê scores e ranking"
        assert "Regras eliminatórias" in t and "match_events" in t
    finally:
        libera_capacidade(client, world, world["donor_a"])
    _ = (BASE, proibidas)


# ================================================================== consistência UI × API
def test_destaque_da_situacao_cobre_todos_os_textos_da_api():
    """A interface não importa código da API: este teste garante que todo texto de situação devolvido ao doador tem um destaque (Pendente/Aceita/Recusada/…)."""
    from api.views import SITUACAO_DOACAO, SITUACAO_MATCH
    from app.ui_common import SITUACAO_DESTAQUE, destaque_situacao
    for txt in list(SITUACAO_DOACAO.values()) + list(SITUACAO_MATCH.values()):
        assert any(txt.startswith(ini) for ini, _, _ in SITUACAO_DESTAQUE), f"sem destaque na interface para: {txt}"
    assert destaque_situacao("Aguardando resposta de uma ONG")[0] == "Pendente" and destaque_situacao("Uma ONG aceitou a doação")[0] == "Aceita"
    assert destaque_situacao("Nenhuma ONG disponível no momento")[0] == "Recusada"


# ================================================================== Markdown injection (texto digitado por terceiros)
MALICIOSO = "![x](http://exemplo.invalido/p.png) [clique](http://exemplo.invalido) **a** $x$ :red[z]"


def test_esc_neutraliza_markdown_latex_e_cores():
    from app.ui_common import esc, limpar
    s = esc(MALICIOSO)
    for ativo in ("](", "![", "**", ":red[", "$x$"):
        assert ativo not in s, (ativo, s)
    assert esc(None) == "" and limpar("Prazo curto (R-VAL-2)") == "Prazo curto"


def test_nome_de_alimento_malicioso_nao_vira_link_nem_imagem_na_tela_do_doador(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["donor_a"])
    preenche_item(at, 0, MALICIOSO, "GRAOS_CEREAIS", 1.0, 1.0, "kg", emb="pacote")
    assert not at.exception, [e.value for e in at.exception]
    for md in list(at.markdown) + list(at.caption):
        assert "](" not in str(md.value).replace("\\]\\(", ""), md.value
