# Rede Alimenta IA — Projeto Integrador FIAP (Fase 1 + Fase 2 Parte 1)

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
Documentos: `docs/FASE2_P1_PRECHECK.md`, `docs/FASE2_P1_MATCH_ENGINE.md`, `docs/FASE2_P1_RELATORIO_FINAL.md`, `docs/data/PENDING_LICENSE_CONFIRMATIONS.md`. Não há endpoints de rota (Parte 2).
