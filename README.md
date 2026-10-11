# Rede Alimenta IA — Projeto Integrador FIAP (Fase 1 + Fase 2 Partes 1 e 2)

Solução para reduzir desperdício de alimentos conectando **doadores a ONGs** (fluxo DOADOR → ONG) com IA e DevSecOps. Este repositório contém o **Checkpoint 1**: dados (reais + simulados), MVP da IA, API e modelagem de ameaças STRIDE.

> **Regra central (AGENTS.md):** dados REAIS (ONGs, bancos de alimentos, municípios, população, PAA) nunca são inventados; dados SIMULADOS (doadores, lotes, textos, desfechos) existem apenas como `data_origin = SIMULATED`; **métricas obtidas em dados simulados não são desempenho real**.

## Como reproduzir

```bash
pip install -r requirements.txt
python -m pipelines.run_all                      # raw → bronze → silver → gold (≈40 s; verifica checksums do RAW)
python -m simulation.generator --seed 20261003 --n-lots 60000 --n-donors 8000 --tag main
python -m simulation.validation main             # relatório de realismo
python -m ml.semantic.train_eval main            # análise semântica (texto simulado)
python -m ml.training.train main                 # ranker (baselines + LR/RF/HGB). Precisa de ~6 GB de RAM
python -m ml.training.robustness                 # 5 seeds + cenários + misspecificação (requer gerar os tags rb_s*, sc_*)
python -m quality.data_quality && python -m eda.eda
python -m pytest                                 # suíte de testes
uvicorn api.main:app --reload                    # Swagger em http://127.0.0.1:8000/docs
```

## Mapa do repositório

| Pasta | Conteúdo |
|---|---|
| `pipelines/` | Ingestão e transformação de dados REAIS (IBGE, IPEA/OSC, RBBA, PAA) e utilitários de geografia (haversine) |
| `simulation/` | Simulador de doações (ver `simulation/README.md`) |
| `ml/` | Dataset de pares, treino do ranker, avaliação, análise semântica |
| `api/` | FastAPI: `/health`, `/ready`, `/api/v1/model/info`, `POST /api/v1/predict` |
| `quality/`, `eda/` | Relatório de qualidade e EDA automáticos |
| `security/STRIDE.md` | Ameaças, impacto, probabilidade, mitigação e fase |
| `docs/data/` | Fontes, licenças, linhagem, dicionário, simulação, EDA, qualidade |
| `docs/MODEL_REPORT.md` | Modelo, métricas (SIMULADAS), limitações |
| `tests/` | Testes de ingestão, simulador, transformação, features, modelo, schemas e API |

## Limitações que a equipe deve conhecer

* Não há conjunto de textos reais rotulados (`data/manual_labeled/README.md` traz o protocolo).
* Atributos declarados das ONGs, frota, lotes e desfechos são simulados; o simulador tem validação documentada, com um check que **não passa** (R1) e outro que mostra viés pessimista (R6).
* Licenças de IPEA/OSC, RBBA e centroides de município estão marcadas como pendentes de confirmação em `docs/data/DATA_LICENSES.md`.


## Fase 2 · Parte 1 — plataforma, API autenticada e motor de match

```bash
cp .env.example .env   # preencha localmente (não versionar); carregue as variáveis no shell
scripts/pg_local.sh init && scripts/pg_local.sh start      # PostgreSQL local SEM Docker (ou use o docker run indicado no script)
python -m scripts.bootstrap_db                              # Alembic + importa ONGs reais (PUBLIC) e dados do simulador (SIMULATED)
python -m scripts.create_user --role ADMIN --label admin-local   # token exibido UMA vez
uvicorn api.main:app --port 8000                            # Swagger em /docs
streamlit run app/streamlit_app.py                          # UI mínima (doador / ONG) — fala só com a API
python -m pytest                                            # exige TEST_DATABASE_URL (banco *_test)
scripts/e2e_run.sh                                          # validação ponta a ponta (sobe tudo, roda o fluxo e encerra)
```
Documentos: `docs/FASE2_P1_PRECHECK.md`, `docs/FASE2_P1_MATCH_ENGINE.md`, `docs/FASE2_P1_RELATORIO_FINAL.md`, `docs/data/PENDING_LICENSE_CONFIRMATIONS.md`.


## Fase 2 · Parte 2 — rotas de coleta, Docker e DevSecOps

> **Aviso:** dados públicos usados para fins acadêmicos; licença de reutilização não confirmada (NEEDS_REVIEW, `publication_cleared=false`). Não redistribua `data/`. Toda métrica é calculada sobre dados SIMULADOS e não representa desempenho real.

### Docker (api + frontend + postgres)
Pré-requisito: Docker com Compose v2 e as pastas `data/gold`, `data/metadata`, `data/simulated` geradas localmente (pipelines + simulador; **não** versionadas).

```bash
cp .env.example .env                  # preencha POSTGRES_PASSWORD (letras, números, - e _). O .env não vai ao Git nem às imagens
docker compose up -d postgres migrate # banco + migrations Alembic (0001, 0002)
docker compose --profile seed run --rm seed   # carga: ONGs PUBLIC + dados SIMULATED (SIM_TAG=main por padrão)
docker compose up -d --build          # api (http://127.0.0.1:8000/docs) + frontend (http://127.0.0.1:8501)
docker compose exec api python -m scripts.create_user --role ADMIN --label admin-local   # token exibido UMA vez
```
Os contêineres rodam sem root (uid 10001), com `cap_drop: ALL`; o Postgres **não** é publicado no host; as portas ficam em `127.0.0.1`.

### Windows (PowerShell) — equivalentes do que é exclusivo de Linux
`scripts/pg_local.sh` e `scripts/e2e_run.sh` são **somente Linux/macOS** (Bash). No Windows use Docker (acima) ou:
```powershell
Copy-Item .env.example .env                            # edite e preencha POSTGRES_PASSWORD
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://rede_alimenta:<SENHA>@127.0.0.1:5433/rede_alimenta"   # banco local (instalação nativa do PostgreSQL 16) ou o do Compose com a porta publicada
python -m scripts.bootstrap_db                         # Alembic + carga
python -m scripts.create_user --role ADMIN --label admin-local
python -m uvicorn api.main:app --port 8000             # terminal 1
streamlit run app/streamlit_app.py                     # terminal 2 — funciona da raiz, sem PYTHONPATH e sem "python -m"
python -m scripts.e2e_flow                             # fluxo ponta a ponta (API em execução)
```
Correção de portabilidade: `streamlit run app/streamlit_app.py` falhava com `ModuleNotFoundError: No module named 'app'`; agora o próprio arquivo insere a raiz do projeto em `sys.path` (sem duplicar). Os scripts de `scripts/` usam o mesmo mecanismo. Teste: `tests/test_portabilidade.py`.

### Rotas de coleta
`POST /api/v1/routes/plan` (perfis ORG/ADMIN) planeja a coleta de doações **já aceitas** por uma ONG (um destino, até 12 doadores) e persiste duas rotas (`routes`/`route_stops`): a do **solver OR-Tools** (principal) e a do **baseline vizinho mais próximo**, com comparação. `GET /api/v1/routes/{id}` consulta. Restrições: capacidade do veículo e da ONG, janela de retirada do doador, entrega até a validade menos margem (`ROUTE_SAFETY_MARGIN_H`), refrigeração e janela da ONG. Distâncias/tempos são **estimativas** (haversine × desvio ÷ velocidade, como na Parte 1), não rota viária. Detalhes, premissas e resultados: `docs/ROUTING.md` e `docs/ROUTING_BENCHMARK.json`.

### CI/CD e segurança
`.github/workflows/ci.yml`: lint (Ruff), testes (com PostgreSQL), Bandit, pip-audit, Trivy (dependências, configuração e imagens), gitleaks e fluxo completo via Compose. Relatórios antes/depois em `security/reports/` (`LEIA-ME.md`, `SUPRESSOES.md`); ameaças em `security/STRIDE.md` (§11–12). Verificação de tipos (mypy) **não adotada** (falha interna da ferramenta).

Documentos: `docs/FASE2_P2_RELATORIO_FINAL.md`, `docs/ROUTING.md`.
