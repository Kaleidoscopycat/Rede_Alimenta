"""Exporta o contrato OpenAPI gerado pela aplicação para `docs/openapi.json` (sem subir servidor, sem banco e sem nuvem).

Em produção (`APP_ENV=production`) `/docs`, `/redoc` e `/openapi.json` ficam desligados; este arquivo versionado é o contrato público da API.
Uso:
  python -m scripts.export_openapi            # grava docs/openapi.json
  python -m scripts.export_openapi --check    # só confere: código de saída 1 se docs/openapi.json estiver diferente do gerado (usado também por tests/test_p4a_openapi.py)
O contrato não contém token, segredo nem dado real: os exemplos são genéricos (api/openapi_docs.py).
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Portabilidade: permite `python scripts/export_openapi.py` de qualquer pasta, sem PYTHONPATH (a raiz do projeto entra em sys.path uma única vez).
_ROOT = str(_Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import argparse
import json

DESTINO = _Path(_ROOT) / "docs" / "openapi.json"


def gerar() -> dict:
    """Contrato gerado pela aplicação (normalizado por ida e volta em JSON, como será gravado)."""
    from api.main import app
    return json.loads(json.dumps(app.openapi(), ensure_ascii=False))


def serializar(contrato: dict) -> str:
    return json.dumps(contrato, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="não grava; falha se docs/openapi.json estiver desatualizado")
    a = ap.parse_args()
    atual = gerar()
    if a.check:
        if not DESTINO.exists() or json.loads(DESTINO.read_text(encoding="utf-8")) != atual:
            print("docs/openapi.json está desatualizado: rode `python -m scripts.export_openapi`")
            return 1
        print("docs/openapi.json confere com a aplicação")
        return 0
    DESTINO.write_text(serializar(atual), encoding="utf-8", newline="\n")
    print(f"gravado {DESTINO.relative_to(_ROOT)}: {len(atual['paths'])} caminhos, {len(atual['components']['schemas'])} modelos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
