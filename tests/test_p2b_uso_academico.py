"""Decisão da equipe (outubro/2026): dados públicos em USO ACADÊMICO, licença NÃO CONFIRMADA (NEEDS_REVIEW), sem redistribuição de bases brutas e aviso visível."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRASE = "dados públicos usados para fins acadêmicos; licença de reutilização não confirmada"


def test_interface_mostra_aviso_academico_sem_token():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    textos = " ".join(c.value for c in at.caption).lower()
    assert FRASE in textos


def test_nenhum_endpoint_de_exportacao_ou_download_de_bases(client):
    paths = client.get("/openapi.json").json()["paths"]
    proibidos = [p for p in paths if any(t in p.lower() for t in ("export", "download", "/raw", "dump"))]
    assert not proibidos, proibidos


def test_dados_brutos_fora_do_repositorio_e_das_imagens():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/" in gi and "data/simulated/" in gi
    di = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert "data" in di
    for df in ("Dockerfile.api", "Dockerfile.frontend"):
        txt = (ROOT / "docker" / df).read_text(encoding="utf-8")
        assert "COPY data" not in txt and "data/raw" not in txt


def test_licencas_continuam_nao_confirmadas(p2_db):
    from sqlalchemy import select
    from database import models as m
    from database.session import session_scope
    with session_scope() as s:
        rows = s.execute(select(m.PublicDataSource.id, m.PublicDataSource.publication_cleared, m.PublicDataSource.review_status)).all()
    assert rows
    assert all(r[1] is False for r in rows), "nenhuma fonte pode estar liberada para publicação"
    status = {r[0]: r[2] for r in rows}
    # dados públicos já processados (ONGs, municípios, população/indicadores, coordenadas): licença NÃO confirmada. (As fontes PAA têm referência verificada na Fase 1 e não são redistribuídas.)
    for sid in ("ipea_osc_area", "rbba_resumo", "ibge_municipios", "ibge_populacao", "ibge_coords"):
        assert status[sid] == "NEEDS_REVIEW", (sid, status[sid])
