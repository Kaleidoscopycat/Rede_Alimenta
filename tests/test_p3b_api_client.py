"""Etapa B — ApiClient: novos métodos (rascunho, itens, ranking, organizações) e mensagens de erro em linguagem simples. Sem rede: httpx.MockTransport (nenhum dado de negócio)."""
import json

import httpx
import pytest

from app.api_client import ApiClient, ApiError

CALLS: list[tuple[str, str, dict | None, dict]] = []


def _cli(status=200, payload=None):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        CALLS.append((req.method, req.url.path, body, dict(req.url.params)))
        assert req.headers["authorization"] == "Bearer rai_token_somente_de_teste"
        return httpx.Response(status, json=payload if payload is not None else {"ok": True})
    return ApiClient("http://api", "rai_token_somente_de_teste", http=httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("chamada,esperado", [
    (lambda c: c.create_draft(), ("POST", "/api/v1/donations/drafts", {}, {})),
    (lambda c: c.create_draft({"contem_alergenico": True}), ("POST", "/api/v1/donations/drafts", {"contem_alergenico": True}, {})),
    (lambda c: c.patch_draft("D1", {"dias_retirada": [1, 2]}), ("PATCH", "/api/v1/donations/D1/draft", {"dias_retirada": [1, 2]}, {})),
    (lambda c: c.add_item("D1", {"produto": "x"}), ("POST", "/api/v1/donations/D1/items", {"produto": "x"}, {})),
    (lambda c: c.patch_item("D1", 7, {"confirm_item": True}), ("PATCH", "/api/v1/donations/D1/items/7", {"confirm_item": True}, {})),
    (lambda c: c.delete_item("D1", 7), ("DELETE", "/api/v1/donations/D1/items/7", None, {})),
    (lambda c: c.list_items("D1"), ("GET", "/api/v1/donations/D1/items", None, {})),
    (lambda c: c.parse_preview("duas linhas"), ("POST", "/api/v1/donations/items/parse-preview", {"texto": "duas linhas"}, {})),
    (lambda c: c.items_from_text("D1", "texto"), ("POST", "/api/v1/donations/D1/items/from-text", {"texto": "texto"}, {})),
    (lambda c: c.finalize("D1"), ("POST", "/api/v1/donations/D1/finalize", None, {})),
    (lambda c: c.list_donations(5, 10, "READY"), ("GET", "/api/v1/donations", None, {"limit": "5", "offset": "10", "status": "READY"})),
    (lambda c: c.ranking("M1"), ("GET", "/api/v1/matches/M1/ranking", None, {})),
    (lambda c: c.list_organizations("SP", 3), ("GET", "/api/v1/organizations", None, {"uf": "SP", "limit": "3", "offset": "0"})),
    (lambda c: c.get_organization("O1"), ("GET", "/api/v1/organizations/O1", None, {})),
    (lambda c: c.list_matches("PROPOSED"), ("GET", "/api/v1/matches", None, {"limit": "20", "offset": "0", "status": "PROPOSED"})),
])
def test_metodos_chamam_o_endpoint_certo(chamada, esperado):
    CALLS.clear()
    chamada(_cli())
    assert CALLS[-1] == esperado


def test_erro_422_vira_mensagem_em_portugues():
    detail = [{"loc": ["body", "unit_weight"], "msg": "Input should be greater than 0", "type": "greater_than"}, {"loc": ["body", "validade_data"], "msg": "valor inválido"}]
    with pytest.raises(ApiError) as e:
        _cli(422, {"detail": detail}).add_item("D1", {})
    assert e.value.status == 422
    f = e.value.friendly
    assert f.startswith("Confira os dados informados") and "peso ou volume por unidade" in f and "validade" in f and "body" not in f and "{" not in f


@pytest.mark.parametrize("status,detail,trecho", [
    (401, "Not Found", "código de acesso"), (403, "Forbidden", "não tem permissão"), (404, "Not Found", "Não encontramos"), (410, "gone", "gone"),
    (409, "doação em estado MATCHING: itens não podem mais ser alterados", "não podem mais ser alterados"), (500, "Traceback (most recent call last)", "Tente novamente"),
])
def test_mensagens_amigaveis_sem_traceback(status, detail, trecho):
    with pytest.raises(ApiError) as e:
        _cli(status, {"detail": detail}).me()
    assert trecho in e.value.friendly and "Traceback" not in e.value.friendly
