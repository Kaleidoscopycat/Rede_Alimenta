"""Fase 3 Parte 1 (Etapa A) — funções PURAS: conversão de peso/volume para kg, validade mês/ano e agregação do lote.
As entradas são valores técnicos de teste das funções (não representam doações, doadores ou produtos reais e nada disso é gravado)."""
import datetime as dt

import pytest

from api import item_rules as r
from api.aggregation import PERECIB_RANK, ItemAgg, aggregate
from core.settings import DONATION, TZ

NOW = dt.datetime(2026, 10, 13, 13, 0, tzinfo=dt.timezone.utc)  # terça 10:00 em Brasília


def eod(y, mth, d):
    return dt.datetime(y, mth, d, 23, 59, 59, tzinfo=TZ)


# ------------------------------------------------------------------ peso e volume → kg
@pytest.mark.parametrize("n,w,u,kg", [(3, 5, "kg", 15.0), (6, 500, "g", 3.0), (1, 250, "g", 0.25), (2, 1.5, "kg", 3.0)])
def test_massa_informada_converte_sem_estimativa(n, w, u, kg):
    x = r.item_weight(n, w, u, "GRAOS_CEREAIS", {})
    assert x.quantity_kg == pytest.approx(kg) and x.basis == r.BASIS_MASS and not x.estimated and x.note is None


def test_volume_usa_massa_por_litro_da_categoria_e_marca_estimativa():
    x = r.item_weight(4, 900, "ml", "INDUSTRIALIZADOS", {"litro": 0.92})
    assert x.quantity_kg == pytest.approx(4 * 0.9 * 0.92) and x.basis == r.BASIS_VOLUME and x.estimated
    assert "premissa sem fonte" in x.note and "0.92" in x.note


def test_volume_sem_massa_por_litro_usa_densidade_padrao_configurada():
    x = r.item_weight(2, 1, "l", "LATICINIOS_OVOS", {})
    assert x.quantity_kg == pytest.approx(2 * DONATION.default_density_kg_per_l) and x.estimated
    assert "densidade padrão" in x.note


def test_peso_ou_quantidade_ausente_nao_inventa_valor():
    assert r.item_weight(None, 5, "kg", "FRUTAS", {}).quantity_kg is None
    assert r.item_weight(3, None, None, "FRUTAS", {}).quantity_kg is None


def test_unidade_invalida_e_limite_de_peso():
    with pytest.raises(ValueError):
        r.item_weight(1, 1, "arroba", "FRUTAS", {})
    with pytest.raises(ValueError):
        r.item_weight(DONATION.max_total_kg, 2, "kg", "FRUTAS", {})


def test_massa_unitaria_da_taxonomia_so_e_sugestao():
    assert r.category_unit_mass("caixa", "FRUTAS", {"caixa": 20.0}) == 20.0
    assert r.category_unit_mass("caixa", "FRUTAS", {}) is None


# ------------------------------------------------------------------ validade
def test_mes_ano_vira_ultimo_dia_do_mes_inclusive_fevereiro():
    assert r.parse_month_year("12/2027") == dt.date(2027, 12, 31)
    assert r.parse_month_year("2028-02") == dt.date(2028, 2, 29)  # bissexto
    assert r.parse_month_year("02/2027") == dt.date(2027, 2, 28)
    for ruim in ("13/2027", "00/2027", "2027", "ab/2027", "1/2027"):
        assert r.parse_month_year(ruim) is None


def test_validade_vale_ate_o_fim_do_dia_em_sao_paulo_e_aviso_conservador():
    e = r.end_of_day(dt.date(2027, 12, 31))
    assert e == eod(2027, 12, 31) and e.tzinfo is not None
    assert "último dia do mês" in r.validity_note("MONTH", e)
    assert r.validity_note("DAY", e) is None


# ------------------------------------------------------------------ agregação do lote
def ia(i, cat, kg, exp, refrig, per):
    return ItemAgg(i, cat, f"p{i}", kg, exp, refrig, per)


def test_agregacao_soma_validade_mais_proxima_e_refrigeracao_se_qualquer():
    a = aggregate([ia(1, "GRAOS_CEREAIS", 15.0, eod(2027, 12, 31), False, "NAO_PERECIVEL"), ia(2, "GRAOS_CEREAIS", 5.0, eod(2027, 8, 31), False, "NAO_PERECIVEL"),
                   ia(3, "LATICINIOS_OVOS", 3.0, eod(2026, 10, 20), True, "PERECIVEL_REFRIGERADO_CONGELADO")], NOW)
    assert a.quantity_kg == pytest.approx(23.0) and not a.incomplete_weight
    assert a.expires_at == eod(2026, 10, 20) and a.validity_days == 7 and a.nearest_item_ids == [3]
    assert a.exige_refrigeracao is True
    assert a.perecibilidade == "PERECIVEL_REFRIGERADO_CONGELADO"  # a mais restritiva
    assert a.categoria == "GRAOS_CEREAIS" and a.categories == ["GRAOS_CEREAIS", "LATICINIOS_OVOS"] and a.is_mixed_batch


def test_categoria_do_lote_e_a_de_maior_peso_com_desempate_pela_mais_perecivel():
    a = aggregate([ia(1, "FRUTAS", 10.0, eod(2026, 11, 1), False, "PERECIVEL_BAIXO_RISCO"), ia(2, "PANIFICADOS", 10.0, eod(2026, 11, 1), False, "PERECIVEL_REFRIGERADO_CONGELADO")], NOW)
    assert a.categoria == "PANIFICADOS" and a.categories[0] == "PANIFICADOS"
    b = aggregate([ia(1, "FRUTAS", 30.0, eod(2026, 11, 1), False, "PERECIVEL_BAIXO_RISCO"), ia(2, "PANIFICADOS", 10.0, eod(2026, 11, 1), False, "PERECIVEL_REFRIGERADO_CONGELADO")], NOW)
    assert b.categoria == "FRUTAS"


def test_lote_de_uma_categoria_nao_e_misto():
    a = aggregate([ia(1, "FRUTAS", 1.0, eod(2026, 11, 1), False, "PERECIVEL_BAIXO_RISCO"), ia(2, "FRUTAS", 2.0, eod(2026, 11, 3), False, "PERECIVEL_BAIXO_RISCO")], NOW)
    assert not a.is_mixed_batch and a.categories == ["FRUTAS"]


def test_peso_incompleto_e_refrigeracao_desconhecida_nao_sao_inventados():
    a = aggregate([ia(1, "FRUTAS", 4.0, eod(2026, 11, 1), None, "PERECIVEL_BAIXO_RISCO"), ia(2, "FRUTAS", None, eod(2026, 11, 3), False, "PERECIVEL_BAIXO_RISCO")], NOW)
    assert a.quantity_kg == 4.0 and a.incomplete_weight
    assert a.exige_refrigeracao is None  # nenhum item exige, mas um é desconhecido
    c = aggregate([ia(1, "FRUTAS", None, None, None, None)], NOW)
    assert c.quantity_kg is None and c.expires_at is None and c.validity_days is None


def test_lote_vazio():
    a = aggregate([], NOW)
    assert a.n_items == 0 and a.quantity_kg is None and not a.is_mixed_batch


def test_aviso_de_validades_muito_diferentes_e_sugestao_de_separar():
    perto, longe = eod(2026, 10, 20), eod(2027, 6, 30)
    a = aggregate([ia(1, "FRUTAS", 1.0, perto, False, "PERECIVEL_BAIXO_RISCO"), ia(2, "GRAOS_CEREAIS", 1.0, longe, False, "NAO_PERECIVEL")], NOW)
    assert a.spread_warning and a.spread_days > DONATION.validity_spread_warn_days and a.short_validity_item_ids == [1]
    b = aggregate([ia(1, "FRUTAS", 1.0, perto, False, "PERECIVEL_BAIXO_RISCO"), ia(2, "FRUTAS", 1.0, eod(2026, 10, 25), False, "PERECIVEL_BAIXO_RISCO")], NOW)
    assert not b.spread_warning
    c = aggregate([ia(1, "FRUTAS", 1.0, perto, False, "PERECIVEL_BAIXO_RISCO"), ia(2, "GRAOS_CEREAIS", 1.0, longe, False, "NAO_PERECIVEL")], NOW, spread_warn_days=1000)
    assert not c.spread_warning  # limite configurável


def test_ordem_de_risco_cobre_todas_as_perecibilidades_do_parser():
    from ml.semantic.classifier import PERECIB
    assert set(PERECIB_RANK) == set(PERECIB)
    assert [PERECIB_RANK[p] for p in PERECIB] == sorted(PERECIB_RANK[p] for p in PERECIB), "a ordem do parser deve ser crescente em risco"
