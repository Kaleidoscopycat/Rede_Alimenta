"""Base geográfica: haversine documentada e testável, location_precision e geo_quality.

Haversine: distância ortodrômica (círculo máximo) entre dois pontos numa esfera de raio
6371,0088 km (raio médio da Terra, IUGG). É distância em LINHA RETA; NÃO é distância viária.
Coordenada ausente (NaN/None) => resultado NaN (organização NÃO ranqueável por distância,
de forma explícita; nunca é tratada como 0 km).
"""
from __future__ import annotations

import math

import numpy as np

EARTH_RADIUS_KM = 6371.0088
BRAZIL_LAT = (-34.0, 6.0)
BRAZIL_LON = (-74.0, -32.0)
GEO_OK_KM = 25.0          # escolha metodológica (DATA_DICTIONARY Parte C), não dado de fonte
GEO_SUSPEITA_KM = 100.0   # idem


def haversine_km(lat1, lon1, lat2, lon2):
    """Distância em linha reta (km). Aceita escalares ou arrays (broadcast numpy). NaN se faltar coordenada."""
    lat1, lon1, lat2, lon2 = (np.asarray(x, dtype="float64") for x in (lat1, lon1, lat2, lon2))
    p = np.pi / 180.0
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    d = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return float(d) if d.ndim == 0 else d


def in_brazil(lat, lon) -> bool:
    return (lat is not None and lon is not None and not (math.isnan(lat) or math.isnan(lon))
            and BRAZIL_LAT[0] <= lat <= BRAZIL_LAT[1] and BRAZIL_LON[0] <= lon <= BRAZIL_LON[1])


def geo_quality_from_distance(d_km: float) -> str:
    """OK <= 25 km | REVISAR 25-100 km | SUSPEITA > 100 km do centroide do município (ponto RBBA)."""
    if d_km is None or (isinstance(d_km, float) and math.isnan(d_km)):
        return "NAO_APLICAVEL"
    if d_km > GEO_SUSPEITA_KM:
        return "SUSPEITA"
    return "REVISAR" if d_km > GEO_OK_KM else "OK"


def location_precision(has_own_point: bool, geo_quality: str, has_municipality: bool) -> str:
    """EXACT (ponto da própria fonte e geo_quality != SUSPEITA) | MUNICIPALITY_CENTROID | NONE."""
    if has_own_point and geo_quality != "SUSPEITA":
        return "EXACT"
    return "MUNICIPALITY_CENTROID" if has_municipality else "NONE"


def estimated_travel_hours(dist_km, detour: float, speed_kmh, service_min: float):
    """Tempo estimado = dist_reta * desvio / velocidade + serviço. ESTIMATIVA (premissas), não rota."""
    dist_km = np.asarray(dist_km, dtype="float64")
    return dist_km * detour / np.asarray(speed_kmh, dtype="float64") + service_min / 60.0
