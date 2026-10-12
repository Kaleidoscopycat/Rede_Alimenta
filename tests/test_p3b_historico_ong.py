"""Etapa B — correção de integração: o histórico da ONG inclui as propostas que ela recebeu e que já passaram à próxima candidata (recusadas/sem resposta), sem expor nada de outras ONGs."""
from tests.helpers_p2 import org_token
from tests.test_p3a_visibilidade_perfil import PROIBIDAS, cenario, chaves  # noqa: F401  (cenario é uma fixture)


def _meu(client, hdr, mid, status=None):
    rota = "/api/v1/matches" + (f"?status={status}" if status else "")
    return next((x for x in client.get(rota, headers=hdr).json() if x["id"] == mid), None)


def test_historico_da_ong_inclui_recusada_e_nao_confunde_com_aceite_de_outra(client, world, cenario):  # noqa: F811
    _, mt, full, org1 = cenario
    mid = mt["id"]
    assert len(full["ranking"]) >= 2
    atual = _meu(client, org1, mid, "PROPOSED")
    assert atual and atual["awaiting_my_response"] and atual["mine_now"] and atual["my_last_event"] == "PROPOSED"
    assert client.post(f"/api/v1/matches/{mid}/respond", headers=org1, json={"accept": False, "note": "sem espaço (teste)"}).status_code == 200
    h = _meu(client, org1, mid)
    assert h is not None, "a recusa deve continuar no histórico da ONG"
    assert h["awaiting_my_response"] is False and h["mine_now"] is False and h["my_last_event"] == "DECLINED" and h["my_last_event_at"]
    assert not (chaves(h) & PROIBIDAS)
    org2 = org_token(client, world["admin"], full["ranking"][1]["org_id"])
    assert client.post(f"/api/v1/matches/{mid}/respond", headers=org2, json={"accept": True}).status_code == 200
    h1, h2 = _meu(client, org1, mid), _meu(client, org2, mid)
    assert h1["mine_now"] is False and h1["my_last_event"] == "DECLINED"  # o aceite foi de OUTRA ONG: não aparece como minha coleta
    assert h2["mine_now"] is True and h2["my_last_event"] == "ACCEPTED"
    assert client.post(f"/api/v1/matches/{mid}/outcome", headers=org1, json={"result": "COLLECTED"}).status_code == 403
    assert client.post(f"/api/v1/matches/{mid}/outcome", headers=org2, json={"result": "COLLECTED"}).status_code == 200
    assert _meu(client, org2, mid)["my_last_event"] == "COLLECTED"
