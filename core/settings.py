"""Configuração por variáveis de ambiente (sem segredos no código). Premissas do motor de match são PREMISSAS DO PROJETO, não verificadas."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Sao_Paulo"))


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class MatchSettings:
    """Pesos e premissas do motor (ver docs/FASE2_P1_MATCH_ENGINE.md). Todos configuráveis; NENHUM foi calibrado com dados reais."""
    engine_version: str = "match-engine-1.0.0"
    # FINAL_SCORE = w_ml*ML_SCORE + w_rule*BUSINESS_RULE_SCORE + w_dist*DISTANCE_SCORE  (soma = 1)
    w_ml: float = field(default_factory=lambda: _f("MATCH_W_ML", 0.50))
    w_rule: float = field(default_factory=lambda: _f("MATCH_W_RULE", 0.30))
    w_dist: float = field(default_factory=lambda: _f("MATCH_W_DIST", 0.20))
    # componentes do BUSINESS_RULE_SCORE (soma = 1)
    br_capacity: float = field(default_factory=lambda: _f("MATCH_BR_CAPACITY", 0.35))
    br_refrigeration: float = field(default_factory=lambda: _f("MATCH_BR_REFRIG", 0.30))
    br_org_type: float = field(default_factory=lambda: _f("MATCH_BR_ORGTYPE", 0.20))
    br_regional: float = field(default_factory=lambda: _f("MATCH_BR_REGIONAL", 0.15))
    # DISTANCE_SCORE = a*exp(-dist/d0) + (1-a)*folga_normalizada
    dist_d0_km: float = field(default_factory=lambda: _f("MATCH_DIST_D0_KM", 30.0))
    dist_alpha: float = field(default_factory=lambda: _f("MATCH_DIST_ALPHA", 0.5))
    k_candidates: int = field(default_factory=lambda: _i("MATCH_K", 15))
    radius_km: float = field(default_factory=lambda: _f("MATCH_RADIUS_KM", 150.0))
    schedule_horizon_days: int = 7
    proposal_ttl_minutes: float = field(default_factory=lambda: _f("PROPOSAL_TTL_MINUTES", 30.0))
    expiry_scan_seconds: float = field(default_factory=lambda: _f("EXPIRY_SCAN_SECONDS", 15.0))
    # fator de desvio / velocidades: mesmas premissas da Fase 1 (api/service.py)


SETTINGS = MatchSettings()


@dataclass(frozen=True)
class RouteSettings:
    """Premissas da roteirização (Fase 2 Parte 2). Mesma metodologia de geolocalização da Parte 1: haversine × fator de desvio ÷ velocidade
    (api/service.py: DETOUR, SPEED_SHORT, SPEED_LONG, SERVICE_MIN). São PREMISSAS não verificadas — NÃO são distância/tempo viários reais."""
    algorithm_version: str = "routing-1.0.0"
    detour: float = field(default_factory=lambda: _f("ROUTE_DETOUR", 1.35))
    speed_short_kmh: float = field(default_factory=lambda: _f("ROUTE_SPEED_SHORT_KMH", 22.0))
    speed_long_kmh: float = field(default_factory=lambda: _f("ROUTE_SPEED_LONG_KMH", 55.0))
    short_threshold_km: float = 15.0          # distância em linha reta até a qual vale a velocidade curta (igual à Parte 1)
    unload_min: int = field(default_factory=lambda: _i("ROUTE_SERVICE_MIN", 30))   # descarga na ONG (Parte 1: SERVICE_MIN = 30)
    safety_margin_h: float = field(default_factory=lambda: _f("ROUTE_SAFETY_MARGIN_H", 2.0))  # entrega limite = validade − margem
    horizon_h: float = field(default_factory=lambda: _f("ROUTE_HORIZON_H", 12.0))             # duração máxima de uma viagem
    solver_time_limit_s: int = field(default_factory=lambda: _i("ROUTE_SOLVER_TIME_LIMIT_S", 3))
    max_stops: int = field(default_factory=lambda: _i("ROUTE_MAX_STOPS", 12))


ROUTE = RouteSettings()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida (ver .env.example). Nenhuma credencial é embutida no código.")
    return url
