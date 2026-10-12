"""Fase 3 Parte 1 (Etapa A) — API de rascunho e itens: criação, itens manuais, conversão para kg, agregação do lote, finalização, bloqueios, propriedade, limites.
Doador = conta de DEMONSTRAÇÃO sobre doador SIMULADO do simulador (data_origin=SIMULATED). Os itens manuais usam rótulos técnicos de teste ("item-tecnico-N") e valores técnicos."""
import dataclasses
import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import models as m
from database.session import session_scope

BASE = "/api/v1/donations"


def d_plus(clock, n):
    return (clock().astimezone(dt.timezone(dt.timedelta(hours=-3))).date() + dt.timedelta(days=n)).isoformat()


def novo_rascunho(client, world, donor="donor_a", **kw):
    r = client.post(f"{BASE}/drafts", headers=world[donor], json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def item(n=1, **kw):
    base = {"produto": f"item-tecnico-{n}", "categoria": "GRAOS_CEREAIS", "quantity": 3, "unit": "pacote", "unit_weight": 5, "unit_weight_unit": "kg", "exige_refrigeracao": False}
    base.update(kw)
    return base


def add(client, world, did, body, donor="donor_a"):
    r = client.post(f"{BASE}/{did}/items", headers=world[donor], json=body)
    assert r.status_code == 201, r.text
    return r.json()


def fin(client, world, did, donor="donor_a"):
    r = client.post(f"{BASE}/{did}/finalize", headers=world[donor])
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ rascunho vazio e itens
def test_rascunho_vazio_nao_finaliza(client, world):
    d = novo_rascunho(client, world)
    assert d["perfil"] == "DONOR" and d["status"] == "DRAFT" and d["items"] == [] and d["resumo"]["n_items"] == 0 and d["data_origin"] == "SIMULATED"
    r = client.post(f"{BASE}/{d['id']}/finalize", headers=world["donor_a"])
    assert r.status_code == 422


def test_item_manual_converte_para_kg_e_agrega_no_cabecalho(client, world, clock):
    d = novo_rascunho(client, world)
    d = add(client, world, d["id"], item(1, validade_mes_ano="12/2027"))
    it = d["items"][0]
    assert it["quantity_kg"] == 15.0 and not it["weight_estimated"] and it["entry_source"] == "MANUAL" and it["pending_fields"] == []
    assert it["perecibilidade"] == "NAO_PERECIVEL"  # derivada da categoria (taxonomia), nunca digitada
    assert it["validity_precision"] == "MONTH" and it["expires_at"].startswith("2027-12-31T23:59:59") and "último dia do mês" in it["validity_note"]
    assert d["quantity_kg"] == 15.0 and d["resumo"]["categories"] == ["GRAOS_CEREAIS"] and not d["resumo"]["is_mixed_batch"]
    assert any("mês/ano" in a for a in d["alertas"])
    assert d["status"] == "DRAFT"


def test_item_em_volume_usa_massa_por_litro_da_taxonomia_e_avisa(client, world, clock):
    d = novo_rascunho(client, world)
    d = add(client, world, d["id"], item(2, categoria="INDUSTRIALIZADOS", quantity=4, unit="garrafa", unit_weight=900, unit_weight_unit="ml", validade_data=d_plus(clock, 90)))
    it = d["items"][0]
    assert it["quantity_kg"] == pytest.approx(3.312) and it["weight_estimated"] and "0.92" in it["weight_note"] and "premissa sem fonte" in it["weight_note"]
    assert any("peso ESTIMADO" in a for a in d["alertas"])
    with session_scope() as s:
        row = s.get(m.DonationItem, it["id"])
        assert row.weight_basis == "VOLUME_CONVERTIDO" and row.unit_weight == 900 and row.unit_weight_unit == "ml"


def test_lote_misto_e_agregacao_conservadora(client, world, clock):
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1, validade_data=d_plus(clock, 200)))
    d = add(client, world, d["id"], item(2, categoria="LATICINIOS_OVOS", quantity=2, unit="caixa", unit_weight=12, unit_weight_unit="kg", validade_data=d_plus(clock, 9), exige_refrigeracao=True))
    r = d["resumo"]
    assert r["quantity_kg"] == pytest.approx(15.0 + 24.0) and r["is_mixed_batch"] and set(r["categories"]) == {"GRAOS_CEREAIS", "LATICINIOS_OVOS"}
    assert r["validity_days"] == 9, "a validade do lote é a do item mais próximo"
    assert r["exige_refrigeracao"] is True and r["perecibilidade"] == "PERECIVEL_REFRIGERADO_CONGELADO"
    assert d["categoria"] == "LATICINIOS_OVOS"  # categoria predominante = a de maior peso (24 kg de laticínios × 15 kg de grãos)
    assert any("Lote misto" in a and "DESCONHECIDO" in a for a in d["alertas"])
    assert any("validades muito diferentes" in a for a in d["alertas"]), "diferença de 191 dias > limite de aviso"
    with session_scope() as s:
        row = s.get(m.Donation, d["id"])
        assert row.is_mixed_batch and sorted(row.categories) == ["GRAOS_CEREAIS", "LATICINIOS_OVOS"] and row.aggregated_at is not None


# ------------------------------------------------------------------ finalização e bloqueios
def test_finalizar_ready_com_todos_os_campos(client, world, clock):
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1, validade_data=d_plus(clock, 30)))
    d = fin(client, world, d["id"])
    assert d["status"] == "READY" and d["confirmed_at"] and d["situacao"].startswith("Pronta")


def test_refrigeracao_nao_informada_deixa_pendente(client, world, clock):
    d = novo_rascunho(client, world)
    body = item(1, validade_data=d_plus(clock, 30))
    body.pop("exige_refrigeracao")
    d = add(client, world, d["id"], body)
    assert d["items"][0]["missing_fields"] == ["exige_refrigeracao"] and d["resumo"]["exige_refrigeracao"] is None
    d = fin(client, world, d["id"])
    assert d["status"] == "PENDING_CONFIRMATION" and "exige_refrigeracao" in d["block_reason"]
    r = client.patch(f"{BASE}/{d['id']}/items/{d['items'][0]['id']}", headers=world["donor_a"], json={"exige_refrigeracao": False})
    assert r.status_code == 200 and r.json()["status"] == "DRAFT"  # editar volta a rascunho
    assert fin(client, world, d["id"])["status"] == "READY"


def test_validade_vencida_bloqueia_ate_remover_o_item(client, world, clock):
    d = novo_rascunho(client, world)
    ok = add(client, world, d["id"], item(1, validade_data=d_plus(clock, 20)))
    d = add(client, world, d["id"], item(2, validade_data=d_plus(clock, -1)))
    d = fin(client, world, d["id"])
    assert d["status"] == "BLOCKED_EXPIRED" and "item-tecnico-2" in d["block_reason"]
    assert client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]}).status_code == 409
    vencido = next(i for i in d["items"] if i["produto"] == "item-tecnico-2")
    r = client.delete(f"{BASE}/{d['id']}/items/{vencido['id']}", headers=world["donor_a"])
    assert r.status_code == 200 and [i["produto"] for i in r.json()["items"]] == [ok["items"][0]["produto"]]
    assert fin(client, world, d["id"])["status"] == "READY"


def test_item_sem_validade_bloqueia(client, world):
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1))
    d = fin(client, world, d["id"])
    assert d["status"] == "BLOCKED_NO_VALIDITY" and "item-tecnico-1" in d["block_reason"]


def test_editar_doacao_ready_volta_a_rascunho_e_match_trava_edicao(client, world, clock):
    d = novo_rascunho(client, world)
    d = add(client, world, d["id"], item(1, validade_data=d_plus(clock, 30)))
    d = fin(client, world, d["id"])
    assert d["status"] == "READY"
    d = client.patch(f"{BASE}/{d['id']}/items/{d['items'][0]['id']}", headers=world["donor_a"], json={"quantity": 4}).json()
    assert d["status"] == "DRAFT" and d["quantity_kg"] == 20.0 and d["confirmed_at"] is None
    d = fin(client, world, d["id"])
    mt = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]})
    assert mt.status_code == 201, mt.text
    assert client.post(f"{BASE}/{d['id']}/items", headers=world["donor_a"], json=item(9, validade_data=d_plus(clock, 30))).status_code == 409
    # limpa: recusa até esgotar para liberar capacidade reservada
    mj = mt.json()
    for _ in range(40):
        if mj["status"] != "PROPOSED":
            break
        mj = client.post(f"/api/v1/matches/{mj['id']}/respond", headers=world["admin"], json={"accept": False}).json()


def test_fluxo_antigo_de_confirmacao_recusa_doacao_com_itens(client, world, clock):
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1, validade_data=d_plus(clock, 30)))
    r = client.patch(f"{BASE}/{d['id']}/confirm", headers=world["donor_a"], json={"quantidade_kg": 5})
    assert r.status_code == 409


# ------------------------------------------------------------------ propriedade e perfis
def test_outro_doador_nao_ve_nem_edita_e_admin_ve_tudo(client, world, clock):
    d = novo_rascunho(client, world)
    did = d["id"]
    for meth, path, body in (("GET", f"{BASE}/{did}", None), ("GET", f"{BASE}/{did}/items", None), ("POST", f"{BASE}/{did}/items", item(1)),
                             ("PATCH", f"{BASE}/{did}/draft", {"contem_alergenico": True}), ("POST", f"{BASE}/{did}/finalize", None)):
        r = client.request(meth, path, headers=world["donor_b"], json=body)
        assert r.status_code == 403, (meth, path, r.status_code)
    a = add(client, world, did, item(1, validade_data=d_plus(clock, 10)))
    v = client.get(f"{BASE}/{did}", headers=world["admin"]).json()
    assert v["perfil"] == "ADMIN" and v["items"][0]["weight_basis"] == "MASSA_INFORMADA" and "parser_suggestion" in v["items"][0] and a["items"]
    # ORG não opera doações
    assert client.get(f"{BASE}/{did}", headers=world["admin"]).status_code == 200


def test_entradas_estritas(client, world, clock):
    d = novo_rascunho(client, world)
    u = f"{BASE}/{d['id']}/items"
    h = world["donor_a"]
    v = d_plus(clock, 10)
    assert client.post(u, headers=h, json={**item(1), "campo_extra": 1}).status_code == 422
    assert client.post(u, headers=h, json=item(1, unit_weight_unit="arroba")).status_code == 422
    assert client.post(u, headers=h, json=item(1, unit_weight=0)).status_code == 422
    assert client.post(u, headers=h, json=item(1, quantity=-1)).status_code == 422
    assert client.post(u, headers=h, json=item(1, categoria="XYZ")).status_code == 422
    assert client.post(u, headers=h, json=item(1, validade_data=v, validade_mes_ano="12/2027")).status_code == 422
    assert client.post(u, headers=h, json=item(1, validade_mes_ano="13/2027")).status_code == 422
    assert client.post(f"{BASE}/drafts", headers=h, json={"dias_retirada": []}).status_code == 422
    assert client.post(f"{BASE}/drafts", headers=h, json={"janela_retirada_inicio_h": 10, "janela_retirada_fim_h": 9}).status_code == 422
    assert client.patch(f"{BASE}/{d['id']}/items/999999999", headers=h, json={"quantity": 1}).status_code == 404


def test_limite_de_itens_configuravel(client, world, clock, monkeypatch):
    from api.routers import drafts
    monkeypatch.setattr(drafts, "DONATION", dataclasses.replace(drafts.DONATION, max_items=2))
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1, validade_data=d_plus(clock, 10)))
    add(client, world, d["id"], item(2, validade_data=d_plus(clock, 10)))
    assert client.post(f"{BASE}/{d['id']}/items", headers=world["donor_a"], json=item(3, validade_data=d_plus(clock, 10))).status_code == 422


def test_item_herda_origem_da_doacao_e_o_banco_recusa_origem_diferente(client, world, clock):
    d = novo_rascunho(client, world)
    d = add(client, world, d["id"], item(1, validade_data=d_plus(clock, 10)))
    with session_scope() as s:
        don = s.get(m.Donation, d["id"])
        assert all(i.data_origin == don.data_origin == "SIMULATED" for i in don.items)
        assert don.items[0].generator_version == don.generator_version  # rastreio do simulador herdado
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            s.add(m.DonationItem(donation_id=d["id"], data_origin="USER_ENTERED", produto="x"))


def test_pesos_do_item_no_banco_exigem_par_valor_unidade(client, world, clock):
    d = novo_rascunho(client, world)
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            don = s.get(m.Donation, d["id"])
            s.add(m.DonationItem(donation_id=don.id, data_origin=don.data_origin, generator_version=don.generator_version, seed=don.seed, dataset_version=don.dataset_version,
                                 produto="x", unit_weight=1.0, unit_weight_unit=None))


# ------------------------------------------------------------------ texto → itens SUGERIDOS
def test_pre_visualizacao_do_texto_nao_grava_doacao(client, world):
    texto = world["texts"]["ready"][0]
    with session_scope() as s:
        n0 = len(s.scalars(select(m.Donation.id)).all())
        i0 = len(s.scalars(select(m.DonationItem.id)).all())
    r = client.post(f"{BASE}/items/parse-preview", headers=world["donor_a"], json={"texto": texto})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["items"] and all("revisao_do_item" in i["pending_fields"] for i in j["items"]) and j["training_data_origin"] == "SIMULATED" and "não afirma" in j["aviso"]
    with session_scope() as s:
        assert len(s.scalars(select(m.Donation.id)).all()) == n0 and len(s.scalars(select(m.DonationItem.id)).all()) == i0


def test_itens_sugeridos_do_texto_exigem_confirmacao(client, world, clock):
    d = novo_rascunho(client, world, texto=world["texts"]["ready"][1])
    assert d["status"] == "DRAFT" and d["items"] and all(i["entry_source"] == "TEXTO_SUGERIDO" and "revisao_do_item" in i["pending_fields"] for i in d["items"])
    d = fin(client, world, d["id"])
    assert d["status"] in ("PENDING_CONFIRMATION", "BLOCKED_NO_VALIDITY", "BLOCKED_EXPIRED"), "sugestões nunca viram READY sem a confirmação do doador"
    # confirmar um item incompleto é recusado
    it = d["items"][0]
    if it["missing_fields"]:
        r = client.patch(f"{BASE}/{d['id']}/items/{it['id']}", headers=world["donor_a"], json={"confirm_item": True})
        assert r.status_code == 422
    # aceitar campo sem valor sugerido é recusado
    r = client.patch(f"{BASE}/{d['id']}/items/{it['id']}", headers=world["donor_a"], json={"accept_fields": ["peso_por_unidade"]}) if it["unit_weight"] is None else None
    if r is not None:
        assert r.status_code == 422


def test_doador_completa_e_confirma_item_sugerido_e_finaliza(client, world, clock):
    d = novo_rascunho(client, world, texto=world["texts"]["ready"][2])
    for extra in d["items"][1:]:  # o doador remove fragmentos que não são itens e completa o primeiro
        assert client.delete(f"{BASE}/{d['id']}/items/{extra['id']}", headers=world["donor_a"]).status_code == 200
    d = client.get(f"{BASE}/{d['id']}", headers=world["donor_a"]).json()
    it = d["items"][0]
    body = {"categoria": "GRAOS_CEREAIS", "quantity": 1, "unit_weight": 10, "unit_weight_unit": "kg", "validade_data": d_plus(clock, 30), "exige_refrigeracao": False, "confirm_item": True}
    r = client.patch(f"{BASE}/{d['id']}/items/{it['id']}", headers=world["donor_a"], json=body)
    assert r.status_code == 200, r.text
    got = r.json()["items"][0]
    assert got["pending_fields"] == [] and got["entry_source"] == "TEXTO_SUGERIDO" and got["quantity_kg"] == 10.0
    assert fin(client, world, d["id"])["status"] == "READY"
