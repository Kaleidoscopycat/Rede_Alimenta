import numpy as np
from pipelines.geo import haversine_km, in_brazil, geo_quality_from_distance, estimated_travel_hours


def test_haversine_sp_rj_conhecido():
    d = float(haversine_km(-23.5505, -46.6333, -22.9068, -43.1729))
    assert 350 < d < 365  # ~357 km em linha reta


def test_haversine_zero_e_simetria():
    assert float(haversine_km(-15.8, -47.9, -15.8, -47.9)) == 0.0
    a = float(haversine_km(-10, -50, -20, -40)); b = float(haversine_km(-20, -40, -10, -50))
    assert abs(a - b) < 1e-9


def test_haversine_coordenada_ausente_gera_nan():
    d = haversine_km(np.array([np.nan, -23.5]), np.array([-46.6, -46.6]), -22.9, -43.1)
    assert np.isnan(d[0]) and not np.isnan(d[1])


def test_tempo_estimado_monotonico():
    t = estimated_travel_hours(np.array([0.0, 10.0, 100.0]), 1.35, np.array([22.0, 22.0, 55.0]), 30.0)
    assert t[0] == 0.5 and t[1] > t[0] and t[2] > t[1]
