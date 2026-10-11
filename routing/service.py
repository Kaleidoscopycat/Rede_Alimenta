"""Camada de aplicação da roteirização: lê doações ACEITAS por uma ONG, monta o problema, planeja (baseline + solver), valida e persiste em routes/route_stops.
Premissas logísticas (desvio, velocidades, descarga, margem, horizonte) vêm de core.settings.ROUTE e são gravadas em `routes.parameters`."""
from __future__ import annotations

import datetime as dt
import math
import uuid
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import ROUTE, TZ
from database import models as m
from routing import core

DISTANCE_BASIS = "HAVERSINE_X_DETOUR"


class RouteError(Exception):
    def __init__(self, message: str, status_code: int = 422, code: str = "ROUTE_ERROR"):
        super().__init__(message)
        self.status_code, self.code = status_code, code


def _window_rel(local_dep: dt.datetime, days_mask: int, start_h: float, end_h: float, need_min: int = 0) -> tuple[int, int] | None:
    """Primeira janela (dia permitido pela máscara; bit 0 = segunda) que ainda não terminou, em minutos relativos à partida. Sem multi-dia: janela futura distante será barrada pelo horizonte."""
    for d in range(0, 8):
        day = (local_dep + dt.timedelta(days=d)).date()
        if not (int(days_mask) >> day.weekday()) & 1:
            continue
        midnight = dt.datetime.combine(day, dt.time(0, 0), tzinfo=local_dep.tzinfo)
        ws, we = midnight + dt.timedelta(hours=float(start_h)), midnight + dt.timedelta(hours=float(end_h))
        ws_min = max(0, math.ceil((ws - local_dep).total_seconds() / 60.0))
        we_min = math.floor((we - local_dep).total_seconds() / 60.0)
        if we_min - need_min >= ws_min:
            return ws_min, we_min
    return None


def _abs(dep: dt.datetime, minutes: int) -> dt.datetime:
    return dep + dt.timedelta(minutes=int(minutes))


def _accepted_org(session: Session, donations: list[m.Donation]) -> uuid.UUID:
    ids = [d.id for d in donations]
    rows = session.execute(select(m.Match.donation_id, m.Match.current_org_id).where(m.Match.donation_id.in_(ids), m.Match.status == "ACCEPTED")).all()
    got = {r[0]: r[1] for r in rows}
    missing = [str(i) for i in ids if i not in got]
    if missing:
        raise RouteError(f"doações sem match ACEITO por uma ONG: {missing}", 409, "DOACAO_SEM_ACEITE")
    orgs = set(got.values())
    if len(orgs) != 1:
        raise RouteError("as doações foram aceitas por ONGs diferentes; o escopo inicial é UMA ONG de destino por rota", 409, "ONGS_DIFERENTES")
    return orgs.pop()


def build_problem(session: Session, user: m.User, donation_ids: list[uuid.UUID], vehicle_id: uuid.UUID | None, departure: dt.datetime, margin_h: float) -> tuple[core.Problem, dict[str, Any]]:
    ids = list(dict.fromkeys(donation_ids))
    if not (1 <= len(ids) <= ROUTE.max_stops):
        raise RouteError(f"informe de 1 a {ROUTE.max_stops} doações", 422, "NUMERO_DE_DOACOES")
    donations = [session.get(m.Donation, i) for i in ids]
    if any(d is None for d in donations):
        raise RouteError("doação não encontrada", 404, "DOACAO_NAO_ENCONTRADA")
    if any(d.expires_at is None or d.quantity_kg is None or d.exige_refrigeracao is None for d in donations):  # type: ignore[union-attr]
        raise RouteError("doação incompleta (validade, quantidade e refrigeração são obrigatórias)", 409, "DOACAO_INCOMPLETA")
    org_id = _accepted_org(session, donations)  # type: ignore[arg-type]
    if user.role == "ORG" and user.organization_id != org_id:
        raise RouteError("as doações não foram aceitas pela sua organização", 403, "FORA_DO_ESCOPO")
    loc = session.get(m.OrganizationLocation, org_id)
    prof = session.get(m.OrganizationProfile, org_id)
    if loc is None or loc.lat is None or loc.lon is None:
        raise RouteError("ONG sem localização conhecida (nunca inventada)", 422, "ONG_SEM_LOCALIZACAO")
    if prof is None:
        raise RouteError("ONG sem perfil declarado (capacidade e horários)", 422, "ONG_SEM_PERFIL")
    if vehicle_id is not None:
        veh = session.get(m.Vehicle, vehicle_id)
        if veh is None:
            raise RouteError("veículo não encontrado", 404, "VEICULO_NAO_ENCONTRADO")
        if user.role == "ORG" and veh.organization_id != user.organization_id:
            raise RouteError("o veículo pertence a outra organização", 403, "FORA_DO_ESCOPO")
    else:
        veh = session.scalars(select(m.Vehicle).where(m.Vehicle.organization_id == org_id).order_by(m.Vehicle.created_at, m.Vehicle.id)).first()
        if veh is None:
            raise RouteError("a ONG de destino não tem veículo cadastrado (informe vehicle_id de um veículo cadastrado)", 422, "SEM_VEICULO")
    local_dep = departure.astimezone(TZ)
    a = core.Assumptions(ROUTE.detour, ROUTE.speed_short_kmh, ROUTE.speed_long_kmh, ROUTE.short_threshold_km, ROUTE.unload_min)
    stops: list[core.Stop] = []
    meta: dict[str, Any] = {"donations": {}, "org_id": org_id, "vehicle": veh, "profile": prof, "location": loc, "departure": departure, "margin_h": margin_h}
    margin = dt.timedelta(hours=margin_h)
    for d in donations:
        dl = session.scalars(select(m.DonorLocation).where(m.DonorLocation.donor_id == d.donor_id).order_by(m.DonorLocation.id.desc())).first()  # type: ignore[union-attr]
        if dl is None:
            raise RouteError("doador sem localização conhecida", 422, "DOADOR_SEM_LOCALIZACAO")
        win = _window_rel(local_dep, d.pickup_days_mask, d.pickup_start_h, d.pickup_end_h, int(d.load_minutes))  # type: ignore[union-attr]
        ws, we = win if win else (10 ** 6, 10 ** 6 + 1)  # sem janela nos próximos 8 dias: cai fora do horizonte (motivo explícito)
        deadline = math.floor(((d.expires_at - margin) - departure).total_seconds() / 60.0)  # type: ignore[union-attr, operator]
        stops.append(core.Stop(key=str(d.id), lat=dl.lat, lon=dl.lon, kg=float(d.quantity_kg), service_min=int(d.load_minutes), win_start=ws, win_end=we,  # type: ignore[union-attr, arg-type]
                               deadline=deadline, cold=bool(d.exige_refrigeracao)))  # type: ignore[union-attr]
        meta["donations"][str(d.id)] = {"donation": d, "donor_id": d.donor_id, "lat": dl.lat, "lon": dl.lon, "precision": dl.location_precision, "window": win,  # type: ignore[union-attr]
                                         "deadline_at": d.expires_at - margin}  # type: ignore[operator]
    dest_win = _window_rel(local_dep, prof.open_days_mask, prof.open_hour, prof.close_hour, ROUTE.unload_min)
    d_open, d_close = dest_win if dest_win else (10 ** 6, 10 ** 6 + 1)
    prob = core.Problem(depot=(veh.base_lat, veh.base_lon), dest=(loc.lat, loc.lon), dest_open=d_open, dest_close=d_close, vehicle_cap_kg=float(veh.capacity_kg),
                        org_cap_kg=float(prof.capacity_max_kg_day), refrigerated=bool(veh.refrigerated), stops=tuple(stops), assumptions=a, horizon_min=int(ROUTE.horizon_h * 60))
    return prob, meta


def _origin(meta: dict[str, Any]) -> dict[str, Any]:
    """Origem do resultado: USER_ENTERED só se TODAS as entradas forem USER_ENTERED; caso contrário SIMULATED, com a rastreabilidade da primeira fonte simulada."""
    srcs = [meta["vehicle"], meta["profile"]] + [x["donation"] for x in meta["donations"].values()]
    sim = [s for s in srcs if s.data_origin == "SIMULATED"]
    if not sim:
        return {"data_origin": "USER_ENTERED", "generator_version": None, "seed": None, "dataset_version": None}
    s0 = sim[0]
    return {"data_origin": "SIMULATED", "generator_version": s0.generator_version, "seed": s0.seed, "dataset_version": s0.dataset_version}


def plan_and_persist(session: Session, user: m.User, donation_ids: list[uuid.UUID], vehicle_id: uuid.UUID | None = None, departure_at: dt.datetime | None = None,
                     safety_margin_h: float | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    departure = (departure_at or now)
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=TZ)
    margin_h = ROUTE.safety_margin_h if safety_margin_h is None else float(safety_margin_h)
    prob, meta = build_problem(session, user, donation_ids, vehicle_id, departure, margin_h)
    result = core.plan(prob, ROUTE.solver_time_limit_s)
    org = _origin(meta)
    gid = uuid.uuid4()
    veh: m.Vehicle = meta["vehicle"]
    params = {"algorithm_version": ROUTE.algorithm_version, "detour": ROUTE.detour, "speed_short_kmh": ROUTE.speed_short_kmh, "speed_long_kmh": ROUTE.speed_long_kmh,
              "short_threshold_km": ROUTE.short_threshold_km, "unload_min": ROUTE.unload_min, "safety_margin_h": margin_h, "horizon_h": ROUTE.horizon_h,
              "solver_time_limit_s": ROUTE.solver_time_limit_s, "vehicle_capacity_kg": veh.capacity_kg, "vehicle_refrigerated": veh.refrigerated,
              "org_capacity_kg": prob.org_cap_kg, "dest_window_min": [prob.dest_open, prob.dest_close], "departure_at": departure.isoformat(), "distance_basis": DISTANCE_BASIS,
              "baseline": core.ALGO_BASELINE, "penalty_base": core.PENALTY_BASE}
    reason_txt = core.REASONS
    keys = [s.key for s in prob.stops]
    out_routes: list[m.Route] = []
    for res, primary in ((result["solver"], True), (result["baseline"], False)):
        ev = res.evaluation
        un = [{"donation_id": u["key"], "reason": u["reason"], "reason_text": reason_txt[u["reason"]]} for u in res.unassigned]
        r = m.Route(id=uuid.uuid4(), plan_group_id=gid, is_primary=primary, organization_id=meta["org_id"], vehicle_id=veh.id, requested_by=user.id,
                    status="PLANNED" if res.order else "INFEASIBLE", algorithm=res.algorithm, algorithm_version=ROUTE.algorithm_version, parameters=params, departure_at=departure,
                    delivery_done_at=_abs(departure, ev.done) if res.order else None, total_km_est=ev.km if res.order else None, total_minutes_est=ev.minutes if res.order else None,
                    kg_collected=ev.kg, n_stops=len(res.order), unassigned=un, comparison=_cmp_json(result["comparison"]), solver_info=_jsonable(res.info),
                    distance_basis=DISTANCE_BASIS, created_at=now, **org)
        session.add(r)
        session.flush()
        seq = 0
        session.add(m.RouteStop(route_id=r.id, seq=seq, stop_type="DEPARTURE", lat=veh.base_lat, lon=veh.base_lon, location_precision=veh.location_precision, planned_arrival_at=departure,
                                planned_start_at=departure, planned_depart_at=departure, load_kg_after=0.0, data_origin=org["data_origin"], generator_version=org["generator_version"],
                                seed=org["seed"], dataset_version=org["dataset_version"]))
        if res.order:
            for j, v in zip(res.order, ev.visits, strict=True):
                seq += 1
                info = meta["donations"][keys[j]]
                win = info["window"]
                session.add(m.RouteStop(route_id=r.id, seq=seq, stop_type="PICKUP", donation_id=info["donation"].id, donor_id=info["donor_id"], lat=info["lat"], lon=info["lon"],
                                        location_precision=info["precision"], planned_arrival_at=_abs(departure, v.arrival), planned_start_at=_abs(departure, v.start),
                                        planned_depart_at=_abs(departure, v.depart), wait_min=v.wait, window_start_at=_abs(departure, win[0]) if win else None,
                                        window_end_at=_abs(departure, win[1]) if win else None, deadline_at=info["deadline_at"], load_kg_after=v.load_kg_after, leg_km_est=v.leg_km,
                                        leg_minutes_est=v.leg_min, data_origin=org["data_origin"], generator_version=org["generator_version"], seed=org["seed"], dataset_version=org["dataset_version"]))
            seq += 1
            session.add(m.RouteStop(route_id=r.id, seq=seq, stop_type="DELIVERY", lat=meta["location"].lat, lon=meta["location"].lon, location_precision=meta["location"].location_precision,
                                    planned_arrival_at=_abs(departure, ev.dest_arrival), planned_start_at=_abs(departure, ev.dest_start), planned_depart_at=_abs(departure, ev.done),
                                    wait_min=ev.dest_start - ev.dest_arrival, load_kg_after=0.0, leg_km_est=ev.dest_leg_km,
                                    leg_minutes_est=ev.dest_arrival - (ev.visits[-1].depart if ev.visits else 0), data_origin=org["data_origin"],
                                    generator_version=org["generator_version"], seed=org["seed"], dataset_version=org["dataset_version"]))
        out_routes.append(r)
    session.flush()
    return {"plan_group_id": str(gid), "primary": route_view(session, out_routes[0]), "baseline": route_view(session, out_routes[1]), "comparison": _cmp_json(result["comparison"])}


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def _cmp_json(c: dict[str, Any]) -> dict[str, Any]:
    return _jsonable(c)


def rotulo(origin: str) -> str:
    if origin == "SIMULATED":
        return ("SIMULAÇÃO: frota, janelas de retirada, capacidade e horários vêm de premissas SIMULADAS; distâncias e tempos são ESTIMATIVAS (linha reta × fator de desvio ÷ velocidade), "
                "não rota viária; resultados não representam desempenho real.")
    return "ESTIMATIVA com premissas logísticas não verificadas (linha reta × desvio ÷ velocidade); não é rota viária."


def route_view(session: Session, r: m.Route) -> dict[str, Any]:
    veh = session.get(m.Vehicle, r.vehicle_id)
    org = session.get(m.Organization, r.organization_id)
    stops = session.scalars(select(m.RouteStop).where(m.RouteStop.route_id == r.id).order_by(m.RouteStop.seq)).all()
    return {"id": str(r.id), "plan_group_id": str(r.plan_group_id), "is_primary": r.is_primary, "algorithm": r.algorithm, "algorithm_version": r.algorithm_version, "status": r.status,
            "organization": org.ong_id if org else None, "organization_id": str(r.organization_id),
            "vehicle": {"id": str(veh.id), "type": veh.vehicle_type, "capacity_kg": veh.capacity_kg, "refrigerated": veh.refrigerated, "data_origin": veh.data_origin,
                        "base_municipio_ibge": veh.base_municipio_ibge, "location_precision": veh.location_precision} if veh else None,
            "departure_at": r.departure_at, "delivery_done_at": r.delivery_done_at, "total_km_est": r.total_km_est, "total_minutes_est": r.total_minutes_est, "kg_collected": r.kg_collected,
            "n_stops": r.n_stops, "unassigned": r.unassigned, "comparison": r.comparison, "parameters": r.parameters, "solver_info": r.solver_info, "distance_basis": r.distance_basis,
            "data_origin": r.data_origin, "generator_version": r.generator_version, "dataset_version": r.dataset_version, "seed": r.seed, "rotulo": rotulo(r.data_origin), "created_at": r.created_at,
            "stops": [{"seq": s.seq, "type": s.stop_type, "donation_id": str(s.donation_id) if s.donation_id else None, "lat": s.lat, "lon": s.lon, "location_precision": s.location_precision,
                       "planned_arrival_at": s.planned_arrival_at, "planned_start_at": s.planned_start_at, "planned_depart_at": s.planned_depart_at, "wait_min": s.wait_min,
                       "window_start_at": s.window_start_at, "window_end_at": s.window_end_at, "deadline_at": s.deadline_at, "load_kg_after": s.load_kg_after, "leg_km_est": s.leg_km_est,
                       "leg_minutes_est": s.leg_minutes_est, "data_origin": s.data_origin} for s in stops]}


__all__ = ["RouteError", "plan_and_persist", "route_view", "build_problem", "asdict"]
