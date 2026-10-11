"""Contrato dos endpoints de rotas (Fase 2 Parte 2): POST /api/v1/routes/plan e GET /api/v1/routes/{id}.
Fixture TÉCNICA: o aceite da ONG é gravado direto no banco (o ciclo de aceite já é testado em test_p2_match); veículos e doações vêm do simulador (SIMULATED)."""
import uuid

import pytest
from sqlalchemy import func, select

from database import models as m
from database.session import session_scope
from tests.helpers_p2 import org_token
from tests.test_p2_match import new_lot

URL = "/api/v1/routes/plan"


@pytest.fixture(scope="module")
def alvo(client, world):
    """ONG real com localização, perfil e veículo SIMULADO cadastrado, na mesma região do doador A."""
    with session_scope() as s:
        dl = s.scalars(select(m.DonorLocation).where(m.DonorLocation.donor_id == world["donor_a_id"])).first()
        row = s.execute(select(m.Vehicle.organization_id, m.Vehicle.id).join(m.OrganizationLocation, m.OrganizationLocation.organization_id == m.Vehicle.organization_id)
                        .join(m.OrganizationProfile, m.OrganizationProfile.organization_id == m.Vehicle.organization_id)
                        .where(m.Vehicle.refrigerated.is_(True), m.Vehicle.capacity_kg >= 500, m.OrganizationLocation.lat.is_not(None))
                        .order_by(func.abs(m.OrganizationLocation.lat - dl.lat) + func.abs(m.OrganizationLocation.lon - dl.lon)).limit(1)).first()
        assert row, "esperava ao menos uma ONG com veículo refrigerado entre os veículos simulados"
        return {"org_id": row[0], "vehicle_id": row[1]}


def aceitar(client, world, org_id, **kw):
    d = new_lot(client, world, **kw)
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 15})
    assert r.status_code == 201, r.text
    mid = uuid.UUID(r.json()["id"])
    with session_scope() as s:  # fixture técnica: ONG alvo aceita
        mt = s.get(m.Match, mid)
        mt.status, mt.current_org_id = "ACCEPTED", org_id
    return d


def partida(clock):
    return clock().isoformat()


@pytest.fixture()
def org_headers(client, world, alvo):
    return org_token(client, world["admin"], str(alvo["org_id"]))


def test_plano_com_sucesso_persiste_solver_e_baseline(client, world, alvo, clock):
    d1, d2 = aceitar(client, world, alvo["org_id"], quantidade_kg=20), aceitar(client, world, alvo["org_id"], quantidade_kg=30)
    r = client.post(URL, headers=world["admin"], json={"donation_ids": [d1["id"], d2["id"]], "vehicle_id": str(alvo["vehicle_id"]), "departure_at": partida(clock)})
    assert r.status_code == 201, r.text
    j = r.json()
    p, b = j["primary"], j["baseline"]
    assert p["algorithm"].startswith("ORTOOLS") and b["algorithm"] == "NEAREST_NEIGHBOR"
    assert p["is_primary"] and not b["is_primary"] and p["plan_group_id"] == b["plan_group_id"] == j["plan_group_id"]
    assert p["data_origin"] == "SIMULATED" and p["rotulo"].startswith("SIMULAÇÃO") and p["dataset_version"]
    assert p["parameters"]["detour"] == 1.35 and p["parameters"]["algorithm_version"] == p["algorithm_version"]
    assert j["comparison"]["solver"]["lots_delivered"] >= j["comparison"]["baseline"]["lots_delivered"]
    types = [s["type"] for s in p["stops"]]
    if p["status"] == "PLANNED":
        assert types[0] == "DEPARTURE" and types[-1] == "DELIVERY" and types.count("PICKUP") == p["n_stops"]
        assert p["kg_collected"] == pytest.approx([x for x in p["stops"] if x["type"] == "PICKUP"][-1]["load_kg_after"])
        assert p["total_km_est"] is not None and p["total_minutes_est"] is not None
        for s in p["stops"]:
            assert s["data_origin"] == "SIMULATED"
    else:
        assert p["status"] == "INFEASIBLE" and p["unassigned"]
    g = client.get(f"/api/v1/routes/{p['id']}", headers=world["admin"])
    assert g.status_code == 200 and g.json()["id"] == p["id"] and len(g.json()["stops"]) == len(p["stops"])
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(m.Route).where(m.Route.plan_group_id == uuid.UUID(j["plan_group_id"]))) == 2
        assert s.scalar(select(func.count()).select_from(m.Route).where(m.Route.plan_group_id == uuid.UUID(j["plan_group_id"]), m.Route.data_origin == "USER_ENTERED")) == 0


def test_org_dona_do_aceite_planeja_com_veiculo_proprio(client, world, alvo, org_headers, clock):
    d = aceitar(client, world, alvo["org_id"], quantidade_kg=15)
    r = client.post(URL, headers=org_headers, json={"donation_ids": [d["id"]], "departure_at": partida(clock)})
    assert r.status_code == 201, r.text
    rid = r.json()["primary"]["id"]
    assert client.get(f"/api/v1/routes/{rid}", headers=org_headers).status_code == 200


def test_org_de_outra_ong_nao_acessa(client, world, alvo, clock):
    d = aceitar(client, world, alvo["org_id"], quantidade_kg=10)
    r = client.post(URL, headers=world["admin"], json={"donation_ids": [d["id"]], "vehicle_id": str(alvo["vehicle_id"]), "departure_at": partida(clock)})
    rid = r.json()["primary"]["id"]
    with session_scope() as s:
        outra = s.scalar(select(m.OrganizationLocation.organization_id).where(m.OrganizationLocation.organization_id != alvo["org_id"]).limit(1))
    intruso = org_token(client, world["admin"], str(outra))
    assert client.get(f"/api/v1/routes/{rid}", headers=intruso).status_code == 403
    assert client.post(URL, headers=intruso, json={"donation_ids": [d["id"]], "departure_at": partida(clock)}).status_code == 403


def test_autenticacao_e_perfis(client, world):
    corpo = {"donation_ids": [str(uuid.uuid4())]}
    assert client.post(URL, json=corpo).status_code == 401
    assert client.post(URL, headers=world["donor_a"], json=corpo).status_code == 403
    assert client.get(f"/api/v1/routes/{uuid.uuid4()}", headers=world["donor_a"]).status_code == 403
    assert client.get(f"/api/v1/routes/{uuid.uuid4()}", headers=world["admin"]).status_code == 404


def test_validacao_de_entrada(client, world):
    h = world["admin"]
    assert client.post(URL, headers=h, json={"donation_ids": []}).status_code == 422
    assert client.post(URL, headers=h, json={"donation_ids": ["nao-e-uuid"]}).status_code == 422
    assert client.post(URL, headers=h, json={"donation_ids": [str(uuid.uuid4())], "campo_extra": 1}).status_code == 422
    assert client.post(URL, headers=h, json={"donation_ids": [str(uuid.uuid4())], "safety_margin_h": -1}).status_code == 422
    assert client.post(URL, headers=h, json={"donation_ids": [str(uuid.uuid4())]}).status_code == 404


def test_doacao_sem_aceite_da_ong_retorna_409(client, world, alvo):
    d = new_lot(client, world)  # sem match aceito
    r = client.post(URL, headers=world["admin"], json={"donation_ids": [d["id"]], "vehicle_id": str(alvo["vehicle_id"])})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "DOACAO_SEM_ACEITE"


def test_lote_refrigerado_em_veiculo_comum_fica_de_fora_com_motivo(client, world, alvo, clock):
    with session_scope() as s:
        comum = s.scalars(select(m.Vehicle).where(m.Vehicle.organization_id == alvo["org_id"], m.Vehicle.refrigerated.is_(False))).first()
        if comum is None:
            comum = s.scalars(select(m.Vehicle).where(m.Vehicle.refrigerated.is_(False), m.Vehicle.capacity_kg >= 100)).first()
        vid = comum.id
    d = aceitar(client, world, alvo["org_id"], quantidade_kg=10, exige_refrigeracao=True)
    r = client.post(URL, headers=world["admin"], json={"donation_ids": [d["id"]], "vehicle_id": str(vid), "departure_at": partida(clock)})
    assert r.status_code == 201, r.text
    p = r.json()["primary"]
    assert p["status"] == "INFEASIBLE" and p["n_stops"] == 0
    assert p["unassigned"][0]["reason"] == "REFRIGERACAO_INCOMPATIVEL"


def test_prazo_de_validade_com_margem_excessiva_deixa_lote_fora(client, world, alvo, clock):
    d = aceitar(client, world, alvo["org_id"], quantidade_kg=10, dias_ate_validade=1)
    r = client.post(URL, headers=world["admin"], json={"donation_ids": [d["id"]], "vehicle_id": str(alvo["vehicle_id"]), "departure_at": partida(clock), "safety_margin_h": 48})
    assert r.status_code == 201, r.text
    p = r.json()["primary"]
    assert p["status"] == "INFEASIBLE" and p["unassigned"][0]["reason"] in ("PRAZO_INVIAVEL", "JANELA_INALCANCAVEL", "JANELA_INSUFICIENTE", "FORA_DO_HORIZONTE")
    assert p["parameters"]["safety_margin_h"] == 48


def test_rota_registra_auditoria(client, world, alvo, clock):
    d = aceitar(client, world, alvo["org_id"], quantidade_kg=12)
    client.post(URL, headers=world["admin"], json={"donation_ids": [d["id"]], "vehicle_id": str(alvo["vehicle_id"]), "departure_at": partida(clock)})
    with session_scope() as s:
        n = s.scalar(select(func.count()).select_from(m.AuditLog).where(m.AuditLog.action == "route.plan"))
    assert n >= 1
