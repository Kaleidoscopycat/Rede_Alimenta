"""Cria o esquema (Alembic) e importa dados REAIS (gold) + SIMULADOS (opcional). Uso: python -m scripts.bootstrap_db [--sim-tag main] [--no-sim] [--no-lots]
Requer DATABASE_URL no ambiente. Gera docs/data/IMPORT_REPORT_FASE2P1.json com contagens por origem."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Portabilidade: permite `python scripts/x.py` de qualquer pasta, sem PYTHONPATH (a raiz do projeto entra em sys.path uma única vez).
_ROOT = str(_Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import argparse
import json
import logging
# Supressão justificada em security/reports/SUPRESSOES.md (B404)
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

from sqlalchemy import text

from database.importers import import_all
from database.session import get_engine, session_scope

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def counts() -> dict:
    q = {
        "organizations(PUBLIC)": "select count(*) from organizations where data_origin='PUBLIC'",
        "organization_locations": "select count(*) from organization_locations",
        "organizations_sem_coordenada": "select count(*) from organization_locations where lat is null",
        "municipalities(PUBLIC)": "select count(*) from municipalities",
        "public_indicators(PUBLIC)": "select count(*) from public_indicators",
        "organization_profiles(SIMULATED)": "select count(*) from organization_profiles where data_origin='SIMULATED'",
        "organization_profiles(USER_ENTERED)": "select count(*) from organization_profiles where data_origin='USER_ENTERED'",
        "vehicles(SIMULATED)": "select count(*) from vehicles where data_origin='SIMULATED'",
        "vehicles(USER_ENTERED)": "select count(*) from vehicles where data_origin='USER_ENTERED'",
        "donors(SIMULATED)": "select count(*) from donors where data_origin='SIMULATED'",
        "donors(USER_ENTERED)": "select count(*) from donors where data_origin='USER_ENTERED'",
        "donations(SIMULATED)": "select count(*) from donations where data_origin='SIMULATED'",
        "donations(USER_ENTERED)": "select count(*) from donations where data_origin='USER_ENTERED'",
        "donation_items(SIMULATED)": "select count(*) from donation_items where data_origin='SIMULATED'",
        "public_data_sources": "select count(*) from public_data_sources",
        "food_categories": "select count(*) from food_categories",
    }
    with get_engine().connect() as c:
        return {k: int(c.execute(text(v)).scalar()) for k, v in q.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim-tag", default="main")
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--no-lots", action="store_true")
    ap.add_argument("--report", default=str(ROOT / "docs" / "data" / "IMPORT_REPORT_FASE2P1.json"))
    a = ap.parse_args()
    t0 = time.time()
    # Supressão justificada em security/reports/SUPRESSOES.md (B603)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)  # nosec B603
    with session_scope() as s:
        rep = import_all(s, None if a.no_sim else a.sim_tag, with_lots=not a.no_lots)
    rep["contagens_no_banco"] = counts()
    rep["segundos"] = round(time.time() - t0, 1)
    Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
