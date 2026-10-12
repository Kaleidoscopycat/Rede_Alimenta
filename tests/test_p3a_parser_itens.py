"""Fase 3 Parte 1 (Etapa A) — parser de texto livre EM ITENS (api/item_parser.py).
O texto de regressão abaixo é usado SOMENTE para testar o parser (função pura): NADA é gravado como doação, doador, ONG ou produto real."""
import datetime as dt
from pathlib import Path

import pytest
import yaml

from api.item_parser import merge_segments, parse_items, parse_validity, split_segments
from api.parsing import ParserService

ROOT = Path(__file__).resolve().parents[1]
HOJE = dt.date(2026, 10, 13)
TEXTO_REGRESSAO = ("arroz agulhinha tipo 1 (pacote de 5 kg, 3 unidades, validade 12/2027), feijão carioca (pacote de 1 kg, 5 unidades, validade 08/2027), "
                   "macarrão espaguete (pacote de 500 g, 6 unidades, validade 05/2028) e óleo de soja (garrafa de 900 ml, 4 unidades, validade 10/2027)")


@pytest.fixture(scope="module")
def svc():
    return ParserService()


@pytest.fixture(scope="module")
def taxonomia():
    y = yaml.safe_load((ROOT / "simulation" / "config" / "taxonomy_v0.2.yaml").read_text(encoding="utf-8"))["categories"]
    return {c: dict(v.get("unit_mass_kg", {})) for c, v in y.items()}, {c: v["perecibilidade"] for c, v in y.items()}


def run(svc, taxonomia, texto):
    um, cp = taxonomia
    return parse_items(svc, texto, HOJE, um, cp, 30)


def test_regressao_quatro_itens_com_pacote_unidades_e_validade_mes_ano(svc, taxonomia):
    res = run(svc, taxonomia, TEXTO_REGRESSAO)
    its = res["items"]
    assert [i["produto"] for i in its] == ["arroz agulhinha tipo 1", "feijão carioca", "macarrão espaguete", "óleo de soja"]
    assert [i["quantity"] for i in its] == [3, 5, 6, 4]
    assert [i["unit"] for i in its] == ["pacote", "pacote", "pacote", "garrafa"]
    assert [(i["unit_weight"], i["unit_weight_unit"]) for i in its] == [(5, "kg"), (1, "kg"), (500, "g"), (900, "ml")]
    assert [round(i["quantity_kg"], 3) for i in its] == [15.0, 5.0, 3.0, 3.312]  # óleo: 4 × 0,9 L × 0,92 kg/L (premissa da taxonomia, sem fonte)
    assert [i["weight_estimated"] for i in its] == [False, False, False, True]
    assert its[3]["weight_basis"] == "VOLUME_CONVERTIDO" and any("premissa sem fonte" in n for n in its[3]["notes"])
    # validade mês/ano → último dia do mês, aviso e pendência de confirmação
    assert [i["expires_at"].date().isoformat() for i in its] == ["2027-12-31", "2027-08-31", "2028-05-31", "2027-10-31"]
    assert all(i["validity_precision"] == "MONTH" and i["validity_source"] == "SUGERIDA_PELO_TEXTO" for i in its)
    assert all(any("último dia do mês" in n for n in i["notes"]) for i in its)
    assert all("validade" in i["pending_fields"] for i in its)
    # tudo vindo do texto é SUGESTÃO: o item inteiro e a refrigeração exigem confirmação do doador
    assert all("revisao_do_item" in i["pending_fields"] and "exige_refrigeracao" in i["pending_fields"] for i in its)
    assert [i["categoria"] for i in its] == ["GRAOS_CEREAIS", "GRAOS_CEREAIS", "GRAOS_CEREAIS", "INDUSTRIALIZADOS"]
    assert all(i["perecibilidade"] == "NAO_PERECIVEL" for i in its)
    assert res["training_data_origin"] == "SIMULATED" and "simulado" in res["threshold_note"]


def test_parser_e_funcao_pura_nao_grava_nada(svc, taxonomia, p2_db):
    from sqlalchemy import func, select
    from database import models as m
    from database.session import session_scope

    def contagens():
        with session_scope() as s:
            return tuple(s.scalar(select(func.count()).select_from(t)) for t in (m.Donation, m.DonationItem, m.Donor, m.MlPrediction))

    antes = contagens()
    run(svc, taxonomia, TEXTO_REGRESSAO)
    assert contagens() == antes


def test_categoria_incerta_fica_pendente(svc, taxonomia):
    res = run(svc, taxonomia, "doacao de comida (varias caixas)")
    assert "categoria" in res["items"][0]["pending_fields"] or res["items"][0]["categoria"] is None


def test_sem_peso_ou_validade_nada_e_inventado(svc, taxonomia):
    it = run(svc, taxonomia, "tomate 2 caixas")["items"][0]
    assert it["quantity"] == 2 and it["unit"] == "caixa"
    assert it["unit_weight"] is None and it["quantity_kg"] is None and it["expires_at"] is None
    assert {"peso_por_unidade", "validade"} <= set(it["pending_fields"])


def test_massa_total_sem_embalagem_assume_uma_unidade_e_pede_confirmacao(svc, taxonomia):
    it = run(svc, taxonomia, "5 kg de arroz")["items"][0]
    assert it["produto"] == "arroz" and it["unit_weight"] == 5 and it["quantity"] == 1 and it["quantity_kg"] == 5
    assert "quantidade" in it["pending_fields"] and any("assumimos 1" in n for n in it["notes"])


def test_volume_nao_vira_contagem_de_embalagens(svc, taxonomia):
    it = run(svc, taxonomia, "leite 12 litros")["items"][0]
    assert it["unit_weight"] == 12 and it["unit_weight_unit"] == "l" and it["quantity"] == 1
    assert it["quantity_kg"] < 20, "12 L não pode virar 12 embalagens de 12 L"


def test_separacao_em_itens_respeita_parenteses_e_virgulas_de_dentro():
    assert split_segments("arroz (pacote de 5 kg, 3 unidades), feijão; milho e trigo") == ["arroz (pacote de 5 kg, 3 unidades)", "feijão", "milho", "trigo"]
    assert merge_segments(["arroz", "validade 12/2027"]) == ["arroz, validade 12/2027"]


def test_limite_de_itens_e_aviso(svc, taxonomia):
    um, cp = taxonomia
    res = parse_items(svc, ", ".join(f"arroz {i} (pacote de 1 kg, 1 unidade)" for i in range(40)), HOJE, um, cp, 5)
    assert len(res["items"]) == 5 and res["alerts"]


@pytest.mark.parametrize("txt,esperado", [("12/2027", (dt.date(2027, 12, 31), "MONTH")), ("2028-02", (dt.date(2028, 2, 29), "MONTH")), ("05/11/2026", (dt.date(2026, 11, 5), "DAY")),
                                          ("2026-11-05", (dt.date(2026, 11, 5), "DAY")), ("31/02/2026", (None, None)), ("13/2027", (None, None))])
def test_formatos_de_validade(txt, esperado):
    assert parse_validity(txt) == esperado
