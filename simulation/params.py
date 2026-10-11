"""Carregamento e sorteio dos parâmetros (params_v0.2.0.yaml). Cada run sorteia os intervalos [PREMISSA] com a seed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

SIM_DIR = Path(__file__).resolve().parent
PARAMS_FILE = SIM_DIR / "params" / "params_v0.2.0.yaml"
TAXONOMY_FILE = SIM_DIR / "config" / "taxonomy_v0.2.yaml"
GENERATOR_VERSION = "0.2.0"
SCENARIOS = {"aceitacao": ("baixa", "media", "alta"), "hortifruti": ("alto", "baixo"), "declarado": ("base", "fiel", "otimista")}


def file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _draw_range(rng: np.random.Generator, r: Any) -> Any:
    if isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(x, (int, float)) for x in r):
        return float(rng.uniform(r[0], r[1]))
    if isinstance(r, dict):
        return {k: _draw_range(rng, v) for k, v in r.items()}
    return r


class Params:
    """Acesso `P['grupo.nome']`; `drawn` guarda os valores sorteados (com tipo e fonte) para documentação."""

    def __init__(self, rng: np.random.Generator, scenario: dict[str, str] | None = None):
        self.raw = yaml.safe_load(PARAMS_FILE.read_text(encoding="utf-8"))
        self.scenario = {"aceitacao": "media", "hortifruti": "alto", "declarado": "base", **(scenario or {})}
        self.drawn: dict[str, dict] = {}
        self.values: dict[str, Any] = {}
        for g, items in self.raw.items():
            if not isinstance(items, dict):
                continue
            for name, spec in items.items():
                key = f"{g}.{name}"
                if "range" in spec:
                    rg = spec["range"]
                    if g == "declared" and self.scenario["declarado"] in spec.get("scenario_override", {}):
                        rg = spec["scenario_override"][self.scenario["declarado"]]
                    v = _draw_range(rng, rg)
                else:
                    # valores fixos; os de `RAW_VALUE_KEYS` guardam intervalos/listas que o gerador sorteia por conta própria
                    v = spec["value"]
                self.values[key] = v
                self.drawn[key] = {"value": v, "type": spec["type"], "source": spec["source"], "why": spec["why"], "range": spec.get("range")}
        self.values["_scenario"] = self.scenario
        self.taxonomy = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))

    def __getitem__(self, k: str) -> Any:
        return self.values[k]

    def params_hash(self) -> str:
        h = hashlib.sha256()
        h.update(file_sha256(PARAMS_FILE).encode())
        h.update(file_sha256(TAXONOMY_FILE).encode())
        h.update(json.dumps(self.scenario, sort_keys=True).encode())
        return h.hexdigest()

    def dump(self) -> dict:
        return {"scenario": self.scenario, "drawn": self.drawn, "params_file_sha256": file_sha256(PARAMS_FILE),
                "taxonomy_file_sha256": file_sha256(TAXONOMY_FILE)}
