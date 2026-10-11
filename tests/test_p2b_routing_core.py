"""Roteirização (núcleo, sem banco): restrições, verificador independente, baseline × solver, ótimo por força bruta e coerência das premissas com a Parte 1.
Coordenadas: centroides de municípios REAIS da Grande São Paulo (IBGE) usados só como geometria de teste; não há doadores/lotes de negócio aqui."""
import itertools

import pytest

from routing import core
from routing.core import Assumptions, Problem, Stop

A = Assumptions(detour=1.35, speed_short_kmh=22.0, speed_long_kmh=55.0, short_threshold_km=15.0, unload_min=30)
# centroides aproximados (graus): São Paulo, Osasco, Guarulhos, Santo André, São Bernardo, Barueri
SP, OSASCO, GRU, SANTO_ANDRE, SBC, BARUERI = (-23.55, -46.63), (-23.53, -46.79), (-23.46, -46.53), (-23.66, -46.53), (-23.69, -46.56), (-23.51, -46.88)


def stop(key, pos, kg=100.0, ws=0, we=600, deadline=700, cold=False, svc=15):
    return Stop(key=key, lat=pos[0], lon=pos[1], kg=kg, service_min=svc, win_start=ws, win_end=we, deadline=deadline, cold=cold)


def problem(stops, cap=1000.0, org_cap=1000.0, refrigerated=False, depot=OSASCO, dest=SP, dest_open=0, dest_close=720, horizon=720):
    return Problem(depot=depot, dest=dest, dest_open=dest_open, dest_close=dest_close, vehicle_cap_kg=cap, org_cap_kg=org_cap, refrigerated=refrigerated, stops=tuple(stops),
                   assumptions=A, horizon_min=horizon)


def test_premissas_iguais_as_da_parte_1():
    """A metodologia de tempo/distância é a MESMA da geolocalização da Parte 1 (api/service.py)."""
    from api import service
    from core.settings import ROUTE
    assert (ROUTE.detour, ROUTE.speed_short_kmh, ROUTE.speed_long_kmh, ROUTE.unload_min) == (service.DETOUR, service.SPEED_SHORT, service.SPEED_LONG, service.SERVICE_MIN)
    assert ROUTE.short_threshold_km == 15.0


def test_matriz_usa_haversine_x_desvio_e_velocidade_por_faixa():
    p = problem([stop("a", GRU)])
    m = core.build_matrices(p)
    from pipelines.geo import haversine_km
    straight = float(haversine_km(OSASCO[0], OSASCO[1], GRU[0], GRU[1]))
    assert m.km[0][1] == pytest.approx(straight * 1.35, rel=1e-3)
    speed = 22.0 if straight <= 15.0 else 55.0
    assert 0 <= m.minutes[0][1] - m.km[0][1] / speed * 60 < 1.0  # minutos arredondados para cima


def test_verificador_aponta_cada_restricao():
    base = [stop("a", GRU, kg=600), stop("b", SANTO_ANDRE, kg=600)]
    assert "CAPACIDADE_VEICULO" in core.evaluate(problem(base, cap=1000), [0, 1]).violations
    assert "CAPACIDADE_ONG" in core.evaluate(problem(base, org_cap=1000), [0, 1]).violations
    assert "REFRIGERACAO:a" in core.evaluate(problem([stop("a", GRU, cold=True)], refrigerated=False), [0]).violations
    assert core.evaluate(problem([stop("a", GRU, cold=True)], refrigerated=True), [0]).feasible
    assert any(v.startswith("JANELA_DOADOR") for v in core.evaluate(problem([stop("a", GRU, ws=0, we=20)]), [0]).violations)
    assert any(v.startswith("PRAZO_VALIDADE") for v in core.evaluate(problem([stop("a", GRU, deadline=60)]), [0]).violations)
    assert "JANELA_ONG" in core.evaluate(problem([stop("a", GRU)], dest_close=30), [0]).violations
    assert "HORIZONTE" in core.evaluate(problem([stop("a", GRU)], horizon=30, dest_close=900), [0]).violations


def test_rotas_planejadas_sempre_passam_no_verificador():
    stops = [stop("a", GRU, kg=300), stop("b", SANTO_ANDRE, kg=300), stop("c", SBC, kg=300), stop("d", BARUERI, kg=300)]
    p = problem(stops, cap=1000)
    out = core.plan(p, 2)
    for r in (out["baseline"], out["solver"]):
        assert core.evaluate(p, r.order, out["matrices"]).feasible
        assert sum(p.stops[j].kg for j in r.order) <= 1000
    assert len(out["solver"].order) >= len(out["baseline"].order)


def test_triagem_explica_cada_lote_fora():
    stops = [stop("frio", GRU, cold=True), stop("pesado", GRU, kg=5000), stop("janela", GRU, ws=0, we=5), stop("prazo", GRU, deadline=10), stop("ok", GRU)]
    p = problem(stops)
    m = core.build_matrices(p)
    ok, rej = core.screen(p, m)
    assert ok == [4]
    assert rej[0] == "REFRIGERACAO_INCOMPATIVEL" and rej[1] == "EXCEDE_CAPACIDADE_VEICULO" and rej[2] == "JANELA_INSUFICIENTE" and rej[3] == "PRAZO_INVIAVEL"
    out = core.plan(p, 1)
    got = {u["key"]: u["reason"] for u in out["solver"].unassigned}
    assert got == {"frio": "REFRIGERACAO_INCOMPATIVEL", "pesado": "EXCEDE_CAPACIDADE_VEICULO", "janela": "JANELA_INSUFICIENTE", "prazo": "PRAZO_INVIAVEL"}


def test_capacidade_escolhe_maior_massa_nao_so_menor_distancia():
    """Capacidade só comporta dois dos três lotes: o solver entrega o maior total em kg possível (a penalidade pesa kg)."""
    stops = [stop("p", GRU, kg=400), stop("q", SANTO_ANDRE, kg=500), stop("r", SBC, kg=450)]
    p = problem(stops, cap=1000, org_cap=1000)
    out = core.plan(p, 2)
    best = max(sum(p.stops[j].kg for j in c) for r in range(0, 4) for c in itertools.combinations(range(3), r) if sum(p.stops[j].kg for j in c) <= 1000)
    assert sum(p.stops[j].kg for j in out["solver"].order) == pytest.approx(best)


def test_solver_atinge_otimo_da_forca_bruta_e_nao_perde_do_baseline():
    stops = [stop("a", GRU, kg=200), stop("b", SANTO_ANDRE, kg=200), stop("c", SBC, kg=200), stop("d", BARUERI, kg=200), stop("e", OSASCO, kg=200)]
    p = problem(stops, cap=2000, org_cap=2000, depot=BARUERI, dest=SP)
    out = core.plan(p, 3)
    m, cands = out["matrices"], out["candidates"]
    bf_order, bf_obj = core.brute_force(p, m, cands)
    assert core.objective(p, m, out["solver"].order, cands) == bf_obj
    assert core.objective(p, m, out["solver"].order, cands) <= core.objective(p, m, out["baseline"].order, cands)
    assert out["comparison"]["solver"]["km"] <= out["comparison"]["baseline"]["km"] + 1e-9


def test_janela_forca_ordem():
    """Doador distante só abre depois: o primeiro a visitar é o que abre cedo, mesmo sendo mais longe."""
    stops = [stop("tarde", GRU, ws=200, we=600), stop("cedo", SBC, ws=0, we=100)]
    p = problem(stops)
    out = core.plan(p, 2)
    assert [p.stops[j].key for j in out["solver"].order] == ["cedo", "tarde"]
    assert core.evaluate(p, out["solver"].order, out["matrices"]).feasible


def test_sem_candidatos_gera_plano_vazio_sem_erro():
    p = problem([stop("frio", GRU, cold=True)])
    out = core.plan(p, 1)
    assert out["solver"].order == [] and out["baseline"].order == []
    assert out["solver"].unassigned[0]["reason"] == "REFRIGERACAO_INCOMPATIVEL"
