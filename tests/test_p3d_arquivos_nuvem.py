"""Fase 3 Parte 2 · Etapa B — arquivos de nuvem (render.yaml, Dockerfiles, docs, .env.example) sem segredos e coerentes. Sem banco, sem Docker."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
txt = lambda p: (ROOT / p).read_text(encoding="utf-8")  # noqa: E731
PADROES_SEGREDO = [r"postgres(ql)?(\+\w+)?://[^\s:@/]+:[^\s@<>\[\]]+@", r"rai_[A-Za-z0-9_\-]{16,}", r"eyJ[A-Za-z0-9_\-]{20,}", r"sb_(secret|publishable)_\w+", r"AKIA[0-9A-Z]{16}"]


def test_render_yaml_dois_servicos_docker_gratuitos_sem_segredos():
    d = yaml.safe_load(txt("render.yaml"))
    sv = {s["name"]: s for s in d["services"]}
    assert set(sv) == {"rede-alimenta-api", "rede-alimenta-frontend"}
    for s in sv.values():
        assert s["type"] == "web" and s["runtime"] == "docker" and s["plan"] == "free" and (ROOT / s["dockerfilePath"]).is_file()
    api, fe = sv["rede-alimenta-api"], sv["rede-alimenta-frontend"]
    assert api["healthCheckPath"] == "/ready" and api["autoDeployTrigger"] == "checksPass"
    env = {e["key"]: e for e in api["envVars"]}
    assert env["APP_ENV"]["value"] == "production"
    for chave in ("DATABASE_URL", "CORS_ALLOW_ORIGINS"):
        assert env[chave].get("sync") is False and "value" not in env[chave]  # segredo/pendente: sem valor no arquivo
    febe = {e["key"]: e for e in fe["envVars"]}
    assert febe["API_BASE_URL"].get("sync") is False and "value" not in febe["API_BASE_URL"]
    assert not any(re.search(p, txt("render.yaml")) for p in PADROES_SEGREDO)


def test_dockerfiles_usam_port_em_forma_shell_e_sem_pip():
    api, fe = txt("docker/Dockerfile.api"), txt("docker/Dockerfile.frontend")
    assert '"--port ${PORT:-8000}"' not in api and "${PORT:-8000}" in api and 'CMD ["sh", "-c", "exec uvicorn' in api
    assert "${PORT:-8501}" in fe and 'CMD ["sh", "-c", "exec streamlit' in fe
    for f in (api, fe):
        assert "HEALTHCHECK" in f and "os.environ.get('PORT'" in f
        runtime = f.split("AS runtime", 1)[1]
        assert "pip install" not in runtime  # pip só no estágio builder


def test_compose_e_ci_continuam_coerentes():
    c = txt("docker-compose.yml")
    assert "APP_ENV: ${APP_ENV:-development}" in c and "API_BASE_URL: http://api:8000" in c
    assert (ROOT / ".github/workflows/ci.yml").is_file()


def test_docs_de_nuvem_existem_e_sem_credenciais():
    for p in ("docs/DEPLOY.md", "docs/LICENCAS_DEMONSTRACAO.md", "README.md", "docs/PITCH.md", ".env.example", "security/STRIDE.md", "render.yaml"):
        for pad in PADROES_SEGREDO:
            assert not re.search(pad, txt(p)), (p, pad)
    deploy = txt("docs/DEPLOY.md")
    ordem = [deploy.index(f"## Passo {i}") for i in range(1, 10)]
    assert ordem == sorted(ordem)
    for termo in ("Resume project", "sslmode=require", "5432", "6543", "--confirm-cloud", "smoke_cloud", "--revoke", "O que fazer se der erro", "pendente de provisionamento", "Read-Host"):
        assert termo.lower() in deploy.lower(), termo


def test_licencas_demonstracao_cobre_datasets_e_nao_inventa_licenca():
    t = txt("docs/LICENCAS_DEMONSTRACAO.md")
    for termo in ("IPEA", "RBBA", "IBGE", "PAA", "SIMULADO", "não confirmada", "acadêmico", "apresentação", "Apagar o banco em nuvem"):
        assert termo.lower() in t.lower(), termo
    assert "Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais" in t and "Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais" in txt("README.md")


def test_env_example_sem_valores_nas_novas_variaveis():
    linhas = [ln for ln in txt(".env.example").splitlines() if ln.startswith("# ") and "=" in ln and ("SMOKE_" in ln or "CORS_ALLOW" in ln)]
    assert linhas and not any(re.search(r"(TOKEN|DATABASE_URL)=\S", ln) for ln in linhas)
