"""STRIDE P2B-1 (Divulgação de informação) — mitigação PENDENTE, registrada como teste esperado-falhar.

Achado ao validar a Parte 1: a API entrega a QUALQUER perfil autenticado os scores internos da IA (ML_SCORE, BUSINESS_RULE_SCORE, DISTANCE_SCORE, FINAL_SCORE) e o ranking:
 * DOADOR recebe o ranking completo de ONGs (todos os scores, componentes, pesos, contagem de elegibilidade);
 * ONG recebe a própria candidatura com os 4 scores e a posição no ranking (`posicao`), além de `current_org`/`current_position` (quem está com a proposta).
Mitigação PLANEJADA (NÃO implementada nesta parte): Fase 3 Parte 1, seção 3 — esquemas de resposta por perfil aplicados NA API (não só na tela).

Estes testes descrevem o comportamento DESEJADO e hoje falham de propósito (xfail estrito). Quando a Fase 3 implementar a mitigação, eles passarão (XPASS)
e, por serem estritos, o CI falhará até que o marcador seja removido — o que sinaliza que o risco foi tratado.
"""
import pytest

from tests.helpers_p2 import org_token, ready_donation

SCORES = {"ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE"}
MOTIVO = "STRIDE P2B-1 PENDENTE: esquemas de resposta por perfil na API (Fase 3 Parte 1, seção 3)"


def _match(client, world):
    d = ready_donation(client, world)
    r = client.post("/api/v1/matches", headers=world["donor_a"], json={"donation_id": d["id"], "top_n": 5})
    assert r.status_code == 201, r.text
    return r.json()


def _contem_scores(obj) -> bool:
    if isinstance(obj, dict):
        return bool(SCORES & set(obj)) or any(_contem_scores(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contem_scores(v) for v in obj)
    return False


@pytest.mark.xfail(strict=True, reason=MOTIVO)
def test_doador_nao_recebe_scores_internos_nem_ranking_completo(client, world):
    mt = _match(client, world)
    assert not _contem_scores(mt), "o doador recebe scores internos da IA"
    assert "ranking" not in mt or len(mt["ranking"]) <= 1, "o doador recebe o ranking completo de ONGs"


@pytest.mark.xfail(strict=True, reason=MOTIVO)
def test_ong_nao_recebe_scores_internos_nem_posicao_no_ranking(client, world):
    mt = _match(client, world)
    tok = org_token(client, world["admin"], mt["ranking"][0]["org_id"])
    visto = client.get(f"/api/v1/matches/{mt['id']}", headers=tok).json()
    assert not _contem_scores(visto), "a ONG recebe os scores internos da IA"
    assert "posicao" not in (visto.get("my_candidacy") or {}), "a ONG descobre a própria classificação relativa às outras"
