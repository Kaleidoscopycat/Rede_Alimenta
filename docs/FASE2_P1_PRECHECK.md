# Fase 2 · Parte 1 — Prechecks (item 0)

Data de execução: 2026-10-08 (ambiente de desenvolvimento do projeto). Escopo: somente a Parte 1; **nada da Parte 2** (roteamento, Docker, CI/CD, Bandit/Trivy) foi iniciado.

## 0.1 PostgreSQL
| Item | Situação |
|---|---|
| Instância existente | **Nenhuma** (sem `psql`/`pg_ctl` no sistema e **sem Docker** no ambiente de execução) |
| Ação | Instância **standalone** PostgreSQL 16.2 (binários do pacote pip `pgserver`, usado só como distribuição dos binários) |
| Comando documentado | `export POSTGRES_PASSWORD=…; scripts/pg_local.sh init` · `scripts/pg_local.sh start` · `stop` · `status` (porta 5433, `127.0.0.1`, auth `scram-sha-256`; dados em `~/rede_alimenta_pgdata`, fora do repositório) |
| Alternativa com Docker | `docker run -d --name rede-alimenta-pg -e POSTGRES_PASSWORD=*** -e POSTGRES_DB=rede_alimenta -p 5433:5432 postgres:16` (não executada aqui) |
| Bancos | `rede_alimenta` (operação/validação) e `rede_alimenta_test` (testes; o esquema é recriado) |
| Segredos | só por variável de ambiente (`.env.example` sem valores reais; `.gitignore` bloqueia `.env`) |

> Esta é uma instância de desenvolvimento **dentro do sandbox**, não um ambiente de produção.

## 0.2 Limitações herdadas (mantidas e exibidas)
| Limitação | Como é tratada na Parte 1 |
|---|---|
| `PROVISORIO_rascunho_ia.csv` é rascunho gerado por IA, **não** `MANUALLY_LABELED` | Nunca usado como teste de desempenho; `GET /model/info` e `parse` informam "sem conjunto MANUALLY_LABELED"; UI repete o aviso |
| τ do parser (0,66) foi calibrado sobre **texto simulado** | Toda resposta de `POST /donations/parse` traz `threshold_note = "limiar calibrado sobre texto simulado"`, `training_data_origin = SIMULATED`, `parser_version`; a UI e os docs repetem |
| Simulador: **R1 não passa**; **R6 pessimista** | Registrado em `docs/data/DATA_SIMULATION.md` (seção 7) e exibido como "dados simulados com limitações conhecidas" na UI, no `/model/info` e nas respostas de match |
| Licenças não confirmadas (IPEA/OSC, RBBA, IBGE, CNPJ, centroides) | Permanecem **NEEDS_REVIEW** (`public_data_sources.review_status`; `publication_cleared=false`). Lista de pendências: `docs/data/PENDING_LICENSE_CONFIRMATIONS.md` |
| Parser devolve `AUSENTE` para "vence ontem" | Limitação conhecida e registrada; o lote fica `BLOCKED_NO_VALIDITY` (bloqueio seguro) até o doador informar a validade |

## 0.3 Autenticação mínima (aplicada na API)
Token por usuário (`rai_…`, 256 bits), perfis DONOR/ORG/ADMIN, autorização por posse do recurso, só o hash SHA-256 é gravado, `audit_logs` para falhas (401/403) sem o token, exceções públicas apenas `/health`, `/ready` e OpenAPI. Testes: `tests/test_p2_auth.py`. **TLS e rate limit estão PENDENTES** (registrados em `security/STRIDE.md`, seção 11), assim como a limitação do esquema de token estático.
