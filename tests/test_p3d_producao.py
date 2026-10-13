"""Fase 3 Parte 2 · Etapa B — endurecimento de produção, carga em nuvem, smoke e aviso acadêmico. Sem banco (exceto onde indicado); nenhuma credencial real."""
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from core.hardening import AuthFailureLimiter, client_ip, cors_origins

ROOT = Path(__file__).resolve().parents[1]
SEGREDO = "senha-somente-de-teste-123"


def _py(code: str, **env) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "DATABASE_URL", "CORS_ALLOW_ORIGINS", "TRUST_PROXY_HEADERS")}
    e.update(env)
    return subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n%s" % (str(ROOT), code)], cwd=ROOT, env=e, capture_output=True, text=True, timeout=120)


# ------------------------------------------------------------------------------------------- limitador
def test_limitador_bloqueia_e_libera_pela_janela():
    lim = AuthFailureLimiter(max_failures=3, window_s=60)
    for t in (0, 1, 2):
        assert lim.blocked("1.1.1.1", now=t) == 0
        lim.fail("1.1.1.1", now=t)
    assert lim.blocked("1.1.1.1", now=3) > 0 and lim.blocked("2.2.2.2", now=3) == 0
    assert lim.blocked("1.1.1.1", now=62) == 0  # janela esvaziou


def test_limitador_memoria_limitada():
    lim = AuthFailureLimiter(max_failures=2, window_s=60, max_keys=10)
    for i in range(100):
        lim.fail(f"10.0.0.{i}", now=1)
    assert len(lim._hits) <= 10


def test_ip_so_confia_no_proxy_quando_configurado(monkeypatch):
    class R:
        headers = {"x-forwarded-for": "6.6.6.6, 9.9.9.9"}
        client = type("C", (), {"host": "10.1.1.1"})()
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    assert client_ip(R()) == "10.1.1.1"
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    assert client_ip(R()) == "9.9.9.9"  # último hop (o do proxy confiável), nunca o primeiro (forjável)


def test_cors_sem_curinga(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.exemplo.com/, *, ,https://b.exemplo.com")
    assert cors_origins() == ["https://app.exemplo.com", "https://b.exemplo.com"]
    monkeypatch.delenv("CORS_ALLOW_ORIGINS")
    assert cors_origins() == []


# ------------------------------------------------------------------------------------------- production
def test_production_desliga_docs_e_poe_cabecalhos():
    r = _py("""
from fastapi.testclient import TestClient
from api.main import app
c = TestClient(app)
print('R:', [c.get(p).status_code for p in ('/docs','/redoc','/openapi.json')])
h = c.get('/health').headers
print('R:', h['x-content-type-options'], h['x-frame-options'], 'strict-transport-security' in h, 'content-security-policy' in h)
o = c.options('/api/v1/me', headers={'Origin':'https://mal.exemplo.com','Access-Control-Request-Method':'GET'})
print('R:', 'access-control-allow-origin' in o.headers)
""", APP_ENV="production", DATABASE_URL="postgresql://u:p@localhost/x", CORS_ALLOW_ORIGINS="https://app.exemplo.com")
    assert r.returncode == 0, r.stderr[-800:]
    l1, l2, l3 = [x[3:] for x in r.stdout.splitlines() if x.startswith('R: ')]
    assert l1 == "[404, 404, 404]" and l2 == "nosniff DENY True True" and l3 == "False"


def test_development_mantem_docs():
    r = _py("""
from fastapi.testclient import TestClient
from api.main import app
print('R:', TestClient(app).get('/docs').status_code)
""", APP_ENV="development", DATABASE_URL="postgresql://u:p@localhost/x")
    assert r.returncode == 0 and "R: 200" in r.stdout


@pytest.mark.parametrize("url,ok", [
    ("postgresql://u:p@localhost:5432/x", True), ("postgresql://u:p@postgres:5432/x", True),
    ("postgresql://u:p@db.exemplo.com:5432/x", False), ("postgresql://u:p@db.exemplo.com:5432/x?sslmode=disable", False),
    ("postgresql://u:p@db.exemplo.com:5432/x?sslmode=require", True), ("postgresql://u:p@db.exemplo.com/x?sslmode=verify-full", True),
])
def test_production_exige_ssl_em_banco_remoto(url, ok):
    r = _py("from core.settings import database_url\nprint(database_url() == %r)" % url, APP_ENV="production", DATABASE_URL=url)
    assert (r.returncode == 0) is ok
    assert "u:p@" not in r.stdout + r.stderr  # a URL não vaza em erro algum


# ------------------------------------------------------------------------------------------- ApiClient: cold start
def test_apiclient_tenta_de_novo_em_get(monkeypatch):
    from app.api_client import ApiClient
    monkeypatch.setattr("app.api_client.time.sleep", lambda s: None)
    n = {"c": 0}
    esperas = []

    def handler(req):
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, json={"role": "ADMIN"})
    c = ApiClient("http://api", "tok", http=httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler)), wake_max_s=60, on_wait=esperas.append)
    assert c.me() == {"role": "ADMIN"} and n["c"] == 3 and len(esperas) == 2


def test_apiclient_nao_repete_post_nem_quando_desligado(monkeypatch):
    from app.api_client import ApiClient, ApiError
    monkeypatch.setattr("app.api_client.time.sleep", lambda s: None)
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(503, json={"detail": "x"})
    c = ApiClient("http://api", "tok", http=httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler)), wake_max_s=60)
    with pytest.raises(ApiError):
        c.create_draft()
    assert n["c"] == 1
    n["c"] = 0
    c2 = ApiClient("http://api", "tok", http=httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler)), wake_max_s=0)
    with pytest.raises(ApiError):
        c2.me()
    assert n["c"] == 1


def test_apiclient_desiste_ao_estourar_o_limite(monkeypatch):
    from app.api_client import ApiClient, ApiError
    monkeypatch.setattr("app.api_client.time.sleep", lambda s: None)
    t = {"v": 0.0}
    monkeypatch.setattr("app.api_client.time.monotonic", lambda: t.__setitem__("v", t["v"] + 5) or t["v"])
    c = ApiClient("http://api", "tok", http=httpx.Client(base_url="http://api", transport=httpx.MockTransport(lambda r: httpx.Response(503, json={"detail": "x"}))), wake_max_s=20)
    with pytest.raises(ApiError):
        c.me()


# ------------------------------------------------------------------------------------------- load_to_cloud
def test_mask_e_redact():
    from scripts.load_to_cloud import mask_host, redact
    assert mask_host("aws-0-sa-east-1.pooler.supabase.com") == "aws***.com" and mask_host("localhost") == "localhost"
    url = f"postgresql://postgres.abc:{SEGREDO}@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    out = redact(f"falha em {url} usuario postgres.abc senha {SEGREDO} host aws-0-sa-east-1.pooler.supabase.com", url)
    for pedaco in (SEGREDO, "postgres.abc", "pooler.supabase.com"):
        assert pedaco not in out


def test_load_to_cloud_estimate_nao_usa_banco():
    r = _py("import sys; sys.argv=['x','--estimate','--sim-tag','smoke']\nfrom scripts.load_to_cloud import main\nmain()")
    assert r.returncode == 0, r.stderr[-500:]
    est = json.loads(r.stdout[r.stdout.index("{"):])["estimativa"]
    assert est["cabe_no_plano_gratuito"] is True and est["tamanho_estimado_mb"] > 0


def test_load_to_cloud_sem_confirmacao_nao_escreve_e_nao_imprime_segredo():
    url = f"postgresql://postgres.abc:{SEGREDO}@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
    r = _py("import sys; sys.argv=['x','--sim-tag','smoke']\nfrom scripts.load_to_cloud import main\nmain()", DATABASE_URL=url)
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "PLANO (nada foi carregado)" in out and "--confirm-cloud" in out
    assert SEGREDO not in out and "postgres.abc" not in out and "pooler.supabase.com" not in out and "aws***.com" in out


def test_load_to_cloud_recusa_remoto_sem_ssl():
    url = f"postgresql://u:{SEGREDO}@db.exemplo.com:5432/postgres"
    r = _py("import sys; sys.argv=['x','--confirm-cloud']\nfrom scripts.load_to_cloud import main\nmain()", DATABASE_URL=url)
    assert r.returncode == 2 and "sslmode=require" in r.stdout and SEGREDO not in r.stdout + r.stderr


def test_load_to_cloud_sem_database_url():
    r = _py("import sys; sys.argv=['x','--confirm-cloud']\nfrom scripts.load_to_cloud import main\nmain()")
    assert r.returncode == 2 and "DATABASE_URL" in r.stdout


# ------------------------------------------------------------------------------------------- smoke_cloud
def _fake(respostas):
    def get(url, token=None, timeout=0):
        for sufixo, resp in respostas.items():
            if url.endswith(sufixo):
                return resp
        return 404, ""
    return get


def test_smoke_tudo_certo_e_somente_get():
    from scripts import smoke_cloud as sc
    get = _fake({"/health": (200, "{}"), "/ready": (200, "{}"), "/_stcore/health": (200, "ok"), "/stats/overview": (401, ""), "/stats/security": (403, "")})
    rep = sc.run("https://api.x.com", "https://web.x.com", False, env={}, get=get)
    assert rep.falhas == 0 and any(e == "PULADO" for e, _, _ in rep.linhas)


def test_smoke_banco_pausado_mostra_mensagem():
    from scripts import smoke_cloud as sc
    rep = sc.run("https://api.x.com", None, False, env={}, get=_fake({"/health": (200, ""), "/ready": (503, "")}))
    assert rep.falhas >= 1 and any(sc.PAUSED_MSG in d for _, _, d in rep.linhas)


def test_smoke_docs_habilitado_e_admin_aberto_sao_falhas():
    from scripts import smoke_cloud as sc
    get = _fake({"/health": (200, ""), "/ready": (200, ""), "/docs": (200, ""), "/stats/overview": (200, "{}"), "/stats/security": (401, "")})
    rep = sc.run("https://api.x.com", None, False, env={}, get=get)
    falhas = [n for e, n, _ in rep.linhas if e == "FALHA"]
    assert any("/docs" in n for n in falhas) and any("overview" in n for n in falhas)


def test_smoke_detecta_campo_de_ia_para_doador_sem_imprimir_token():
    from scripts import smoke_cloud as sc
    tok = "rai_token_somente_de_teste"
    vistos = []

    def get(url, token=None, timeout=0):
        vistos.append(token)
        if url.endswith("/api/v1/matches") and token:
            return 200, json.dumps([{"id": 1, "ranking": [{"final_score": 0.9}]}])
        return (200, "{}") if token or url.endswith(("/health", "/ready")) else (404, "")
    rep = sc.run("https://api.x.com", None, False, env={"SMOKE_DONOR_TOKEN": tok}, get=get)
    assert any(e == "FALHA" and "DONOR" in n for e, n, _ in rep.linhas)
    assert tok not in json.dumps(rep.linhas)


def test_smoke_acordar_repete_com_espera_crescente():
    from scripts import smoke_cloud as sc
    estados = {"n": 0}
    esperas = []

    def get(url):
        estados["n"] += 1
        return (200 if estados["n"] > 5 else 503), ""
    assert sc.acordar("https://api.x.com", get=get, sleep=esperas.append) is True
    assert esperas == sorted(esperas) and esperas[0] == 2.0 and esperas[1] > esperas[0]


def test_smoke_exige_https():
    from scripts import smoke_cloud as sc
    with pytest.raises(SystemExit):
        sc._check_url("http://api.exemplo.com")
    assert sc._check_url("http://localhost:8000/") == "http://localhost:8000"


# ------------------------------------------------------------------------------------------- aviso acadêmico
def test_aviso_academico_no_componente_comum():
    from app.ui_common import AVISO_ACADEMICO
    assert AVISO_ACADEMICO == "Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais"


def test_aviso_academico_aparece_sem_token_e_nos_tres_perfis(monkeypatch, client, world):
    from streamlit.testing.v1 import AppTest
    from app.ui_common import AVISO_ACADEMICO
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    for chave in (None, "donor_a", "admin"):
        at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=90)
        at.run()
        if chave:
            at.sidebar.text_input[0].set_value(world[chave]["Authorization"].split(" ", 1)[1])
            at.run()
        assert not at.exception
        assert any(AVISO_ACADEMICO in str(e.value) for e in at.markdown), chave


def test_database_url_normaliza_esquema_dos_paineis():
    r = _py("from core.settings import database_url\nfrom sqlalchemy.engine import make_url\nprint('R:', make_url(database_url()).drivername)", DATABASE_URL="postgres://u:p@localhost/x")
    assert "R: postgresql+psycopg" in r.stdout
    r = _py("from core.settings import database_url\nprint('R:', database_url().split('://')[0])", DATABASE_URL="postgresql+psycopg://u:p@localhost/x")
    assert "R: postgresql+psycopg" in r.stdout
