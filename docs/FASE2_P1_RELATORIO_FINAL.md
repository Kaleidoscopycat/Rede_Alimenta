# Relatório final — Fase 2 · Parte 1 (plataforma, API e motor de match)

Data: 2026-10-08. A Parte 2 (roteamento, Docker, CI/CD, Bandit/Trivy) **não foi iniciada**.

## 1. O que foi alterado
* **Banco**: PostgreSQL 16.2 local (sem Docker) + SQLAlchemy 2.0 + Alembic (migração `0001`, 19 tabelas); restrições `CHECK` de `data_origin`.
* **Importação**: 54 590 ONGs reais (rastreáveis) + dados do simulador (SIMULATED) + território/indicadores.
* **Motor de match híbrido** com 7 regras eliminatórias e scores separados; **ciclo de vida** em tempo real com reserva transacional de capacidade; comparação **guloso × ótimo** em lote.
* **Parser semântico integrado** à entrada da doação (confirmação humana, bloqueio por validade, auditoria por campo).
* **API v1 autenticada** (DONOR/ORG/ADMIN) e **UI Streamlit mínima** (doador e ONG, só via HTTP).
* Teste antigo `tests/test_api.py` migrou de `/predict` para `POST /api/v1/predictions` (a API da Fase 1 foi substituída).

## 2. Arquivos
Novos: `core/settings.py`, `database/{session,models,importers}.py`, `database/migrations/**`, `alembic.ini`, `match/{schedule,eligibility,scoring,index,engine,lifecycle,batch,metrics}.py`, `api/{auth,parsing,donation_rules,schemas_v2,state}.py`, `api/routers/*`, `app/{api_client,streamlit_app}.py`, `scripts/{pg_local.sh,bootstrap_db.py,create_user.py,e2e_flow.py,e2e_run.sh,measure_latency.py}`, `tests/test_p2_*.py`, `tests/helpers_p2.py`, `.env.example`, `.gitignore`, docs (`FASE2_P1_*`, `data/PENDING_LICENSE_CONFIRMATIONS.md`, `data/IMPORT_REPORT_FASE2P1.json`, `E2E_FASE2P1_RESULTADO.json`, `LATENCIA_MATCH_FASE2P1.json`).
Modificados: `api/main.py` (substituído), `api/service.py` (aceita ONGs/território do banco), `tests/conftest.py`, `tests/test_api.py`, `requirements.txt`, `README.md`, `security/STRIDE.md` (seção 11), `docs/data/{DATA_SIMULATION,DATA_SOURCES,DATA_LINEAGE}.md`.

## 3. Fontes de dados
IPEA/Mapa das OSCs (54 398 ONGs), RBBA/MDS (192 bancos), IBGE (municípios/população), centroides de terceiros (PROXY), PAA/MDS. Cada ONG guarda `source`, `source_record_id`, `source_url`, `last_verified_at`. Simulador `main` (`dataset_version 0.2.0+477ed37e+20261003`, seed 20261003).

## 4. Licenças
**Nenhuma foi confirmada nesta fase.** IPEA/OSC, RBBA, IBGE, CNPJ e centroides permanecem **NEEDS_REVIEW** (`publication_cleared=false`); PAA é CC-BY a reverificar. Ver `docs/data/PENDING_LICENSE_CONFIRMATIONS.md`.

## 5. Registros: reais × simulados
| Origem | Registros |
|---|---|
| PUBLIC (reais, fontes públicas) | 54 590 organizações · 54 590 localizações (190 EXACT, 54 400 centroide de município) · 5 571 municípios · 27 855 indicadores · 7 fontes · 11 categorias |
| SIMULATED | 54 590 perfis declarados das ONGs · 8 000 doadores · 60 000 doações/itens (históricos) |
| USER_ENTERED | **0** (não há uso real; nenhum dado fictício foi marcado como real) |

As ONGs são registros públicos (`PUBLIC_RECORD`), **não clientes**. Os 895 mil pares contrafactuais do simulador não foram importados (permanecem em parquet).

## 6. Testes
`python -m pytest`: **83 passed** (32 da Fase 1 + 51 da Parte 1: banco/importação, autenticação 401/403/permitido, parser pela API, regras e scores, ciclo de vida completo com recusa/expiração/aceite/coleta, concorrência de capacidade, lote, geolocalização, contrato OpenAPI, fluxo da UI e AppTest do Streamlit). Validação ponta a ponta (`scripts/e2e_run.sh`) com API e Streamlit reais: doador SIMULATED → parse → confirmação do campo pendente → match → ONG recusa → próxima aceita → coleta (`COLLECTED`). Latência do ranking (200 execuções, ambiente local): p50 ≈ 15 ms, p95 ≈ 29 ms; match completo via HTTP ≈ 150 ms.
Bug corrigido durante os testes: valores `None` nos ajustes do doador sobrescreviam a perecibilidade derivada (a doação ficava indevidamente pendente).

## 7. Métricas do modelo (todas SIMULADAS)
Ranker `ranker-1.0.0` e parser `semantic-parser-1.0.0` foram treinados/avaliados **somente em dados simulados** (ver `docs/MODEL_REPORT.md`); τ=0,66 calibrado sobre texto simulado; não há conjunto MANUALLY_LABELED. Nenhuma métrica nova de desempenho foi produzida na Parte 1, e **nenhum valor simulado representa desempenho real**. Tempos de match registrados são de execuções de demonstração (contas de teste), não de ONGs reais.

## 8. Pendências reais
1. Confirmação formal de licenças (IPEA, RBBA, IBGE, CNPJ, malha oficial).
2. Corpus real de textos e conjunto `MANUALLY_LABELED` (o rascunho de IA não vale).
3. Simulador: R1 não passa e R6 pessimista; atributos declarados das ONGs 100% simulados (cadastro real inexistente).
4. **TLS e rate limit PENDENTES**; token estático sem expiração/rotação (STRIDE P2-3/6/7).
5. PostgreSQL desta fase é uma instância embutida de desenvolvimento (sem Docker); sem backup/HA.
6. Parser: "vence ontem" → ausente (bloqueio seguro); data sem ano já passada é projetada para o ano seguinte (exige confirmação).
7. Distâncias em linha reta, aproximadas quando há centroide; pesos do FINAL_SCORE são premissas.
8. Cobertura de dependências/SAST (Bandit/Trivy) e Docker: Parte 2.

## 9. Próximo passo recomendado
Aprovar a Parte 1 e iniciar a **Parte 2** (roteamento, contêineres, CI/CD e varredura de segurança), em paralelo ao envio dos e-mails de confirmação de licença e à rotulagem manual dos textos.

## Checklist
Prechecks ✔ · Auth mínima ✔ (TLS/rate limit pendentes) · PostgreSQL+Alembic ✔ · ONGs reais rastreáveis ✔ · Motor híbrido com scores separados ✔ · Ciclo de vida/eventos ✔ · Capacidade transacional ✔ · Guloso×ótimo ✔ · Parser integrado ✔ · Haversine/precisão ✔ · Endpoints (sem rota) ✔ · UI mínima ✔ · Testes 83/83 ✔ · Validação ponta a ponta ✔ · Dados reais×simulados separados ✔ · Parte 2 NÃO iniciada ✔.
