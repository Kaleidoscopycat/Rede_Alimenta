"""Benchmark da roteirização: baseline (vizinho mais próximo) × solver (OR-Tools) sobre instâncias SIMULADAS montadas com ONGs/veículos/doadores/lotes já importados no banco.
Tudo aqui é SIMULAÇÃO (doadores, lotes, frota, janelas, prazo). Distâncias/tempos são estimativas (haversine × desvio ÷ velocidade), NÃO rota viária; os números NÃO são desempenho real.
Uso: python -m routing.benchmark --scenario {mesmo_municipio,municipios_vizinhos} --n 20 --seed 20261011 [--time-limit 2] [--out docs/ROUTING_BENCHMARK_<cenario>.json]
Premissas do benchmark (documentadas em docs/ROUTING.md): saída às 08:00 de um dia em que todos funcionam (máscaras de dias ignoradas); prazo de validade = 48 h − margem ROUTE_SAFETY_MARGIN_H;
carga = lote histórico SIMULADO do doador; janela de retirada = janela do próprio doador; veículo = frota SIMULADA da própria ONG."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import time
from pathlib import Path

import numpy as np
from sqlalchemy import select

from core.settings import ROUTE
from database import models as m
from database.session import session_scope
from pipelines.geo import haversine_km
from routing import core

ROOT = Path(__file__).resolve().parents[1]
DEP_H = 8.0
SHELF_H = 48.0
RADIUS_KM = 40.0
N_STOPS = 8


def _instance(rng: random.Random, orgs: list[dict], donors, scenario: str) -> tuple[core.Problem, dict] | None:
    o = rng.choice(orgs)
    d = donors
    dist = haversine_km(o["lat"], o["lon"], d["lat"].to_numpy(), d["lon"].to_numpy())
    if scenario == "mesmo_municipio":
        pool = d[(d["mun"] == o["mun"])]
    else:
        pool = d[(dist <= RADIUS_KM) & (d["mun"] != o["mun"])]
        if pool["mun"].nunique() < 3:
            return None
    if len(pool) < N_STOPS:
        return None
    if scenario == "municipios_vizinhos":  # no máximo um doador por município para espalhar as paradas
        pool = pool.sample(frac=1.0, random_state=rng.randint(0, 10 ** 6)).drop_duplicates("mun")
        if len(pool) < 4:
            return None
    pick = pool.sample(min(N_STOPS, len(pool)), random_state=rng.randint(0, 10 ** 6))
    dep = DEP_H * 60
    margin_min = ROUTE.safety_margin_h * 60
    stops = []
    for r in pick.itertuples(index=False):
        ws = max(0, int((r.start_h - DEP_H) * 60))
        we = int((r.end_h - DEP_H) * 60)
        stops.append(core.Stop(key=str(r.donor_ext), lat=r.lat, lon=r.lon, kg=float(r.kg), service_min=int(r.load_min), win_start=ws, win_end=we,
                               deadline=int(SHELF_H * 60 - margin_min), cold=bool(r.cold)))
    a = core.Assumptions(ROUTE.detour, ROUTE.speed_short_kmh, ROUTE.speed_long_kmh, ROUTE.short_threshold_km, ROUTE.unload_min)
    prob = core.Problem(depot=(o["vlat"], o["vlon"]), dest=(o["lat"], o["lon"]), dest_open=max(0, int((o["open"] - DEP_H) * 60)), dest_close=int((o["close"] - DEP_H) * 60),
                        vehicle_cap_kg=o["cap"], org_cap_kg=o["org_cap"], refrigerated=o["refrig"], stops=tuple(stops), assumptions=a, horizon_min=int(ROUTE.horizon_h * 60))
    _ = dep
    return prob, {"org": o["ong_id"], "vehicle_kg": o["cap"], "refrigerated": o["refrig"]}


def load_pools():
    import pandas as pd
    with session_scope() as s:
        rows = s.execute(select(m.Organization.ong_id, m.Organization.municipio_ibge, m.OrganizationLocation.lat, m.OrganizationLocation.lon, m.Vehicle.base_lat, m.Vehicle.base_lon,
                                m.Vehicle.capacity_kg, m.Vehicle.refrigerated, m.OrganizationProfile.capacity_max_kg_day, m.OrganizationProfile.open_hour, m.OrganizationProfile.close_hour)
                         .join(m.OrganizationLocation, m.OrganizationLocation.organization_id == m.Organization.id).join(m.Vehicle, m.Vehicle.organization_id == m.Organization.id)
                         .join(m.OrganizationProfile, m.OrganizationProfile.organization_id == m.Organization.id)
                         .where(m.OrganizationLocation.lat.is_not(None), m.Vehicle.data_origin == "SIMULATED")).all()
        orgs = [dict(ong_id=r[0], mun=r[1], lat=r[2], lon=r[3], vlat=r[4], vlon=r[5], cap=float(r[6]), refrig=bool(r[7]), org_cap=float(r[8]), open=float(r[9]), close=float(r[10]))
                for r in rows if r[1] is not None]
        dv = s.scalar(select(m.Donor.dataset_version).where(m.Donor.data_origin == "SIMULATED").limit(1))
        drows = s.execute(select(m.Donor.external_id, m.Donor.municipio_ibge, m.DonorLocation.lat, m.DonorLocation.lon, m.Donor.pickup_start_h, m.Donor.pickup_end_h, m.Donor.load_minutes,
                                 m.Donor.id).join(m.DonorLocation, m.DonorLocation.donor_id == m.Donor.id).where(m.Donor.dataset_version == dv)).all()
        dn = pd.DataFrame(drows, columns=["donor_ext", "mun", "lat", "lon", "start_h", "end_h", "load_min", "id"])
        lots = s.execute(select(m.Donation.donor_id, m.Donation.quantity_kg, m.Donation.exige_refrigeracao).where(m.Donation.dataset_version == dv, m.Donation.quantity_kg.is_not(None))).all()
        ld = pd.DataFrame(lots, columns=["id", "kg", "cold"]).groupby("id").first().reset_index()
    donors = dn.merge(ld, on="id")
    return orgs, donors, dv


def run(scenario: str, n: int, seed: int, time_limit: int) -> dict:
    orgs, donors, dv = load_pools()
    rng = random.Random(seed)  # nosec B311  # noqa: S311 — amostragem reprodutível por semente do benchmark (sem uso criptográfico)
    rows, tries = [], 0
    t0 = time.perf_counter()
    while len(rows) < n and tries < n * 200:
        tries += 1
        inst = _instance(rng, orgs, donors, scenario)
        if inst is None:
            continue
        prob, meta = inst
        out = core.plan(prob, time_limit)
        m_, cands = out["matrices"], out["candidates"]
        b, s_ = out["baseline"], out["solver"]
        if not cands:
            continue
        ob, os_ = core.objective(prob, m_, b.order, cands), core.objective(prob, m_, s_.order, cands)
        rows.append({"org": meta["org"], "paradas_ofertadas": len(prob.stops), "elegiveis": len(cands),
                     "baseline": {"km": b.evaluation.km, "minutos": b.evaluation.minutes, "lotes": len(b.order), "kg": b.evaluation.kg},
                     "solver": {"km": s_.evaluation.km, "minutos": s_.evaluation.minutes, "lotes": len(s_.order), "kg": s_.evaluation.kg},
                     "viavel_baseline": b.evaluation.feasible, "viavel_solver": s_.evaluation.feasible, "solver_objetivo_menor_ou_igual": os_ <= ob,
                     "solver_voltou_ao_baseline": bool(s_.info.get("fallback_to_baseline"))})
    def agg(k: str, f: str) -> float:
        return round(statistics.mean(r[k][f] for r in rows), 2) if rows else float("nan")
    same_lots = sum(1 for r in rows if r["solver"]["lotes"] == r["baseline"]["lotes"])
    better_km = sum(1 for r in rows if r["solver"]["lotes"] == r["baseline"]["lotes"] and r["solver"]["km"] < r["baseline"]["km"] - 1e-9)
    worse_km = sum(1 for r in rows if r["solver"]["lotes"] == r["baseline"]["lotes"] and r["solver"]["km"] > r["baseline"]["km"] + 1e-9)
    more_lots = sum(1 for r in rows if r["solver"]["lotes"] > r["baseline"]["lotes"])
    fewer_lots = sum(1 for r in rows if r["solver"]["lotes"] < r["baseline"]["lotes"])
    return {"rotulo": "SIMULAÇÃO: doadores, lotes, frota e janelas SIMULADOS; ONGs e municípios são registros públicos reais; distâncias/tempos são estimativas (linha reta × desvio ÷ velocidade), "
                      "não rota viária. NÃO representa desempenho no mundo real.",
            "scenario": scenario, "instancias": len(rows), "seed": seed, "tentativas": tries, "dataset_version": dv, "algoritmo_versao": ROUTE.algorithm_version,
            "parametros": {"detour": ROUTE.detour, "speed_short_kmh": ROUTE.speed_short_kmh, "speed_long_kmh": ROUTE.speed_long_kmh, "unload_min": ROUTE.unload_min,
                           "safety_margin_h": ROUTE.safety_margin_h, "horizon_h": ROUTE.horizon_h, "solver_time_limit_s": time_limit, "paradas_por_instancia": N_STOPS,
                           "raio_km_vizinhos": RADIUS_KM, "saida": f"{int(DEP_H):02d}:00", "validade_h": SHELF_H},
            "medias": {"baseline": {k: agg("baseline", k) for k in ("km", "minutos", "lotes", "kg")}, "solver": {k: agg("solver", k) for k in ("km", "minutos", "lotes", "kg")}},
            "contagens": {"mesmo_numero_de_lotes": same_lots, "solver_menos_km_com_mesmos_lotes": better_km, "solver_mais_km_com_mesmos_lotes": worse_km, "solver_entrega_mais_lotes": more_lots,
                          "solver_entrega_menos_lotes": fewer_lots, "todas_viaveis": all(r["viavel_baseline"] and r["viavel_solver"] for r in rows),
                          "solver_nunca_pior_no_objetivo": all(r["solver_objetivo_menor_ou_igual"] for r in rows)},
            "segundos": round(time.perf_counter() - t0, 1), "instancias_detalhe": rows,
            "gerado_em": dt.datetime.now(dt.timezone.utc).isoformat()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["mesmo_municipio", "municipios_vizinhos"], required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--time-limit", type=int, default=2)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(a.scenario, a.n, a.seed, a.time_limit)
    out = Path(a.out) if a.out else ROOT / "docs" / f"ROUTING_BENCHMARK_{a.scenario}.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x)), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("scenario", "instancias", "medias", "contagens", "segundos")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
