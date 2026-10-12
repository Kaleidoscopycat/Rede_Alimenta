"""Fase 3 Parte 1 (Etapa B) — AJUSTE B0: a saída do parser (`fields`, confiança, versão, limiar) NÃO é do doador nem da ONG.

Esconder na tela não protege quem chama a API com o token do doador: a varredura abaixo é RECURSIVA sobre o JSON de TODAS as respostas acessíveis ao DONOR (GET e POST de doações e de itens,
fluxo novo e fluxo antigo) e ao ORG. O ADMIN continua recebendo `fields` (AdminDonationView)."""
import re

from api.schemas_views import AdminDonationView, DonorDonationView, OrgDonationView
from tests.helpers_p2 import new_ready_donation
from tests.test_p3a_rascunho_api import BASE, d_plus, fin, item
from tests.test_p3a_visibilidade_perfil import PROIBIDAS, cenario, chaves  # noqa: F401  (cenario é uma fixture)

# saída do parser / da IA que o DONOR e a ORG não recebem (varredura por NOME de chave, em qualquer nível)
SAIDA_PARSER = {"fields", "confidence", "confidence_threshold", "threshold_note", "parser_version", "parse_confidence", "threshold", "extracted", "extracted_confidence", "parser_suggestion",
                "training_data_origin", "manually_labeled_evaluation", "needs_human_confirmation", "weight_basis"}
CONF = re.compile(r"(^|_)conf(idence)?($|_)")  # categoria_conf, exige_refrigeracao_conf, confidence… (mas não `confirmed_at`)


def proibidas(obj) -> set[str]:
    ks = chaves(obj)
    return {k for k in ks if k in SAIDA_PARSER or k in PROIBIDAS or CONF.search(k)}


def test_regex_de_confianca_nao_pega_confirmed_at():
    assert CONF.search("categoria_conf") and CONF.search("confidence") and CONF.search("exige_refrigeracao_conf") and not CONF.search("confirmed_at") and not CONF.search("confirm_item")


def test_schemas_donor_e_org_nao_tem_fields_e_admin_tem():
    assert "fields" not in DonorDonationView.model_fields and "fields" not in OrgDonationView.model_fields and "fields" in AdminDonationView.model_fields
    assert DonorDonationView.model_fields.keys().isdisjoint({"parser_version", "parser_suggestion"})


def test_openapi_do_doador_nao_declara_fields(client):
    sch = client.get("/openapi.json").json()["components"]["schemas"]
    assert "fields" not in sch["DonorDonationView"]["properties"] and "fields" not in sch["OrgDonationView"]["properties"] and "fields" in sch["AdminDonationView"]["properties"]


def test_fluxo_novo_do_doador_nunca_devolve_fields_nem_saida_do_parser(client, world, clock):
    """Todas as respostas do fluxo de rascunho/itens (POST, PATCH, DELETE e GET), com itens manuais E sugeridos pelo texto."""
    h = world["donor_a"]
    resp = []

    def ok(r, codes=(200, 201)):
        assert r.status_code in codes, r.text
        j = r.json()
        resp.append(j)
        return j

    pv = ok(client.post(f"{BASE}/items/parse-preview", headers=h, json={"texto": world["texts"]["ready"][0]}))
    d = ok(client.post(f"{BASE}/drafts", headers=h, json={"texto": world["texts"]["ready"][1]}))
    d = ok(client.post(f"{BASE}/{d['id']}/items", headers=h, json=item(1, validade_data=d_plus(clock, 30))))
    d = ok(client.patch(f"{BASE}/{d['id']}/draft", headers=h, json={"contem_alergenico": True}))
    d = ok(client.post(f"{BASE}/{d['id']}/items/from-text", headers=h, json={"texto": world["texts"]["ready"][2]}))
    sug = next(i for i in d["items"] if i["entry_source"] == "TEXTO_SUGERIDO")
    d = ok(client.patch(f"{BASE}/{d['id']}/items/{sug['id']}", headers=h, json={"accept_fields": [], "quantity": 1}))
    ok(client.get(f"{BASE}/{d['id']}/items", headers=h))
    ok(client.get(f"{BASE}/{d['id']}", headers=h))
    ok(client.get(BASE, headers=h))
    d = ok(client.delete(f"{BASE}/{d['id']}/items/{sug['id']}", headers=h))
    d = fin(client, world, d["id"])
    resp.append(d)
    assert "fields" not in d and "pending_fields" in d
    for j in resp:
        assert not proibidas(j), proibidas(j)
    assert "fields" not in pv


def test_fluxo_antigo_do_doador_tambem_nao_devolve_fields(client, world):
    """POST /donations e PATCH /confirm (lote único) continuam no servidor, mas o doador recebe só `pending_fields` e os valores finais já confirmados."""
    d = new_ready_donation(client, world, "donor_a", "ready", 3)
    assert "fields" not in d and not proibidas(d)
    assert d["categoria"] and d["quantity_kg"] and d["validity_days"] is not None, "valores finais ficam no cabeçalho"
    if world["texts"]["pending"]:
        p = client.post("/api/v1/donations", headers=world["donor_a"], json={"texto": world["texts"]["pending"][0]}).json()
        assert "fields" not in p and not proibidas(p)
        if p["status"] == "PENDING_CONFIRMATION":
            assert p["pending_fields"] and all(isinstance(k, str) for k in p["pending_fields"])
            c = client.patch(f"/api/v1/donations/{p['id']}/confirm", headers=world["donor_a"], json={"accept_fields": [k for k in p["pending_fields"] if k != "quantidade_kg"], "quantidade_kg": 10})
            assert c.status_code == 200 and "fields" not in c.json() and not proibidas(c.json())
    g = client.get(f"/api/v1/donations/{d['id']}", headers=world["donor_a"]).json()
    assert "fields" not in g and not proibidas(g)
    assert client.post("/api/v1/donations/parse", headers=world["donor_a"], json={"texto": world["texts"]["ready"][0]}).status_code == 410, "análise crua do parser: descontinuada para DONOR"


def test_admin_continua_recebendo_fields_e_detalhe_do_parser(client, world):
    d = new_ready_donation(client, world, "donor_a", "ready", 4)
    a = client.get(f"/api/v1/donations/{d['id']}", headers=world["admin"]).json()
    assert a["perfil"] == "ADMIN" and a["fields"] and {"categoria", "quantidade_kg"} <= set(a["fields"]) and a["parser_version"]
    its = client.get(f"/api/v1/donations/{d['id']}/items", headers=world["admin"]).json()
    assert isinstance(its, list)


def test_ong_nao_recebe_fields_nem_saida_do_parser(client, world, cenario):  # noqa: F811
    _, mt, full, org = cenario
    v = client.get(f"/api/v1/matches/{mt['id']}", headers=org).json()
    assert not proibidas(v), proibidas(v)
    assert not proibidas(client.get("/api/v1/matches?status=PROPOSED", headers=org).json())
    assert "fields" not in v["donation"] and v["donation"]["analise"], "a ONG vê a análise em TEXTO (sem scores, sem confiança numérica)"
    assert not re.search(r"\b0[.,]\d{2,}\b.*(confian|score)", " ".join(v["donation"]["analise"]).lower())
