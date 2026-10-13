"""Configuração por variáveis de ambiente (sem segredos no código). Premissas do motor de match são PREMISSAS DO PROJETO, não verificadas."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Sao_Paulo"))

# Ambiente de execução: development (padrão; logs legíveis) | production (logs em JSON; endurecimentos da Etapa B). Valor inválido ⇒ erro explícito (nunca cai em silêncio para "production").
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
if APP_ENV not in ("development", "production"):
    raise RuntimeError("APP_ENV deve ser 'development' ou 'production'")
IS_PRODUCTION = APP_ENV == "production"


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


@dataclass(frozen=True)
class DonationSettings:
    """Doação com vários itens (Fase 3 Parte 1). Todos os valores são PREMISSAS do projeto, configuráveis por ambiente; nenhum tem fonte externa."""
    max_items: int = field(default_factory=lambda: _i("DONATION_MAX_ITEMS", 30))  # limite de itens por doação
    # Se (validade mais distante − validade mais próxima) ultrapassar este número de dias, o doador é avisado de que a validade mais próxima define o prazo de todo o lote.
    validity_spread_warn_days: int = field(default_factory=lambda: _i("DONATION_VALIDITY_SPREAD_WARN_DAYS", 60))
    # Conversão volume → massa quando a categoria não tem massa por litro na taxonomia (premissa sem fonte: densidade ≈ 1 kg/L).
    default_density_kg_per_l: float = field(default_factory=lambda: _f("DONATION_DEFAULT_DENSITY_KG_L", 1.0))
    max_total_kg: float = field(default_factory=lambda: _f("DONATION_MAX_TOTAL_KG", 100000.0))  # mesmo teto de quantidade_kg da API (100 000 kg)


DONATION = DonationSettings()


@dataclass(frozen=True)
class ProjectAssumptions:
    """PREMISSAS DA EQUIPE exibidas no dashboard e na documentação. Não são dados de fonte pública."""
    # refeições = kg ÷ kg_per_meal. Valor definido pela equipe (0,4 kg por refeição); configurável por ambiente, nunca fixo no código das telas.
    kg_per_meal: float = field(default_factory=lambda: _f("MEAL_KG_PER_MEAL", 0.4))

    def __post_init__(self) -> None:
        if not self.kg_per_meal > 0:
            raise RuntimeError("MEAL_KG_PER_MEAL deve ser maior que zero")

    def kg_to_meals(self, kg: float | None) -> float | None:
        return None if kg is None else kg / self.kg_per_meal


ASSUMPTIONS = ProjectAssumptions()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida (ver .env.example). Nenhuma credencial é embutida no código.")
    if IS_PRODUCTION:
        exigir_ssl_se_remoto(url)
    # painéis (Supabase, Render) entregam `postgresql://` ou `postgres://`; o driver instalado é o psycopg 3
    for velho in ("postgres://", "postgresql://"):
        if url.startswith(velho):
            return "postgresql+psycopg://" + url[len(velho):]
    return url


def exigir_ssl_se_remoto(url: str) -> None:
    """Em production, banco que não é local/Compose exige TLS (`sslmode=require` ou mais forte na URL). A URL nunca é impressa."""
    from urllib.parse import parse_qs, urlsplit
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "postgres", ""):
        return
    mode = (parse_qs(p.query).get("sslmode") or [""])[0].lower()
    if mode not in ("require", "verify-ca", "verify-full"):
        raise RuntimeError("em production, DATABASE_URL de banco remoto exige SSL: acrescente ?sslmode=require (a URL não é exibida por segurança)")
