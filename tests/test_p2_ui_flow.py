"""Fluxo consumido pela interface (ApiClient sobre a API) + smoke da UI Streamlit (AppTest). A UI só usa HTTP."""
import pytest

from app.api_client import ApiClient, ApiError
from tests.helpers_p2 import org_token

from pathlib import Path
ROOT_APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def _cli(client, headers):
    return ApiClient("http://testserver", headers["Authorization"].split(" ", 1)[1], http=client)


def test_fluxo_doador_e_ong_pelo_api_client(client, world):
    donor = _cli(client, world["donor_a"])
    me = donor.me()
    assert me["role"] == "DONOR" and me["data_origin_scope"] == "SIMULATED"
    info = donor.model_info()
    assert info["parser"]["training_data_origin"] == "SIMULATED"
    p = donor.parse(world["texts"]["ready"][2])
    assert p["training_data_origin"] == "SIMULATED" and p["threshold_note"] == "limiar calibrado sobre texto simulado"
    d = donor.create_donation({"texto": world["texts"]["ready"][2]})
    if d["status"] == "PENDING_CONFIRMATION":
        d = donor.confirm(d["id"], {"accept_fields": [k for k in d["pending_fields"] if k != "quantidade_kg"], **({"quantidade_kg": 10} if "quantidade_kg" in d["pending_fields"] else {})})
    if d["status"] != "READY":
        d = donor.create_donation({"categoria": "HORT_FRUTOS", "exige_refrigeracao": False, "dias_ate_validade": 4, "quantidade_kg": 15})
    assert d["status"] == "READY" and d["data_origin"] == "SIMULATED"
    mt = donor.create_match(d["id"], 5)
    assert mt["status"] == "PROPOSED" and mt["ranking"]
    cand = mt["ranking"][0]
    ong = _cli(client, org_token(client, world["admin"], cand["org_id"]))
    pend = ong.list_matches("PROPOSED")
    assert any(x["id"] == mt["id"] and x["awaiting_my_response"] for x in pend)
    assert ong.respond(mt["id"], True)["status"] == "ACCEPTED"          # "polling" da ONG enxerga o novo estado
    assert donor.get_match(mt["id"])["status"] == "ACCEPTED"              # "polling" do doador também
    assert ong.outcome(mt["id"], "COLLECTED")["status"] == "COLLECTED"
    tipos = [e["event_type"] for e in donor.events(mt["id"])["events"]]
    assert tipos[0] == "RANKED" and tipos[-1] == "COLLECTED"


def test_erros_da_api_chegam_como_apierror(client, world):
    bad = ApiClient("http://testserver", "rai_invalido_para_teste", http=client)
    with pytest.raises(ApiError) as e:
        bad.me()
    assert e.value.status == 401


def _run(monkeypatch, client, token=None):
    import httpx
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    at = AppTest.from_file(ROOT_APP, default_timeout=60)
    at.run()
    if token:
        at.sidebar.text_input[0].set_value(token)
        at.run()
    return at


def test_ui_sem_token_mostra_avisos(monkeypatch, client, world):
    at = _run(monkeypatch, client)
    assert not at.exception
    txt = " ".join(w.value for w in at.warning).lower()
    assert "dados simulados com limitações conhecidas" in txt
    caps = " ".join(c.value for c in at.caption).lower()
    assert "texto simulado" in caps and "tls" in caps


def test_ui_pagina_doador_e_ong(monkeypatch, client, world):
    tok = world["donor_a"]["Authorization"].split(" ", 1)[1]
    at = _run(monkeypatch, client, tok)
    assert not at.exception, [e.value for e in at.exception]
    assert any("SIMULADOS" in s.value or "simulad" in s.value.lower() for s in at.sidebar.caption)
    org = client.get("/api/v1/organizations?limit=1", headers=world["admin"]).json()[0]["id"]
    tok2 = org_token(client, world["admin"], org)["Authorization"].split(" ", 1)[1]
    at2 = _run(monkeypatch, client, tok2)
    assert not at2.exception, [e.value for e in at2.exception]
