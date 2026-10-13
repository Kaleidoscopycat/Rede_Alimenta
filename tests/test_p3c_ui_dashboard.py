"""Fase 3 Parte 2 (Etapa A): AppTest do dashboard do ADMIN. Cada tela renderiza sem exceção e traz selos de origem / avisos obrigatórios; DONOR e ORG não veem o menu do dashboard."""
import pytest

from tests.test_p3b_ui_apptest import _run, textos

TELAS = ["Overview", "Doações e matches", "Mapa", "Organizações", "Doadores", "Dados públicos", "Indicadores territoriais", "IA", "Recomendações", "Logística", "Segurança e sistema"]


def test_admin_menu_completo(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["admin"])
    assert at.sidebar.radio(key="menu").options == TELAS + ["Visão técnica (admin)"]
    assert at.header[0].value == "Overview"


@pytest.mark.parametrize("tela", TELAS)
def test_cada_tela_renderiza(monkeypatch, client, world, tela):
    at = _run(monkeypatch, client, world["admin"])
    at.sidebar.radio(key="menu").set_value(tela)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.header[0].value.startswith(tela.split(" e ")[0].split(" — ")[0][:6])


def test_overview_selos_premissa_e_nomenclatura(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["admin"])
    t = textos(at)
    assert "0,4" in t or "0.4" in t, "premissa de refeições exibida"
    assert "SIMULADO" in t and "PÚBLICO" in t
    assert not any("salvo" in x.label.lower() for x in at.metric), "“kg salvos” não é rótulo de indicador (usamos ofertado/coletado)"
    assert "Nenhuma doação real registrada." in t


def test_ia_rotulada_como_simulada(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["admin"])
    at.sidebar.radio(key="menu").set_value("IA")
    at.run()
    t = textos(at)
    for termo in ("MRR", "Top-1", "ROC-AUC", "PR-AUC", "MANUALLY_LABELED", "SIMULADOS"):
        assert termo in t, termo


def test_logistica_simula(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["admin"])
    at.sidebar.radio(key="menu").set_value("Logística")
    at.run()
    at.button[0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert "SIMULAÇÃO" in textos(at)


def test_donor_nao_ve_dashboard(monkeypatch, client, world):
    at = _run(monkeypatch, client, world["donor_a"])
    assert "Overview" not in at.sidebar.radio(key="menu").options
