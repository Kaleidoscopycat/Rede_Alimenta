"""Fase 3 Parte 1 (Etapa A) — lote misto no motor de match: a ONG precisa aceitar TODAS as categorias; o alerta de limitação (ranker só treinado com 1 categoria) vai ao ADMIN e à ONG."""
from sqlalchemy import select

from database import models as m
from database.session import session_scope
from match import lifecycle
from match.eligibility import RULES
from tests.helpers_p2 import admin_match, org_token
from tests.test_p2_match import _ctx, _eval, _prep
from tests.test_p3a_rascunho_api import BASE, add, d_plus, fin, item, novo_rascunho


def test_elegibilidade_exige_todas_as_categorias_do_lote(client, world):
    o = _prep()
    o["aceita_FRUTAS_declarado"] = True
    assert _eval(o, _ctx(categorias=("HORT_FRUTOS", "FRUTAS")))["eligible"].all()
    o.loc[0, "aceita_FRUTAS_declarado"] = False  # uma ONG deixa de aceitar a 2ª categoria
    r = _eval(o, _ctx(categorias=("HORT_FRUTOS", "FRUTAS")))
    assert r["fail"]["E_CATEGORIA_NAO_ACEITA"][0] and not r["eligible"][0] and r["eligible"][1:].all()
    assert "E_CATEGORIA_NAO_ACEITA" in RULES
    # sem `categorias` (doações antigas/históricas) o comportamento é o de sempre: só a categoria principal
    assert _eval(o, _ctx())["eligible"].all()


def test_contexto_do_match_leva_todas_as_categorias_e_alerta_de_lote_misto(client, world, clock):
    d = novo_rascunho(client, world)
    add(client, world, d["id"], item(1, categoria="HORT_FRUTOS", quantity=1, unit="caixa", unit_weight=10, unit_weight_unit="kg", validade_data=d_plus(clock, 6)))
    d = add(client, world, d["id"], item(2, categoria="FRUTAS", quantity=1, unit="caixa", unit_weight=8, unit_weight_unit="kg", validade_data=d_plus(clock, 6)))
    d = fin(client, world, d["id"])
    assert d["status"] == "READY" and d["resumo"]["is_mixed_batch"]
    with session_scope() as s:
        ctx = lifecycle.build_ctx(s, s.get(m.Donation, d["id"]), clock())
        assert set(ctx.categorias) == {"HORT_FRUTOS", "FRUTAS"} and ctx.categoria in ctx.categorias and ctx.quantity_kg == 18.0
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]})
    assert r.status_code == 201, r.text
    full = admin_match(client, world, r.json()["id"])
    alertas = full["eligibility"]["alertas"]
    assert any("Lote misto" in a and "DESCONHECIDO" in a for a in alertas)
    assert "Lote misto" not in str(r.json()), "o doador não recebe o detalhe técnico do motor"
    # toda candidata aceita as duas categorias (declaradas simuladas)
    from api.state import STATE
    orgs = STATE.engine.orgs.set_index("org_uuid")
    for c in full["ranking"]:
        row = orgs.loc[c["org_id"]] if c["org_id"] in orgs.index else orgs.loc[__import__("uuid").UUID(c["org_id"])]
        assert bool(row["aceita_HORT_FRUTOS_declarado"]) and bool(row["aceita_FRUTAS_declarado"])
    if full["status"] == "PROPOSED":
        org = org_token(client, world["admin"], full["ranking"][0]["org_id"])
        v = client.get(f"/api/v1/matches/{full['id']}", headers=org).json()
        assert v["donation"]["resumo"]["is_mixed_batch"] and any("Lote misto" in a for a in v["donation"]["analise"])
        assert len(v["donation"]["items"]) == 2
    mid, st = full["id"], full["status"]
    for _ in range(40):  # libera capacidade reservada
        if st != "PROPOSED":
            break
        st = client.post(f"/api/v1/matches/{mid}/respond", headers=world["admin"], json={"accept": False}).json()["status"]
    with session_scope() as s:
        assert s.scalar(select(m.Match.id).where(m.Match.donation_id == d["id"])) is not None
    assert client.get(f"{BASE}/{d['id']}", headers=world["donor_a"]).status_code == 200
