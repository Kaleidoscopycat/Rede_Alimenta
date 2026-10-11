"""Utilitários comuns dos pipelines (caminhos, checksums, manifesto de ingestão, normalização).

Regras do AGENTS.md: RAW nunca é modificado; toda ingestão registra URL, timestamp,
checksum, versão, tamanho e quantidade de registros em data/metadata/ingestion_manifest.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW, BRONZE, SILVER, GOLD, META = (DATA / d for d in ("raw", "bronze", "silver", "gold", "metadata"))
MANIFEST_PATH = META / "ingestion_manifest.json"
BASELINE_CHECKSUMS = META / "raw_checksums.json"  # gerado na Fase 0 (referência de integridade do RAW)


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logging.getLogger(name)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def norm_text(s: Any) -> str:
    """minúsculas, sem acento, sem espaços nas pontas (chave de junção por nome)."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"pipeline_version": PIPELINE_VERSION, "sources": {}}


def register(source_id: str, /, **fields: Any) -> None:
    """Atualiza (mescla) a entrada de uma fonte no manifesto de ingestão."""
    META.mkdir(parents=True, exist_ok=True)
    m = _load_manifest()
    m["pipeline_version"] = PIPELINE_VERSION
    entry = m["sources"].setdefault(source_id, {})
    entry.update(fields)
    entry["last_updated_utc"] = now_utc()
    MANIFEST_PATH.write_text(json.dumps(m, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def register_layer(source_id: str, layer: str, path: Path, n_records: int) -> None:
    """Registra uma camada derivada (bronze/silver/gold) com checksum, tamanho e nº de registros."""
    m = _load_manifest()
    entry = m["sources"].setdefault(source_id, {})
    entry.setdefault("layers", {})[layer] = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "n_records": int(n_records),
        "built_at_utc": now_utc(),
        "pipeline_version": PIPELINE_VERSION,
    }
    META.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def trace_columns(df, source_id: str, source_name: str, source_url: str, source_dataset: str,
                  source_updated_at: str, ingested_at: str):
    """Colunas de rastreabilidade do AGENTS.md §7 (data_origin = PUBLIC)."""
    df["source_id"] = source_id
    df["source_name"] = source_name
    df["source_url"] = source_url
    df["source_dataset"] = source_dataset
    df["source_updated_at"] = source_updated_at
    df["ingested_at"] = ingested_at
    df["pipeline_version"] = PIPELINE_VERSION
    df["data_origin"] = "PUBLIC"
    return df
