import datetime as dt
from ml.semantic.validity import parse_validity
from ml.semantic.classifier import extract_quantity, RulesBaseline

REF = dt.date(2026, 10, 5)


def test_validade_em_dias():
    v = parse_validity("alface 20 caixas, vencem em 2 dias", REF, "HORT_FOLHOSAS")
    assert v["days_to_expiry"] == 2 and v["validity_source"] == "INFORMADA"


def test_validade_ausente_nao_inventa():
    v = parse_validity("vamos doar mandiocas, 32 cxs", REF, "HORT_RAIZES")
    assert v["validity_source"] != "INFORMADA" and v["days_to_expiry"] is None or v["validity_confidence"] < 0.7


def test_quantidade():
    q, u = extract_quantity("Couve manteiga, 80 maços")
    assert q == 80.0 and u is not None


def test_baseline_regras_incerto_pede_confirmacao():
    c, conf = RulesBaseline().predict_category("tomte 10 cx")
    assert conf <= 0.5
