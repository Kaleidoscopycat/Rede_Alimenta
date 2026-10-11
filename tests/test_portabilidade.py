"""Portabilidade (Fase 2 Parte 2, item 0): os pontos de entrada importam a partir de QUALQUER diretório, sem PYTHONPATH e sem `python -m`.
Reproduz o defeito do Windows: `streamlit run app/streamlit_app.py` punha só `app/` em sys.path e `from app.api_client import ...` falhava."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _env_limpo() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/x")  # nada conecta no import
    return env


def test_streamlit_app_importa_fora_da_raiz_sem_pythonpath(tmp_path):
    """Executa o script como o Streamlit faz (pasta do script em sys.path[0]), com cwd diferente da raiz e sem PYTHONPATH."""
    codigo = (
        "import runpy, sys\n"
        f"script = r'{ROOT / 'app' / 'streamlit_app.py'}'\n"
        "sys.path[0] = str(__import__('pathlib').Path(script).parent)\n"  # emula `streamlit run app/streamlit_app.py`
        "ns = runpy.run_path(script, run_name='__not_main__')\n"
        "assert 'ApiClient' in ns, 'a interface não carregou o cliente da API'\n"
        "print('ok', ns['_ROOT'] in sys.path, sys.path.count(ns['_ROOT']))\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path, env=_env_limpo(), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "ModuleNotFoundError" not in r.stderr
    assert r.stdout.strip().endswith("ok True 1"), r.stdout  # raiz presente, sem duplicar


@pytest.mark.parametrize("script", ["create_user.py", "bootstrap_db.py", "measure_latency.py", "e2e_flow.py"])
def test_scripts_importam_fora_da_raiz(tmp_path, script):
    """`python scripts/x.py` de outra pasta: a raiz entra em sys.path (verificado pelo import, sem executar a lógica)."""
    codigo = (
        "import ast, pathlib, sys\n"
        f"p = pathlib.Path(r'{ROOT / 'scripts' / script}')\n"
        "sys.path[0] = str(p.parent)\n"
        "src = p.read_text(encoding='utf-8')\n"
        "tree = ast.parse(src)\n"
        "# executa só os imports e o preâmbulo de sys.path (até a 1ª definição), não a lógica do script\n"
        "corte = next(i for i, n in enumerate(tree.body) if isinstance(n, (ast.FunctionDef, ast.ClassDef)))\n"
        "exec(compile(ast.Module(body=tree.body[:corte], type_ignores=[]), str(p), 'exec'), {'__file__': str(p), '__name__': 'x'})\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path, env=_env_limpo(), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip().endswith("ok")


def test_nao_duplica_entrada_em_sys_path():
    codigo = (
        "import sys, runpy\n"
        f"r = r'{ROOT}'\n"
        "sys.path.insert(0, r)\n"  # raiz já presente (ex.: pytest/conftest)
        f"runpy.run_path(r'{ROOT / 'app' / 'streamlit_app.py'}', run_name='__not_main__')\n"
        "print(sys.path.count(r))\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=ROOT.parent, env=_env_limpo(), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip().endswith("1")


def test_pagina_streamlit_renderiza_fora_da_raiz_sem_pythonpath(tmp_path):
    """Executa a página inteira com o executor oficial do Streamlit (AppTest) em outro diretório, sem PYTHONPATH."""
    codigo = (
        "from streamlit.testing.v1 import AppTest\n"
        f"at = AppTest.from_file(r'{ROOT / 'app' / 'streamlit_app.py'}', default_timeout=60).run()\n"
        "assert not at.exception, [e.value for e in at.exception]\n"
        "print('ok', len(at.warning) + len(at.caption) + len(at.title))\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path, env=_env_limpo(), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "ok" in r.stdout
