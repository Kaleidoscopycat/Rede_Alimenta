# Rede Alimenta IA

Projeto Integrador FIAP (DevSecOps) · **Fase 4 · Etapa A — documentação final**

> **Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais.** Hoje **"Nenhuma doação real registrada."** Doadores, lotes e desfechos são **SIMULADOS** (`data_origin = SIMULATED`); as ONGs são registros de fontes públicas (`PUBLIC`) e **não são clientes** da plataforma. **Métricas obtidas em dados simulados não são desempenho real.**

## 1. Problema

Alimento próprio para consumo é descartado enquanto ONGs precisam de doações. O gargalo é **encontrar a ONG certa, a tempo, com capacidade, refrigeração e rota**. A plataforma trata o fluxo **doador → ONG**; a entrega da ONG ao beneficiário final está fora do escopo.

## 2. Solução

* O doador monta a doação item a item (categoria, quantidade, peso, validade, refrigeração) ou cola um texto que vira **sugestões a confirmar**.
* O **motor de match** filtra as ONGs por regras eliminatórias sobre o *declarado*, pega as 15 mais próximas e as ordena por `FINAL = 0,5·ML + 0,3·regras + 0,2·distância`. A 1ª colocada recebe a proposta; ela aceita ou recusa, e o sistema segue para a próxima se houver recusa ou expiração (30 min).
* **Humano no circuito:** a ONG decide; o sistema **não atesta a segurança sanitária** do alimento.
* **Rotas de coleta** (OR-Tools × vizinho mais próximo) para doações já aceitas; distâncias são **estimadas**, não viárias.
* Três perfis, com a **visibilidade aplicada na API**: o doador não vê scores nem ranking; a ONG vê a proposta e uma análise em texto; só o ADMIN vê scores, ranking e o dashboard técnico (acesso auditado).

Arquitetura, fluxo de dados e implantação (diagramas Mermaid): [`docs/architecture/`](docs/architecture/architecture.md).

## 3. Tecnologias

FastAPI · SQLAlchemy + Alembic · PostgreSQL 16 (Supabase em produção, com RLS) · Streamlit · scikit-learn (HistGradientBoosting; TF-IDF + regressão logística) · OR-Tools · Docker/Compose · GitHub Actions (Ruff, pytest, Bandit, pip-audit, Trivy, gitleaks) · Render (2 serviços Docker, plano gratuito).

## 4. Dados: real × simulado

| Origem | O que é | Quantidade (fonte) | Selo |
|---|---|---|---|
| `PUBLIC` | ONGs e bancos de alimentos por **pseudônimo** (IPEA/OSC e RBBA), municípios e indicadores (IBGE, PAA) | 54.590 ONGs: 54.398 IPEA + 192 RBBA (`docs/data/DATA_SOURCES.md`, `docs/data/IMPORT_REPORT_FASE2P2.json`) | 🟦 PÚBLICO |
| `SIMULATED` | doadores, lotes, textos, desfechos, perfil declarado das ONGs | 8.000 doadores, 60.000 lotes, 895.177 pares (`docs/MODEL_REPORT.md`) | 🟧 SIMULADO |
| `USER_ENTERED` | entradas reais na plataforma | **0** | 🟩 MEDIDO |

Dados reais nunca são inventados; dados simulados vêm de um simulador reprodutível (semente + versão), sempre com rastreio (`generator_version`, `seed`, `dataset_version`). Para 99,65% das ONGs a coordenada é o **centroide do município** (190 têm coordenada exata). Detalhes: [`docs/data/`](docs/data/DATA_SOURCES.md).

## 5. Inteligência artificial

* **Ranker** `ranker-1.0.0` (HistGradientBoosting, 43 atributos, divisão temporal 70/15/15): **MRR 0,695**, Top-1 54,6%, ROC-AUC 0,798, contra a baseline "ONG mais próxima" (MRR 0,465). **Todos esses números são sobre dados SIMULADOS** e sofrem de **circularidade** (o simulador é definido por nós).
* **Parser de texto** (TF-IDF + regressão logística, limiar τ = 0,66): sugere campos que o doador confirma. **Não há conjunto `MANUALLY_LABELED`**: nunca foi medido com texto real de doadores.
* **Lote misto:** desempenho desconhecido (o treino usou lotes de uma só categoria).
* Ficha completa: [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) e [`docs/MODEL_REPORT.md`](docs/MODEL_REPORT.md).

## 6. Segurança e privacidade

Autenticação Bearer (token de 256 bits, **só o hash SHA-256 no banco**), perfis DONOR/ORG/ADMIN, autorização por posse do recurso, RLS em todas as tabelas, cabeçalhos de segurança, CORS restrito, SSL obrigatório no banco remoto, `/docs` desligado em produção, limite de tentativas inválidas por IP, **rate limit global por token/IP** (por instância, em memória), **rotação manual de token** (`create_user --rotate`), auditoria e contêineres sem root. Pipeline: Ruff, pytest, Bandit, pip-audit, Trivy, gitleaks e fluxo e2e via Compose.

* Estado final, varreduras e riscos residuais: [`docs/SEGURANCA_FINAL.md`](docs/SEGURANCA_FINAL.md) · modelagem de ameaças: [`security/STRIDE.md`](security/STRIDE.md) (§16) · LGPD: [`docs/LGPD.md`](docs/LGPD.md).
* **Riscos residuais ditos de frente:** API pública com token estático (rotação manual, não automática); rate limit global só por instância e em memória (não distribuído, sem WAF); `sslmode=require` sem `verify-full`; sem backup gerenciado; IP guardado em `audit_logs` sem prazo de retenção.

## 7. Como rodar localmente

Reprodução completa (do clone ao sistema no ar, o que foi e o que não foi executado): [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

```bash
pip install -r requirements-dev.txt
cp .env.example .env                                      # preencha localmente; nunca versione
scripts/pg_local.sh init && scripts/pg_local.sh start      # PostgreSQL local sem Docker (Linux/macOS)
python -m scripts.bootstrap_db                             # Alembic + ONGs reais (PUBLIC) + dados SIMULATED
python -m scripts.create_user --role ADMIN --label admin-local   # token exibido UMA vez
uvicorn api.main:app --port 8000                           # terminal 1
streamlit run app/streamlit_app.py                         # terminal 2 — http://localhost:8501
```

Os dados (`data/gold`, `data/metadata`, `data/simulated`) **não são versionados**: gere-os com `python -m pipelines.run_all` e `python -m simulation.generator --seed 20261003 --n-lots 60000 --n-donors 8000 --tag main` (use `--tag smoke` com valores pequenos para testes).

**Windows (PowerShell)** — `pg_local.sh` e `e2e_run.sh` são só Linux/macOS; use Docker (abaixo) ou PostgreSQL nativo:
```powershell
Copy-Item .env.example .env
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:DATABASE_URL = "postgresql+psycopg://rede_alimenta:<SENHA>@127.0.0.1:5433/rede_alimenta"
python -m scripts.bootstrap_db
python -m scripts.create_user --role ADMIN --label admin-local
python -m uvicorn api.main:app --port 8000        # terminal 1
streamlit run app/streamlit_app.py                # terminal 2
```

**Usuários de demonstração** (uma conta por perfil; o token aparece uma vez, não coloque em arquivo nem em print):
```bash
python -m scripts.create_user --list donors --limit 5
python -m scripts.create_user --list orgs --limit 5
python -m scripts.create_user --role DONOR --label conta-doador-demo --donor-id <UUID> --demo
python -m scripts.create_user --role ORG   --label conta-ong-demo    --org-id   <UUID> --demo
python -m scripts.create_user --revoke admin-local        # revoga e grava auditoria
python -m scripts.create_user --rotate admin-local        # rotação: novo token (uma vez), anterior desativado, auditoria user.rotate
```

### Docker

Pré-requisito: Docker com Compose v2 e as pastas de dados geradas localmente.
```bash
cp .env.example .env                      # preencha POSTGRES_PASSWORD (letras, números, - e _)
docker compose up -d postgres migrate     # banco + migrations (0001 a 0005)
docker compose --profile seed run --rm seed
docker compose up -d --build              # API em 127.0.0.1:8000, frontend em 127.0.0.1:8501
docker compose exec api python -m scripts.create_user --role ADMIN --label admin-local
```
Contêineres sem root (uid 10001), `cap_drop: ALL`, Postgres não publicado no host. O build e o Compose **não foram executados no ambiente em que esta documentação foi escrita (sem Docker)**; a execução ponta a ponta é **confirmada pelo CI**.

### Configuração

Variáveis documentadas em `.env.example` (apenas nomes e valores não secretos). Principais: `DATABASE_URL`, `APP_ENV` (`production` liga log JSON, SSL obrigatório, CORS restrito e desliga `/docs`), `CORS_ALLOW_ORIGINS`, `TRUST_PROXY_HEADERS`, `RATE_LIMIT_*` (rate limit global; padrões no código, `RATE_LIMIT_ENABLED=false` desliga), `MEAL_KG_PER_MEAL` (padrão 0,4, premissa da equipe), `API_BASE_URL` (frontend).

## 8. Testes e verificações

```bash
ruff check .
bandit -r api app core database match ml pipelines routing scripts simulation quality eda -x tests --severity-level medium
pip-audit -r requirements-dev.txt
python -m pytest                      # exige TEST_DATABASE_URL (banco *_test)
python -m scripts.export_openapi --check
```
Resultado da última execução (14/10/2026, ambiente de desenvolvimento, PostgreSQL 16.2 local): **311 testes passaram, 0 falharam**; Ruff limpo; Bandit 0 achados; pip-audit sem vulnerabilidades conhecidas em `requirements-dev.txt`. Trivy, Docker e GitHub Actions: **confirmados pelo CI**, não por esta execução. Detalhes: [`docs/SEGURANCA_FINAL.md`](docs/SEGURANCA_FINAL.md).

## 9. Publicação (demonstração)

| Serviço | URL |
|---|---|
| API | https://rede-alimenta-api.onrender.com |
| Frontend | https://rede-alimenta-frontend.onrender.com |

* Planos gratuitos **hibernam** após ~15 min sem uso; a primeira requisição pode levar **cerca de 1 minuto**.
* Os serviços e o banco são **de demonstração e podem ser desligados após a apresentação** (`docs/LICENCAS_DEMONSTRACAO.md`).
* Passo a passo de publicação e pendências do responsável: [`docs/DEPLOY.md`](docs/DEPLOY.md). A disponibilidade das URLs **não foi verificada neste ambiente**.

## 10. API e Swagger

Contrato OpenAPI versionado em [`docs/openapi.json`](docs/openapi.json) (gerado pela própria aplicação, com respostas de erro padronizadas e exemplos genéricos; um teste garante que o arquivo confere com a API). Em **produção** `/docs`, `/redoc` e `/openapi.json` ficam **desligados**.

Para ver o Swagger **localmente**: suba a API com `APP_ENV` diferente de `production` e abra http://127.0.0.1:8000/docs.
```bash
uvicorn api.main:app --port 8000
python -m scripts.export_openapi            # regenera docs/openapi.json
python -m scripts.export_openapi --check    # falha se o arquivo estiver desatualizado
```

## 11. Mapa do repositório

| Pasta | Conteúdo |
|---|---|
| `pipelines/`, `simulation/` | ingestão de dados reais; simulador reprodutível |
| `database/`, `scripts/` | modelos, migrations Alembic, importadores, utilitários (usuários, carga, smoke) |
| `ml/`, `match/`, `routing/` | ranker e parser; motor de match; rotas de coleta |
| `api/`, `app/`, `core/` | FastAPI; Streamlit; configuração e hardening |
| `security/` | STRIDE e relatórios de varredura |
| `docs/` | arquitetura, LGPD, model card, segurança, deploy, pitch, reprodutibilidade, prontidão comercial |
| `tests/` | suíte de testes |

## 12. Limitações

* Métricas de IA só em dados **simulados**; circularidade; lote misto desconhecido; sem rótulos manuais de texto real.
* Capacidade, horários e perfil das ONGs são **declarados/simulados**; distâncias em linha reta, não rota viária.
* Nenhuma doação real; **não é um produto pronto para uso comercial** (veja [`docs/COMMERCIAL_READINESS.md`](docs/COMMERCIAL_READINESS.md)).
* Licenças de IPEA/OSC, RBBA e centroides de município **não confirmadas** (`docs/data/DATA_LICENSES.md`); não redistribua `data/`.
* Riscos de segurança residuais: seção 6 e [`docs/SEGURANCA_FINAL.md`](docs/SEGURANCA_FINAL.md).

## 13. Roadmap (trabalho futuro, nada disto existe hoje)

* Lote misto por sublotes; rotulagem manual de textos reais e reavaliação do parser.
* Rate limit distribuído (Redis/gateway), rotação automática e escopos de token; `verify-full` no banco; retenção do IP em auditoria; backup gerenciado.
* Pilotos com doadores e ONGs reais, verificação de cadastro e de condições sanitárias.
* **Rede comunitária** (visão de longo prazo): ampliar para pequenos doadores e ações locais. Não faz parte do escopo atual.

## 14. Capturas de tela a inserir (pendente — não há imagens versionadas)

1. Tela do doador (Nova doação › Itens).
2. Tela da ONG (Propostas recebidas, com "Análise da IA").
3. Dashboard do ADMIN (Overview com selos PÚBLICO/SIMULADO/MEDIDO).
4. Mapa e logística (ONG mais próxima × ranking híbrido × rota).
5. Aba de segurança do dashboard.

## 15. Licenças

* **Software:** Apache-2.0 (arquivo `LICENSE`); dependências em `docs/data/SOFTWARE_LICENSES.md`.
* **Dados:** cada fonte tem seu termo; a tabela de licenças verificadas e pendentes está em [`docs/data/DATA_LICENSES.md`](docs/data/DATA_LICENSES.md). A licença do software **não** transfere direitos sobre os dados de terceiros.

## 16. Documentos principais

[`docs/architecture/`](docs/architecture/architecture.md) · [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) · [`docs/LGPD.md`](docs/LGPD.md) · [`docs/SEGURANCA_FINAL.md`](docs/SEGURANCA_FINAL.md) · [`security/STRIDE.md`](security/STRIDE.md) · [`docs/DEPLOY.md`](docs/DEPLOY.md) · [`docs/DASHBOARD.md`](docs/DASHBOARD.md) · [`docs/ROLE_VISIBILITY.md`](docs/ROLE_VISIBILITY.md) · [`docs/ROUTING.md`](docs/ROUTING.md) · [`docs/PITCH.md`](docs/PITCH.md) · [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) · [`docs/COMMERCIAL_READINESS.md`](docs/COMMERCIAL_READINESS.md)
