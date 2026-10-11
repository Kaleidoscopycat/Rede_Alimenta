"""Núcleo puro (sem banco, sem API) da roteirização: problema, matrizes, verificador de restrições, baseline (vizinho mais próximo) e solver (OR-Tools).

Problema (1 veículo, 1 ONG de destino): sair da base → coletar em doadores → entregar na ONG.
Restrições: capacidade do veículo (kg) · janela de retirada de cada doador · entrega concluída até (validade − margem) de CADA lote a bordo ·
lote refrigerado só em veículo refrigerado · capacidade de recebimento da ONG (kg) · horário de funcionamento da ONG · duração máxima da viagem.
Tempo em minutos inteiros desde a partida. `evaluate` é um verificador INDEPENDENTE: nenhuma rota (do baseline ou do solver) é aceita sem passar por ele.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from pipelines.geo import haversine_km

ALGO_BASELINE = "NEAREST_NEIGHBOR"
ALGO_SOLVER = "ORTOOLS_GLS"
PENALTY_BASE = 10_000_000  # custo (em "metros") de deixar um lote de fora: 10 000 km — entregar mais lotes sempre domina economizar km

REASONS: dict[str, str] = {
    "REFRIGERACAO_INCOMPATIVEL": "lote refrigerado e o veículo não é refrigerado",
    "EXCEDE_CAPACIDADE_VEICULO": "lote maior que a capacidade do veículo (kg)",
    "EXCEDE_CAPACIDADE_ONG": "lote maior que a capacidade de recebimento da ONG (kg)",
    "JANELA_INSUFICIENTE": "a janela de retirada do doador é menor que o tempo de carga",
    "JANELA_INALCANCAVEL": "o veículo não chega ao doador antes do fim da janela de retirada",
    "PRAZO_INVIAVEL": "mesmo coletando só este lote, a entrega não seria concluída antes de (validade − margem)",
    "FORA_DO_HORIZONTE": "a coleta cairia além da duração máxima da viagem",
    "JANELA_ONG_INVIAVEL": "a ONG estaria fechada no horário em que a entrega seria possível",
    "NAO_COUBE_NA_ROTA": "viável isoladamente, mas não coube na rota (capacidade, janelas ou prazos combinados)",
}


@dataclass(frozen=True)
class Assumptions:
    detour: float
    speed_short_kmh: float
    speed_long_kmh: float
    short_threshold_km: float = 15.0
    unload_min: int = 30


@dataclass(frozen=True)
class Stop:
    key: str
    lat: float
    lon: float
    kg: float
    service_min: int
    win_start: int   # início da janela de retirada (min desde a partida)
    win_end: int     # fim da janela (a carga precisa TERMINAR até aqui)
    deadline: int    # minuto-limite da ENTREGA CONCLUÍDA (validade − margem)
    cold: bool = False


@dataclass(frozen=True)
class Problem:
    depot: tuple[float, float]
    dest: tuple[float, float]
    dest_open: int
    dest_close: int
    vehicle_cap_kg: float
    org_cap_kg: float
    refrigerated: bool
    stops: tuple[Stop, ...]
    assumptions: Assumptions
    horizon_min: int = 720


@dataclass
class Matrices:
    km: np.ndarray        # km estimados (linha reta × desvio); nós: 0 = base, 1..n = doadores, n+1 = ONG
    minutes: np.ndarray   # minutos de deslocamento (inteiros, arredondados para cima)
    straight_km: np.ndarray


def build_matrices(p: Problem) -> Matrices:
    pts = [p.depot] + [(s.lat, s.lon) for s in p.stops] + [p.dest]
    lat = np.array([x[0] for x in pts], dtype=float)
    lon = np.array([x[1] for x in pts], dtype=float)
    straight = np.asarray(haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :]), dtype=float)
    if np.isnan(straight).any():
        raise ValueError("coordenada ausente: não é possível calcular a matriz (nunca tratada como 0 km)")
    a = p.assumptions
    road = straight * a.detour
    speed = np.where(straight <= a.short_threshold_km, a.speed_short_kmh, a.speed_long_kmh)
    minutes = np.ceil(road / speed * 60.0 - 1e-9).astype(int)
    np.fill_diagonal(minutes, 0)
    return Matrices(km=road, minutes=minutes, straight_km=straight)


@dataclass
class Visit:
    key: str
    arrival: int
    start: int
    wait: int
    depart: int
    load_kg_after: float
    leg_km: float
    leg_min: int
    deadline: int


@dataclass
class Evaluation:
    feasible: bool
    violations: list[str]
    visits: list[Visit]
    dest_arrival: int
    dest_start: int
    done: int
    km: float
    minutes: int
    kg: float
    dest_leg_km: float = 0.0


def evaluate(p: Problem, order: Sequence[int], m: Matrices | None = None) -> Evaluation:
    """Simula a rota (índices 0-based de `p.stops`) com partida no minuto 0 e confere TODAS as restrições."""
    m = m or build_matrices(p)
    n = len(p.stops)
    cap = min(p.vehicle_cap_kg, p.org_cap_kg)
    viol: list[str] = []
    visits: list[Visit] = []
    t, pos, load, km = 0, 0, 0.0, 0.0
    for j in order:
        s = p.stops[j]
        node = j + 1
        leg_m, leg_k = int(m.minutes[pos][node]), float(m.km[pos][node])
        arr = t + leg_m
        start = max(arr, s.win_start)
        if s.cold and not p.refrigerated:
            viol.append(f"REFRIGERACAO:{s.key}")
        if start > s.win_end - s.service_min:
            viol.append(f"JANELA_DOADOR:{s.key}")
        load += s.kg
        if load > p.vehicle_cap_kg + 1e-6:
            viol.append("CAPACIDADE_VEICULO")
        if load > p.org_cap_kg + 1e-6:
            viol.append("CAPACIDADE_ONG")
        depart = start + s.service_min
        visits.append(Visit(s.key, arr, start, start - arr, depart, load, leg_k, leg_m, s.deadline))
        t, pos, km = depart, node, km + leg_k
    dleg_m, dleg_k = int(m.minutes[pos][n + 1]), float(m.km[pos][n + 1])
    dest_arr = t + dleg_m
    dest_start = max(dest_arr, p.dest_open)
    done = dest_start + p.assumptions.unload_min
    km += dleg_k
    if done > p.dest_close:
        viol.append("JANELA_ONG")
    if done > p.horizon_min:
        viol.append("HORIZONTE")
    for j in order:
        s = p.stops[j]
        if done > s.deadline:
            viol.append(f"PRAZO_VALIDADE:{s.key}")
    _ = cap
    return Evaluation(feasible=not viol, violations=viol, visits=visits, dest_arrival=dest_arr, dest_start=dest_start, done=done, km=round(km, 3), minutes=done,
                      kg=round(sum(p.stops[j].kg for j in order), 3), dest_leg_km=dleg_k)


def screen(p: Problem, m: Matrices) -> tuple[list[int], dict[int, str]]:
    """Separa os lotes que podem, em tese, entrar numa rota dos que são inviáveis sozinhos (com o motivo)."""
    ok: list[int] = []
    rej: dict[int, str] = {}
    for j, s in enumerate(p.stops):
        if s.cold and not p.refrigerated:
            rej[j] = "REFRIGERACAO_INCOMPATIVEL"
        elif s.kg > p.vehicle_cap_kg + 1e-9:
            rej[j] = "EXCEDE_CAPACIDADE_VEICULO"
        elif s.kg > p.org_cap_kg + 1e-9:
            rej[j] = "EXCEDE_CAPACIDADE_ONG"
        elif s.win_end - s.service_min < s.win_start:
            rej[j] = "JANELA_INSUFICIENTE"
        else:
            ev = evaluate(p, [j], m)
            if ev.feasible:
                ok.append(j)
            else:
                v = ev.violations[0].split(":")[0]
                rej[j] = {"JANELA_DOADOR": "JANELA_INALCANCAVEL", "PRAZO_VALIDADE": "PRAZO_INVIAVEL", "HORIZONTE": "FORA_DO_HORIZONTE", "JANELA_ONG": "JANELA_ONG_INVIAVEL"}.get(v, "PRAZO_INVIAVEL")
    return ok, rej


# ---------------------------------------------------------------------------------------------- baseline: vizinho mais próximo
def nearest_neighbor(p: Problem, m: Matrices, candidates: Sequence[int]) -> list[int]:
    """Baseline obrigatório: a cada passo vai ao doador mais próximo (km estimados) que mantém a rota VIÁVEL (capacidade, janela e prazo de todos os lotes a bordo)."""
    n = len(p.stops)
    cap = min(p.vehicle_cap_kg, p.org_cap_kg)
    remaining = set(candidates)
    order: list[int] = []
    t, pos, load, min_deadline = 0, 0, 0.0, 10 ** 9
    while remaining:
        chosen = None
        for j in sorted(remaining, key=lambda x: (m.km[pos][x + 1], x)):
            s = p.stops[j]
            node = j + 1
            start = max(t + int(m.minutes[pos][node]), s.win_start)
            if start > s.win_end - s.service_min or load + s.kg > cap + 1e-9:
                continue
            md = min(min_deadline, s.deadline)
            done = max(start + s.service_min + int(m.minutes[node][n + 1]), p.dest_open) + p.assumptions.unload_min
            if done > min(p.dest_close, md, p.horizon_min):
                continue
            chosen = (j, start, md)
            break
        if chosen is None:
            break
        j, start, md = chosen
        order.append(j)
        remaining.discard(j)
        t, pos, load, min_deadline = start + p.stops[j].service_min, j + 1, load + p.stops[j].kg, md
    return order


# ---------------------------------------------------------------------------------------------- objetivo (igual ao do solver)
def objective(p: Problem, m: Matrices, order: Sequence[int], universe: Sequence[int]) -> int:
    """Custo inteiro do solver: Σ arcos (metros) + Σ penalidade dos lotes de `universe` deixados de fora."""
    n = len(p.stops)
    seq = [0] + [j + 1 for j in order] + [n + 1]
    cost = sum(int(round(m.km[a][b] * 1000)) for a, b in zip(seq[:-1], seq[1:], strict=False))
    skipped = set(universe) - set(order)
    return cost + sum(PENALTY_BASE + int(math.ceil(p.stops[j].kg * 10)) for j in skipped)


# ---------------------------------------------------------------------------------------------- solver OR-Tools
def solve_ortools(p: Problem, m: Matrices, candidates: Sequence[int], time_limit_s: int = 3, warm_start: Sequence[int] | None = None) -> tuple[list[int], dict[str, Any]]:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # import tardio: o módulo é pesado e só a roteirização o usa

    cands = list(candidates)
    k = len(cands)
    info: dict[str, Any] = {"solver": "ortools.constraint_solver", "time_limit_s": time_limit_s, "n_candidates": k}
    if k == 0:
        info["status"] = "SEM_CANDIDATOS"
        return [], info
    n_all = len(p.stops)
    idx = [0] + [c + 1 for c in cands] + [n_all + 1]
    km = m.km[np.ix_(idx, idx)]
    mins = m.minutes[np.ix_(idx, idx)]
    unload = p.assumptions.unload_min
    horizon = int(p.horizon_min)
    manager = pywrapcp.RoutingIndexManager(k + 2, 1, [0], [k + 1])
    routing = pywrapcp.RoutingModel(manager)

    def dist_cb(fi: int, ti: int) -> int:
        return int(round(km[manager.IndexToNode(fi)][manager.IndexToNode(ti)] * 1000))

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(dist_cb))

    def time_cb(fi: int, ti: int) -> int:
        a, b = manager.IndexToNode(fi), manager.IndexToNode(ti)
        svc = p.stops[cands[a - 1]].service_min if 1 <= a <= k else 0
        return int(mins[a][b]) + svc

    routing.AddDimension(routing.RegisterTransitCallback(time_cb), horizon, horizon, True, "T")
    T = routing.GetDimensionOrDie("T")
    for pos in range(1, k + 1):
        s = p.stops[cands[pos - 1]]
        T.CumulVar(manager.NodeToIndex(pos)).SetRange(int(s.win_start), int(min(s.win_end - s.service_min, horizon)))
    end = routing.End(0)
    hi = min(p.dest_close - unload, horizon - unload)
    if hi < p.dest_open:
        info["status"] = "ONG_FECHADA"
        return [], info
    T.CumulVar(end).SetRange(int(p.dest_open), int(hi))
    big = horizon + 10 ** 6
    sv = routing.solver()
    for pos in range(1, k + 1):
        s = p.stops[cands[pos - 1]]
        active = routing.ActiveVar(manager.NodeToIndex(pos))
        sv.Add(T.CumulVar(end) <= int(s.deadline - unload) + (1 - active) * big)

    def dem_cb(fi: int) -> int:
        node = manager.IndexToNode(fi)
        return int(math.ceil(p.stops[cands[node - 1]].kg * 10)) if 1 <= node <= k else 0

    cap10 = int(math.floor(min(p.vehicle_cap_kg, p.org_cap_kg) * 10 + 1e-6))
    routing.AddDimensionWithVehicleCapacity(routing.RegisterUnaryTransitCallback(dem_cb), 0, [cap10], True, "L")
    for pos in range(1, k + 1):
        routing.AddDisjunction([manager.NodeToIndex(pos)], PENALTY_BASE + int(math.ceil(p.stops[cands[pos - 1]].kg * 10)))
    sp = pywrapcp.DefaultRoutingSearchParameters()
    sp.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    sp.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    sp.time_limit.FromSeconds(int(time_limit_s))
    routing.CloseModel()
    start_sol = None
    if warm_start:
        pos_of = {c: i + 1 for i, c in enumerate(cands)}
        try:
            start_sol = routing.ReadAssignmentFromRoutes([[pos_of[j] for j in warm_start if j in pos_of]], True)
        except Exception:  # noqa: BLE001 - o aquecimento é opcional; sem ele o solver parte do PATH_CHEAPEST_ARC
            start_sol = None
    sol = routing.SolveFromAssignmentWithParameters(start_sol, sp) if start_sol is not None else routing.SolveWithParameters(sp)
    info["status_code"] = int(routing.status())
    info["status"] = {0: "NAO_RESOLVIDO", 1: "SUCESSO", 2: "SEM_SOLUCAO", 3: "TEMPO_ESGOTADO_SEM_SOLUCAO", 4: "INVALIDO"}.get(int(routing.status()), "DESCONHECIDO")
    info["warm_start"] = bool(start_sol is not None)
    if sol is None:
        return [], info
    order: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if 1 <= node <= k:
            order.append(cands[node - 1])
        index = sol.Value(routing.NextVar(index))
    info["objective_solver"] = int(sol.ObjectiveValue())
    return order, info


def brute_force(p: Problem, m: Matrices, candidates: Sequence[int]) -> tuple[list[int], int]:
    """Ótimo exato por enumeração (só para instâncias pequenas em testes): minimiza o MESMO objetivo do solver sobre rotas viáveis."""
    cands = list(candidates)
    best: tuple[int, list[int]] = (objective(p, m, [], cands), [])
    for r in range(1, len(cands) + 1):
        for subset in itertools.combinations(cands, r):
            for perm in itertools.permutations(subset):
                ev = evaluate(p, perm, m)
                if ev.feasible:
                    c = objective(p, m, perm, cands)
                    if c < best[0]:
                        best = (c, list(perm))
    return best[1], best[0]


# ---------------------------------------------------------------------------------------------- orquestração
@dataclass
class PlanResult:
    algorithm: str
    order: list[int]
    evaluation: Evaluation
    unassigned: list[dict[str, str]] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)


def _result(p: Problem, m: Matrices, algo: str, order: list[int], rejected: dict[int, str], info: dict[str, Any] | None = None) -> PlanResult:
    ev = evaluate(p, order, m)
    unassigned = [{"key": p.stops[j].key, "reason": rejected.get(j, "NAO_COUBE_NA_ROTA")} for j in range(len(p.stops)) if j not in set(order)]
    return PlanResult(algo, order, ev, unassigned, info or {})


def plan(p: Problem, time_limit_s: int = 3) -> dict[str, Any]:
    """Planeja com o baseline e com o solver; ambos passam pelo verificador. Se o solver ficar pior que o baseline no objetivo, mantém-se o baseline (registrado)."""
    m = build_matrices(p)
    cands, rejected = screen(p, m)
    nn_order = nearest_neighbor(p, m, cands)
    base = _result(p, m, ALGO_BASELINE, nn_order, rejected, {"descricao": "vizinho mais próximo com viabilidade"})
    so_order, sinfo = solve_ortools(p, m, cands, time_limit_s, warm_start=nn_order)
    sinfo["fallback_to_baseline"] = False
    if so_order or sinfo.get("status") == "SUCESSO":
        if not evaluate(p, so_order, m).feasible:
            sinfo["inconsistencia"] = "rota do solver reprovada pelo verificador"
            so_order = nn_order
            sinfo["fallback_to_baseline"] = True
        elif objective(p, m, so_order, cands) > objective(p, m, nn_order, cands):
            so_order = nn_order
            sinfo["fallback_to_baseline"] = True
    else:
        so_order = nn_order
        sinfo["fallback_to_baseline"] = True
    sol = _result(p, m, ALGO_SOLVER, so_order, rejected, sinfo)
    b, s = base.evaluation, sol.evaluation
    cmp = {
        "baseline": {"km": b.km, "minutes": b.minutes, "lots_delivered": len(base.order), "kg": b.kg, "unassigned": len(base.unassigned)},
        "solver": {"km": s.km, "minutes": s.minutes, "lots_delivered": len(sol.order), "kg": s.kg, "unassigned": len(sol.unassigned)},
        "km_delta_pct": round(100.0 * (s.km - b.km) / b.km, 2) if b.km > 0 else None,
        "lots_delta": len(sol.order) - len(base.order),
    }
    return {"matrices": m, "candidates": cands, "rejected": rejected, "baseline": base, "solver": sol, "comparison": cmp}
