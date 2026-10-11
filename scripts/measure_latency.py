"""Mede a latência do ranking (motor, sem HTTP) sobre N doações de FORMA fixa em localizações de doadores SIMULADOS (seed fixa). Resultado: docs/LATENCIA_MATCH_FASE2P1.json.
É medida de ambiente local (PostgreSQL embutido, 1 processo): NÃO representa produção. Uso: python -m scripts.measure_latency [N]"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
from sqlalchemy import select

from api.state import AppState
from core.settings import TZ
from database import models as m
from database.session import session_scope
from match.eligibility import DonationCtx

ROOT = Path(__file__).resolve().parents[1]


def main(n: int = 200) -> None:
    st = AppState()
    st.load()
    assert st.engine is not None, st.error
    rng = np.random.default_rng(20261008)
    with session_scope() as s:
        rows = s.execute(select(m.DonorLocation.lat, m.DonorLocation.lon, m.DonorLocation.location_precision, m.Donor.municipio_ibge).join(m.Donor, m.Donor.id == m.DonorLocation.donor_id)
                         .where(m.Donor.data_origin == "SIMULATED", m.DonorLocation.lat.is_not(None))).all()
    idx = rng.choice(len(rows), size=min(n, len(rows)), replace=False)
    now = dt.datetime(2026, 10, 13, 13, 0, tzinfo=dt.timezone.utc)  # terça 10:00 em São Paulo (referência fixa)
    st.engine.rank(DonationCtx("FRUTAS", 50, 96, False, 31, 8, 17, 30, rows[0][0], rows[0][1], rows[0][3], rows[0][2], False, "SIMULATED"), now)  # aquecimento
    tot, ml, el, n_el = [], [], [], []
    for i in idx:
        lat, lon, prec, mun = rows[i]
        ctx = DonationCtx("FRUTAS", 50.0, 96.0, False, 31, 8.0, 17.0, 30.0, lat, lon, mun, prec, False, "SIMULATED")
        t = time.perf_counter()
        r = st.engine.rank(ctx, now)
        tot.append((time.perf_counter() - t) * 1000)
        ml.append(r["latency_ms"].get("ml_ms", 0.0)); el.append(r["latency_ms"].get("elegibilidade_ms", 0.0)); n_el.append(r["eligibility"]["n_eligible"])
    q = lambda a, p: round(float(np.percentile(a, p)), 2)  # noqa
    out = {"n_rankings": len(tot), "ms_total": {"p50": q(tot, 50), "p95": q(tot, 95), "max": round(max(tot), 2)}, "ms_ml": {"p50": q(ml, 50), "p95": q(ml, 95)},
           "ms_elegibilidade": {"p50": q(el, 50), "p95": q(el, 95)}, "elegiveis_mediana": int(np.median(n_el)), "n_orgs_indexadas": int(len(st.index.orgs)),
           "ambiente": "sandbox local (PostgreSQL embutido, índice em memória, 1 processo, sem rede); medida de ENGENHARIA, não de produção", "origem_dos_dados": "doadores SIMULATED; ONGs reais com perfil declarado SIMULATED",
           "forma_da_doacao": "FRUTAS 50 kg, 96 h de validade, sem refrigeração, janela 08–17 h seg–sex"}
    (ROOT / "docs" / "LATENCIA_MATCH_FASE2P1.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
