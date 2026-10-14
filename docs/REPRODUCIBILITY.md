# Reprodutibilidade — Rede Alimenta IA

> Do clone ao sistema rodando. **Legenda:** *executado aqui* = rodado em 14/10/2026 no ambiente de desenvolvimento desta fase (Linux, Python 3.10.12, PostgreSQL 16.2 local, sem Docker, sem GitHub, sem nuvem); *confirmado pelo CI* = só o GitHub Actions comprova; *não verificado neste ambiente* = não foi rodado.

## 1. Passo a passo

```bash
git clone <repositório> && cd <pasta>
python -m venv .venv && source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# dados reais (rede; leva ~40 s; verifica checksums do RAW)
python -m pipelines.run_all

# dados simulados (determinísticos: mesma semente + mesmos parâmetros = mesma saída)
python -m simulation.generator --seed 20261003 --n-lots 60000 --n-donors 8000 --tag main
python -m simulation.generator --seed 20261003 --n-lots 3000 --n-donors 1000 --tag smoke    # conjunto pequeno para testes

# banco e carga
cp .env.example .env                                     # preencha localmente
scripts/pg_local.sh init && scripts/pg_local.sh start    # PostgreSQL local sem Docker
python -m scripts.bootstrap_db                           # Alembic 0001-0005 + ONGs PUBLIC + dados SIMULATED
python -m scripts.create_user --role ADMIN --label admin-local

# aplicação
uvicorn api.main:app --port 8000                         # terminal 1
streamlit run app/streamlit_app.py                       # terminal 2

# verificações
ruff check .
bandit -r api app core database match ml pipelines routing scripts simulation quality eda -x tests --severity-level medium
pip-audit -r requirements-dev.txt
python -m pytest                                         # exige TEST_DATABASE_URL (banco *_test)
python -m scripts.export_openapi --check
```

Treino (opcional; os artefatos já estão em `ml/artifacts/`): `python -m ml.training.train main` (precisa de ~6 GB de RAM) e `python -m ml.semantic.train_eval main`. Alternativa em contêineres: README, seção Docker.

## 2. O que foi executado nesta fase

| Item | Resultado | Verificação |
|---|---|---|
| Gerador com semente 20261003 (`smoke`, 3.000 lotes / 1.000 doadores) executado **duas vezes** em pastas temporárias | saídas **idênticas** (mesmo conteúdo) | executado aqui |
| Suíte completa `pytest` (5 lotes: 20 + 52 + 83 + 88 + 68) | **311 passaram, 0 falharam** (34 arquivos) | executado aqui |
| Ruff 0.17.0 | `All checks passed!` | executado aqui |
| Bandit 1.9.4 | 0 achados em 11.683 linhas; 10 `# nosec` registrados | executado aqui |
| pip-audit 2.10.1 (`-r requirements-dev.txt`) | sem vulnerabilidades conhecidas | executado aqui |
| `export_openapi --check` / `tests/test_p4a_openapi.py` | `docs/openapi.json` confere com a API | executado aqui |
| Renderização dos 8 diagramas Mermaid | 8 de 8 sem erro | executado aqui |

## 3. O que **não** foi executado

| Item | Situação |
|---|---|
| Docker build, Docker Compose, Trivy, fluxo e2e em contêineres | **confirmado pelo CI** (informado pelo responsável); não rodado aqui |
| Render, Supabase, URLs públicas, `smoke_cloud`, RLS no Supabase real | **não verificado neste ambiente** |
| Pipelines de ingestão (`pipelines.run_all`, requer rede para fontes oficiais) | não rodado nesta fase; registro anterior em `docs/data/DATA_LINEAGE.md` |
| Treino completo do ranker e testes de robustez (5 sementes) | não re-executados; números vêm de `docs/MODEL_REPORT.md` e `ml/artifacts/` |
| DAST, teste de carga, teste de intrusão | nunca feitos |

## 4. Observações sobre o `smoke` local

O conjunto `smoke` que já existia na máquina de desenvolvimento foi gerado com outro hash de parâmetros (`0.2.0+de66952e+20261003`); a regeneração atual produz `0.2.0+477ed37e+20261003`. **Não é falha de determinismo:** duas gerações com os mesmos parâmetros deram o mesmo resultado. Os 311 testes passaram com o `smoke` antigo; o CI regenera o `smoke` a cada execução. Recomenda-se regenerá-lo localmente com o comando da seção 1 antes de novos testes.

## 5. Fatores que podem causar diferenças

* Versões das dependências estão fixadas em `requirements*.txt`; mesmo assim, sistema operacional e Python diferentes podem alterar o treino (floats); por isso as métricas do modelo são tratadas como as de `docs/MODEL_REPORT.md`, não recalculadas aqui.
* As fontes públicas podem mudar ou sair do ar; os checksums SHA-256 do RAW detectam alteração.
* Dados em `data/` não são versionados (licenças pendentes); quem clona precisa gerá-los.
