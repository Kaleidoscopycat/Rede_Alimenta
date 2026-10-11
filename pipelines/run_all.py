"""Executa a ingestão completa: [download opcional] -> raw verify -> bronze -> silver -> gold.
Uso: python -m pipelines.run_all [--refresh]"""
from __future__ import annotations

import sys
import time

from . import gold
from .common import get_logger
from .download import verify_and_fetch
from .ibge import pipeline as ibge
from .organizations import pipeline as orgs
from .paa_mds import pipeline as paa

log = get_logger("run_all")


def main(refresh: bool = False) -> dict:
    t = time.time()
    verify_and_fetch(refresh=refresh)
    out = {"ibge": ibge.run(), "organizations": orgs.run(), "paa": paa.run(), "gold": gold.run()}
    log.info("pipeline completo em %.0fs: %s", time.time() - t, out)
    return out


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
