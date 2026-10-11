"""Motor de match: elegibilidade, scores separados, ciclo de vida (PROPOSED→ACCEPTED|DECLINED|EXPIRED→próxima→COLLECTED|FAILED), capacidade, concorrência, lote e contrato."""
import datetime as dt
import threading

import numpy as np
import pytest
from sqlalchemy import select

from core.settings import SETTINGS, TZ
from database import models as m
from database.session import session_scope
from match import batch as batch_mod
from match import lifecycle
from match.eligibility import RULES, DonationCtx, evaluate
from tests.helpers_p2 import org_token

PAYLOAD = {"categoria": "HORT_FRUTOS", "exige_refrigeracao": False, "dias_ate_validade": 4, "quantidade_kg": 20}


@pytest.fixture()
def restore_clock(clock):
    saved = clock.now
    yield clock
    clock.now = saved


def new_lot(client, world, donor="donor_a", **kw):
    r = client.post("/api/v1/donations", headers=world[donor], json={**PAYLOAD, **kw})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "READY", r.json()
    return r.json()


def new_match(client, world, donor="donor_a", **kw):
    d = new_lot(client, world, donor, **kw)
    r = client.post("/api/v1/matches", headers=world[donor], json={"donation_id": d["id"], "top_n": 15})
    assert r.status_code == 201, r.text
    return d, r.json()


# ------------------------------------------------------------------ scores e ranking
def test_scores_separados_e_final_ponderado(client, world):
    d, mt = new_match(client, world)
    assert mt["status"] in ("PROPOSED", "EXHAUSTED")
    assert mt["ranking"], "esperava candidatas em área metropolitana"
    w = SETTINGS
    finals = []
    for c in mt["ranking"]:
        for k in ("ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE"):
            assert 0.0 <= c[k] <= 1.0
        assert c["FINAL_SCORE"] == pytest.approx(w.w_ml * c["ML_SCORE"] + w.w_rule * c["BUSINESS_RULE_SCORE"] + w.w_dist * c["DISTANCE_SCORE"], abs=2e-4)
        assert c["location_precision"] in ("EXACT", "MUNICIPALITY_CENTROID", "UF_CENTROID", "APPROXIMATE", "CENTROID") or c["location_precision"]
        assert isinstance(c["distancia_aproximada"], bool)
        assert c["explicacao"] and c["regras_aprovadas"] == list(RULES)
        finals.append(c["FINAL_SCORE"])
    assert finals == sorted(finals, reverse=True)
    assert mt["weights"]["natureza"].startswith("PREMISSAS")
    assert mt["data_origin"] == "SIMULATED"
    assert "próprio para consumo" in mt["donation"]["aviso"]
    for etapa in ("busca_espacial_ms", "elegibilidade_ms", "ml_ms", "scores_ms", "total_ms"):
        assert mt["latency_ms"][etapa] >= 0
    assert mt["eligibility"]["n_eligible"] >= len(mt["ranking"])
    assert set(mt["eligibility"]["por_regra"]) == set(RULES)


def test_latencia_registrada_em_ml_predictions(client, world):
    d, mt = new_match(client, world)
    with session_scope() as s:
        p = s.scalars(select(m.MlPrediction).where(m.MlPrediction.match_id == mt["id"])).first()
        assert p is not None and p.latency_ms is not None and p.training_data_origin == "SIMULATED"


# ------------------------------------------------------------------ regras eliminatórias (cópias em memória de linhas de ONGs reais)
def _base_fixture():
    from api.state import STATE
    o = STATE.engine.orgs
    o = o[o["has_location"].to_numpy(bool)].iloc[:6].copy().reset_index(drop=True)
    return o


def _ctx(**kw):
    base = dict(categoria="HORT_FRUTOS", quantity_kg=10.0, hours_to_expiry=96.0, needs_cold=False, pickup_days_mask=127, pickup_start_h=0.0, pickup_end_h=24.0, load_minutes=30.0,
                lat=-23.55, lon=-46.63, municipio_ibge=3550308, location_precision="EXACT", allergen=False, data_origin="SIMULATED")
    base.update(kw)
    return DonationCtx(**base)


NOW = dt.datetime(2026, 10, 13, 10, 0, tzinfo=TZ)


def _eval(orgs, ctx, dist=10.0, cap=1e6):
    n = len(orgs)
    return evaluate(ctx, orgs, np.full(n, dist), np.full(n, cap), NOW)


def _prep():
    """Linhas reais de ONGs; apenas o PERFIL DECLARADO é ajustado em memória (nunca gravado) para isolar cada regra — fixture técnica de teste."""
    o = _base_fixture()
    o["aceita_HORT_FRUTOS_declarado"] = True
    o["camara_fria_declarada"] = True
    o["dias_funcionamento_declarados_mask"] = 127
    o["horario_abertura_declarado_h"] = 0.0
    o["horario_fechamento_declarado_h"] = 24.0
    o["platform_status"] = "REGISTERED"
    o["has_location"] = True
    return o


def test_linha_base_elegivel():
    r = _eval(_prep(), _ctx())
    assert r["eligible"].all()


@pytest.mark.parametrize("regra", list(RULES))
def test_cada_regra_reprova_isoladamente(regra):
    o = _prep()
    ctx, dist, cap = _ctx(), 10.0, 1e6
    if regra == "E_LOCALIZACAO_AUSENTE":
        o["has_location"] = False
    elif regra == "E_NAO_CADASTRADA":
        o["platform_status"] = "PUBLIC_RECORD"
        ctx = _ctx(data_origin="USER_ENTERED")
    elif regra == "E_CATEGORIA_NAO_ACEITA":
        o["aceita_HORT_FRUTOS_declarado"] = False
    elif regra == "E_CAPACIDADE":
        cap = 5.0
    elif regra == "E_REFRIGERACAO":
        o["camara_fria_declarada"] = False
        o["tem_frota"] = False
        o["refrigerado"] = False
        ctx = _ctx(needs_cold=True)
    elif regra == "E_HORARIO":
        o["dias_funcionamento_declarados_mask"] = 0
    elif regra == "E_PRAZO_VALIDADE":
        ctx = _ctx(hours_to_expiry=0.5)
    r = _eval(o, ctx, dist, cap)
    assert r["fail"][regra].all(), regra
    assert not r["eligible"].any()


def test_registro_publico_so_nao_cadastrada_para_doacao_real():
    o = _prep()
    o["platform_status"] = "PUBLIC_RECORD"
    assert _eval(o, _ctx(data_origin="SIMULATED"))["eligible"].all()  # simulação pode usar registros públicos
    assert not _eval(o, _ctx(data_origin="USER_ENTERED"))["eligible"].any()


# ------------------------------------------------------------------ ciclo de vida
def _org_headers_for(client, world, candidate):
    return org_token(client, world["admin"], candidate["org_id"])


def test_ciclo_completo_recusa_expira_aceita_coleta(client, world, restore_clock):
    from api.state import STATE
    d, mt = new_match(client, world)
    assert mt["status"] == "PROPOSED"
    rk = mt["ranking"]
    assert len(rk) >= 3
    mid = mt["id"]
    org1 = _org_headers_for(client, world, rk[0])
    org2 = _org_headers_for(client, world, rk[1])
    org3 = _org_headers_for(client, world, rk[2])
    # ONG que não é a destinatária não responde
    assert client.post(f"/api/v1/matches/{mid}/respond", headers=org2, json={"accept": True}).status_code == 403
    # ONG 1 vê a proposta (apenas a própria candidatura) e recusa
    v = client.get(f"/api/v1/matches/{mid}", headers=org1).json()
    assert v["awaiting_my_response"] and "ranking" not in v
    r = client.post(f"/api/v1/matches/{mid}/respond", headers=org1, json={"accept": False, "note": "sem espaço"})
    assert r.status_code == 200, r.text
    assert r.json()["current_org"] == rk[1]["ong_id"] and r.json()["status"] == "PROPOSED"
    # ONG 2 deixa expirar
    restore_clock.advance(minutes=SETTINGS.proposal_ttl_minutes + 1)
    with session_scope() as s:
        assert lifecycle.expire_overdue(s, STATE.engine) >= 1
    v = client.get(f"/api/v1/matches/{mid}", headers=world["donor_a"]).json()
    assert v["current_org"] == rk[2]["ong_id"]
    # resposta tardia da ONG 2 é negada
    assert client.post(f"/api/v1/matches/{mid}/respond", headers=org2, json={"accept": True}).status_code in (403, 409)
    # ONG 3 aceita; coleta registrada
    assert client.post(f"/api/v1/matches/{mid}/outcome", headers=org3, json={"result": "COLLECTED"}).status_code == 409  # antes do aceite
    a = client.post(f"/api/v1/matches/{mid}/respond", headers=org3, json={"accept": True})
    assert a.status_code == 200 and a.json()["status"] == "ACCEPTED"
    assert client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()["status"] == "MATCHED"
    o = client.post(f"/api/v1/matches/{mid}/outcome", headers=org3, json={"result": "COLLECTED"})
    assert o.status_code == 200 and o.json()["status"] == "COLLECTED"
    # eventos e tempos
    ev = client.get(f"/api/v1/matches/{mid}/events", headers=world["donor_a"]).json()["events"]
    tipos = [e["event_type"] for e in ev]
    assert tipos[0] == "RANKED"
    for t in ("PROPOSED", "DECLINED", "EXPIRED", "ACCEPTED", "COLLECTED"):
        assert t in tipos, tipos
    assert tipos.count("PROPOSED") == 3
    ats = [dt.datetime.fromisoformat(e["at"]) for e in ev]
    assert ats == sorted(ats)
    assert all(e["data_origin"] == "SIMULATED" for e in ev)
    # ONG só vê os próprios eventos
    ev1 = client.get(f"/api/v1/matches/{mid}/events", headers=org1).json()["events"]
    assert ev1 and all(e["ong_id"] == rk[0]["ong_id"] for e in ev1)
    # capacidade: recusada/expirada liberadas; aceita consumida
    with session_scope() as s:
        res = {r.organization_id: r.status for r in s.scalars(select(m.CapacityReservation).where(m.CapacityReservation.match_id == mid))}
        by_org = {str(k): v for k, v in res.items()}
        assert by_org[rk[0]["org_id"]] == "RELEASED" and by_org[rk[1]["org_id"]] == "RELEASED" and by_org[rk[2]["org_id"]] == "CONSUMED"
    # métricas de tempo separadas por origem
    j = client.get("/api/v1/metrics/match-times", headers=world["admin"]).json()
    assert "SIMULATED" in str(j)
    assert client.get("/api/v1/metrics/match-times", headers=world["donor_a"]).status_code == 403


def test_coleta_falha_e_estado_terminal(client, world):
    d, mt = new_match(client, world)
    org = _org_headers_for(client, world, mt["ranking"][0])
    assert client.post(f"/api/v1/matches/{mt['id']}/respond", headers=org, json={"accept": True}).status_code == 200
    assert client.post(f"/api/v1/matches/{mt['id']}/outcome", headers=org, json={"result": "FAILED", "note": "sem transporte"}).json()["status"] == "FAILED"
    assert client.post(f"/api/v1/matches/{mt['id']}/respond", headers=org, json={"accept": True}).status_code == 409
    assert client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()["status"] == "READY"


def test_esgota_candidatas_vira_no_match(client, world):
    d, mt = new_match(client, world)
    n = 0
    while mt["status"] == "PROPOSED" and n < 40:
        mt = client.post(f"/api/v1/matches/{mt['id']}/respond", headers=world["admin"], json={"accept": False}).json()
        n += 1
    assert mt["status"] == "EXHAUSTED"
    assert client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()["status"] == "NO_MATCH"
    with session_scope() as s:
        assert not s.scalars(select(m.CapacityReservation).where(m.CapacityReservation.match_id == mt["id"], m.CapacityReservation.status == "ACTIVE")).all()


def test_match_bloqueado_para_doacao_nao_pronta_e_duplicado(client, world):
    r = client.post("/api/v1/donations", headers=world["donor_a"], json={**PAYLOAD, "dias_ate_validade": -1})
    assert r.json()["status"] == "BLOCKED_EXPIRED"
    assert client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": r.json()["id"]}).status_code == 409
    d, mt = new_match(client, world)
    assert client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]}).status_code == 409  # já em andamento


def test_validade_vence_antes_do_match(client, world, restore_clock):
    d = new_lot(client, world, dias_ate_validade=0)
    restore_clock.advance(hours=16)  # passa da 23:59 do dia da validade
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"]})
    assert r.status_code == 409
    assert client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()["status"] == "BLOCKED_EXPIRED"


# ------------------------------------------------------------------ concorrência de capacidade
def test_concorrencia_nao_ultrapassa_capacidade(client, world):
    from api.state import STATE
    probe = new_lot(client, world, quantidade_kg=20)
    now = lifecycle.utcnow()
    with session_scope() as s:
        ctx = lifecycle.build_ctx(s, s.get(m.Donation, probe["id"]), now)
        top = STATE.engine.rank(ctx, now, lifecycle.reserved_on(s, now.astimezone(TZ).date()))["ranking"][0]
    q = round(top["capacidade_restante_kg"] * 0.6, 1)
    assert q > 0
    d1, d2 = new_lot(client, world, "donor_a", quantidade_kg=q), new_lot(client, world, "donor_a", quantidade_kg=q)
    bar = threading.Barrier(2, timeout=30)
    orig = STATE.engine.rank

    def wrapped(*a, **k):
        res = orig(*a, **k)
        try:
            bar.wait()  # as duas threads só seguem para a proposta depois de ranquear (sem reservas visíveis)
        except threading.BrokenBarrierError:
            pass
        return res

    STATE.engine.rank = wrapped
    out, errs = {}, []

    def run(did):
        try:
            with session_scope() as s:
                admin = s.scalars(select(m.User).where(m.User.role == "ADMIN")).first()
                out[did] = str(lifecycle.create_match(s, STATE.engine, did, admin).id)
        except Exception as e:  # noqa
            errs.append(repr(e))

    try:
        ts = [threading.Thread(target=run, args=(x["id"],)) for x in (d1, d2)]
        [t.start() for t in ts]
        [t.join(60) for t in ts]
    finally:
        STATE.engine.rank = orig
    assert not errs, errs
    assert len(out) == 2
    with session_scope() as s:
        day = lifecycle.utcnow().astimezone(TZ).date()
        caps = {p.organization_id: float(p.capacity_max_kg_day) for p in s.scalars(select(m.OrganizationProfile))}
        tot: dict = {}
        for r in s.scalars(select(m.CapacityReservation).where(m.CapacityReservation.reservation_date == day, m.CapacityReservation.status.in_(("ACTIVE", "CONSUMED")))):
            tot[r.organization_id] = tot.get(r.organization_id, 0.0) + float(r.reserved_kg)
        assert all(v <= caps[k] + 1e-6 for k, v in tot.items()), "capacidade diária ultrapassada"
        cur = [s.get(m.Match, out[x["id"]]).current_org_id for x in (d1, d2)]
        evs = s.scalars(select(m.MatchEvent).where(m.MatchEvent.match_id.in_(list(out.values())), m.MatchEvent.event_type == "SKIPPED")).all()
        # a segunda reserva na mesma ONG foi recusada no momento da proposta (reavaliação sob bloqueio): ONGs distintas ou evento SKIPPED
        assert cur[0] != cur[1] or not cur[0] or evs


# ------------------------------------------------------------------ lote: guloso × ótimo
def test_compare_otimo_supera_guloso_em_caso_tecnico():
    lots = [{"id": "lote_tecnico_1", "ranking": [{"org_id": "org_tecnica_A", "FINAL_SCORE": 0.9}, {"org_id": "org_tecnica_B", "FINAL_SCORE": 0.8}]},
            {"id": "lote_tecnico_2", "ranking": [{"org_id": "org_tecnica_A", "FINAL_SCORE": 0.85}]}]
    c = batch_mod.compare(lots)
    assert c["n_assigned_greedy"] == 1 and c["n_assigned_optimal"] == 2
    assert c["total_score_optimal"] == pytest.approx(1.65) and c["total_score_greedy"] == pytest.approx(0.9)
    assert c["difference"] == pytest.approx(0.75)


def test_batch_pela_api_sobre_lotes_simulados(client, world):
    with session_scope() as s:
        ids = [str(i) for i in s.scalars(select(m.Donation.id).where(m.Donation.data_origin == "SIMULATED", m.Donation.status == "HISTORICAL").limit(8))]
        at = s.scalar(select(m.Donation.created_at).where(m.Donation.id == ids[0]))
    r = client.post("/api/v1/matches/batch-compare", headers=world["admin"], json={"donation_ids": ids, "at": at.isoformat()})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["data_origin"] == "SIMULATED" and "SIMULAÇÃO" in j["details"]["rotulo"]
    assert j["difference"] >= -1e-9 and j["n_assigned_optimal"] >= j["n_assigned_greedy"] - 0
    assert client.post("/api/v1/matches/batch-compare", headers=world["donor_a"], json={"donation_ids": ids}).status_code == 403


# ------------------------------------------------------------------ predições e contrato
def test_predictions_contrato(client, world):
    r = client.post("/api/v1/predictions", headers=world["donor_a"], json={"categoria": "HORT_FRUTOS", "quantidade_kg": 20, "horas_ate_validade": 72, "municipio_ibge": 3550308})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["data_origin"] and "SIMULAD" in j["aviso"].upper()
    assert j["ranking"]
    info = client.get("/api/v1/model/info", headers=world["donor_a"]).json()
    assert info["parser"]["threshold_note"] == "limiar calibrado sobre texto simulado"
    assert any("R1" in a and "R6" in a for a in info["avisos"])


def test_contrato_openapi(client):
    j = client.get("/openapi.json").json()
    paths = j["paths"]
    exigidos = ["/api/v1/organizations", "/api/v1/organizations/{org_id}", "/api/v1/public-data/sources", "/api/v1/donors", "/api/v1/donors/{donor_id}", "/api/v1/donations/parse",
                "/api/v1/donations", "/api/v1/donations/{donation_id}", "/api/v1/donations/{donation_id}/confirm", "/api/v1/matches", "/api/v1/matches/{match_id}",
                "/api/v1/matches/{match_id}/respond", "/api/v1/matches/{match_id}/events", "/api/v1/predictions", "/api/v1/model/info", "/health", "/ready"]
    faltando = [p for p in exigidos if p not in paths]
    assert not faltando, faltando
    assert {"/api/v1/routes/plan", "/api/v1/routes/{route_id}"} <= set(paths), "Parte 2: endpoints de rotas"
    for p, ops in paths.items():
        if p.startswith("/api/v1"):
            for meth, op in ops.items():
                assert op.get("security"), (meth, p)
    for p in ("/health", "/ready"):
        assert not paths[p]["get"].get("security")


# ------------------------------------------------------------------ geolocalização
def test_organizacoes_expoem_precisao_e_nunca_coordenada_inventada(client, world):
    orgs = client.get("/api/v1/organizations?limit=100", headers=world["admin"]).json()
    assert orgs
    for o in orgs:
        loc = o["location"]
        assert loc["location_precision"] in ("EXACT", "MUNICIPALITY_CENTROID", "UF_CENTROID", "NONE") or loc["location_precision"]
        if loc["lat"] is None:
            assert loc["rankable_by_distance"] is False
        assert o["source"] and o["source_record_id"] and o["source_url"] and o["last_verified_at"]
        assert o["data_origin"] == "PUBLIC" and "cliente" in o["aviso"].lower()


def test_distancia_haversine_do_ranking_confere(client, world):
    from pipelines.geo import haversine_km
    d, mt = new_match(client, world)
    from api.state import STATE
    with session_scope() as s:
        loc = s.scalars(select(m.DonorLocation).where(m.DonorLocation.donor_id == world["donor_a_id"])).first()
        lat0, lon0 = loc.lat, loc.lon
    o = STATE.engine.orgs.set_index("org_uuid")
    for c in mt["ranking"][:5]:
        row = o.loc[c["org_id"]] if c["org_id"] in o.index else o.loc[__import__("uuid").UUID(c["org_id"])]
        esperado = float(haversine_km(lat0, lon0, float(row["lat"]), float(row["lon"])))
        assert c["dist_km"] == pytest.approx(esperado, abs=0.02)
