import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_raw_inalterado_confere_checksums():
    if not (ROOT / "data" / "raw").exists():
        pytest.skip("data/raw não está no repositório (licenças não confirmadas: sem redistribuição das bases brutas); a verificação roda onde o RAW existe")
    base = json.loads((ROOT / "data/metadata/raw_checksums.json").read_text(encoding="utf-8"))
    for rel, info in base.items():
        p = ROOT / rel
        assert p.exists(), rel
        assert hashlib.sha256(p.read_bytes()).hexdigest() == info["sha256"], f"RAW alterado: {rel}"


def test_manifesto_tem_campos_de_rastreabilidade():
    m = json.loads((ROOT / "data/metadata/ingestion_manifest.json").read_text(encoding="utf-8"))
    assert m["pipeline_version"] and m["sources"]
    for sid, s in m["sources"].items():
        txt = json.dumps(s)
        for k in ("sha256", "bytes"):
            assert k in txt, (sid, k)


def test_camadas_existem_e_nao_vazias():
    for f in ("bronze/ibge_municipios", "bronze/ipea_osc", "bronze/rbba_pontos", "silver/osc", "silver/rbba", "silver/municipios", "gold/organizations", "gold/territory"):
        assert len(pd.read_parquet(ROOT / "data" / f"{f}.parquet")) > 0, f
