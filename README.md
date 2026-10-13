# Rede Alimenta IA — Projeto Integrador FIAP (Fases 1 a 3; Fase 3 Parte 2 · Etapa A: dashboard)

Solução para reduzir desperdício de alimentos conectando **doadores a ONGs** (fluxo DOADOR → ONG) com IA e DevSecOps. Este repositório contém dados (reais + simulados), a IA (ranker + parser), a API autenticada com motor de match e rotas de coleta, a interface por perfil, o **dashboard do ADMIN**, o pipeline DevSecOps e a modelagem de ameaças STRIDE.

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
docker compose up -d postgres migrate # banco + migrations Alembic (0001 a 0003)
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


## Fase 3 · Parte 1 — doação com vários itens e interface por perfil

> **Aviso:** doadores, doações, lotes e respostas das ONGs usados nas demonstrações são **SIMULADOS** (`data_origin = SIMULATED`); as ONGs listadas são registros de fontes públicas e **não são clientes** da plataforma. Contas `--demo` operam só sobre dados SIMULADOS. Nada simulado é apresentado como real.

**O que mudou**
* O doador monta a doação **item a item** (categoria, nome, unidades, peso/volume por unidade, validade e refrigeração); o total em kg, a validade mais próxima e a refrigeração do lote são calculados a partir dos itens (`docs/DONATION_ITEMS.md`). Líquidos viram kg por **estimativa** (premissa sem fonte), sempre sinalizada como "peso estimado".
* **Visibilidade por perfil aplicada na API** (`docs/ROLE_VISIBILITY.md`): o doador não vê scores, ranking nem saída do parser; a ONG vê a doação proposta, a própria distância e a "Análise da IA" em texto; só o ADMIN vê scores, ranking, modelo e saída do parser (acessos auditados).
* A tela é só apresentação — a barreira de segurança é a API.

**Telas (Streamlit, `app/streamlit_app.py`)**

| Perfil | Menu |
|---|---|
| DONOR | **Nova doação** (passos: Itens → Retirada → Revisar e enviar, com confirmação) · **Minhas doações** (status em destaque: Pendente, Aceita, Recusada…) |
| ORG | **Propostas recebidas** (Aceitar/Recusar com confirmação; bloco recolhível "Análise da IA") · **Histórico** |
| ADMIN | **Visão técnica (admin)** (ranking, scores, explicações, match_events e aviso de lote misto) |

### Criar usuários DONOR, ORG e ADMIN e rodar a interface

O token é exibido **uma única vez** (só o hash vai ao banco). Nunca coloque tokens em `.env`, no repositório ou em prints.

```bash
# 1) banco e carga (uma vez) — ver Fase 2; depois a API (terminal 1)
python -m scripts.bootstrap_db
uvicorn api.main:app --port 8000

# 2) usuários (uma conta por perfil). Liste ids de doadores SIMULATED e de ONGs (pseudônimos públicos):
python -m scripts.create_user --list donors --limit 5
python -m scripts.create_user --list orgs --limit 5
python -m scripts.create_user --role ADMIN --label admin-local
python -m scripts.create_user --role DONOR --label conta-doador-demo --donor-id <UUID-do-doador> --demo
python -m scripts.create_user --role ORG   --label conta-ong-demo    --org-id   <UUID-da-ong>    --demo

# 3) interface (terminal 2) — abra http://localhost:8501 e cole o token do perfil na barra lateral
streamlit run app/streamlit_app.py
```

Mesmos passos no **PowerShell** (Windows):
```powershell
python -m scripts.bootstrap_db
python -m uvicorn api.main:app --port 8000                       # terminal 1

python -m scripts.create_user --list donors --limit 5
python -m scripts.create_user --list orgs --limit 5
python -m scripts.create_user --role ADMIN --label admin-local
python -m scripts.create_user --role DONOR --label conta-doador-demo --donor-id <UUID-do-doador> --demo
python -m scripts.create_user --role ORG   --label conta-ong-demo    --org-id   <UUID-da-ong>    --demo

streamlit run app/streamlit_app.py                               # terminal 2 — http://localhost:8501
$env:API_BASE_URL = "http://127.0.0.1:8000"                      # opcional: se a API não estiver nesse endereço (defina ANTES do streamlit)
```

Com **Docker Compose** (a interface fica em `http://127.0.0.1:8501`):
```bash
docker compose up -d postgres migrate && docker compose --profile seed run --rm seed && docker compose up -d --build
docker compose exec api python -m scripts.create_user --list donors --limit 5
docker compose exec api python -m scripts.create_user --role DONOR --label conta-doador-demo --donor-id <UUID-do-doador> --demo
docker compose exec api python -m scripts.create_user --role ORG   --label conta-ong-demo    --org-id   <UUID-da-ong>    --demo
docker compose exec api python -m scripts.create_user --role ADMIN --label admin-local
```
(No PowerShell o mesmo funciona: troque apenas as quebras de linha e use `` ` `` para continuar uma linha.)

**Fluxo de demonstração (três perfis, três janelas/abas):** o doador adiciona vários itens com validades diferentes, confere o total, informa a retirada e envia → a ONG vê os itens e a "Análise da IA" e aceita ou recusa → o doador acompanha só a situação → o admin vê scores, ranking e o aviso de lote misto. Com um terminal de API em execução, `python -m scripts.e2e_flow` percorre o mesmo caminho por HTTP (tokens por perfil em `E2E_ADMIN_TOKEN`, `E2E_DONOR_TOKEN` e `E2E_ORG_TOKEN`, opcionais; sem eles o script gera tokens novos — ver `docs/ROLE_VISIBILITY.md`).

**Fluxo antigo (lote único):** `POST /donations/parse` está **descontinuado para DONOR** (a resposta é saída crua do parser); `POST /donations` e `PATCH /donations/{id}/confirm` continuam no servidor, mas a tela do doador não os usa. Ver `docs/ROLE_VISIBILITY.md` §1.1.

**Limitações:** o ranker foi treinado só com lotes SIMULADOS de uma única categoria — o desempenho em **lote misto é desconhecido** (aviso na Visão técnica); a leitura de texto livre nunca foi testada com texto real de doadores; token estático, sem TLS nem limite de requisições; localização exata e contato do doador para a ONG só após cadastro real.

Documentos: `docs/DONATION_ITEMS.md`, `docs/ROLE_VISIBILITY.md`, `security/STRIDE.md` (seção 13).


## Fase 3 · Parte 2 — dashboard do ADMIN, observabilidade, preparo de nuvem e defesa

> **Aviso:** dados demonstrativos — doadores, lotes e desfechos são **SIMULADOS**; ONGs e municípios são registros públicos (licença em revisão). Uso exclusivamente acadêmico, sem fins comerciais. Hoje **"Nenhuma doação real registrada."**

### Requisitos do projeto × situação
| Requisito | Situação (Etapas A e B) |
|---|---|
| A) Dataset estruturado | pronto (`data/`, `docs/data/`) — reais + simulados com `data_origin` |
| B) Modelo funcional local | pronto (`ml/artifacts`, `docs/MODEL_REPORT.md`) — métricas **sobre dados simulados** |
| C) Matriz de riscos (STRIDE) | pronta (`security/STRIDE.md`, §14 = dashboard) |
| D) Dockerfile + Compose | prontos (porta via `PORT` para o Render); **build não validado neste ambiente** (sem Docker) — confirma o CI |
| E) CI/CD (GitHub Actions) | pronto (`.github/workflows/ci.yml`); execução só no GitHub |
| F) SAST (Bandit e Trivy) | Bandit/ruff/pip-audit locais em `security/reports/fase3a/`; Trivy de imagem só no CI |
| G) URL pública | **pendente de provisionamento** — `render.yaml` e `docs/DEPLOY.md` prontos; falta o responsável criar os serviços |
| H) Banco em nuvem | **pendente de provisionamento** — migrations (`0004` RLS, `0005`) e `scripts/load_to_cloud.py` prontos; falta criar o projeto Supabase e carregar |
| I) README | este arquivo (rascunho completo) |
| J) Pitch | `docs/PITCH.md` (versão final da Etapa B) |

### Como rodar o dashboard (local)
```bash
python -m scripts.bootstrap_db                                   # esquema + ONGs reais + dados SIMULADOS (use --sim-tag smoke para uma carga pequena)
python -m scripts.create_user --role ADMIN --label admin-defesa  # token exibido UMA vez; não grave em arquivo
uvicorn api.main:app --port 8000                                 # terminal 1
streamlit run app/streamlit_app.py                               # terminal 2 — cole o token na barra lateral; o menu do ADMIN abre no Overview
python -m scripts.create_user --revoke admin-defesa              # ao final da defesa: desativa o token e grava auditoria `user.revoke`
```
Telas, indicadores e regras de exibição: **`docs/DASHBOARD.md`**. Em resumo: selos 🟦 PÚBLICO / 🟧 SIMULADO / 🟩 MEDIDO em todo número; refeições = kg ÷ 0,4 (premissa configurável por `MEAL_KG_PER_MEAL`, exibida na tela); métricas de IA com nomes reais (MRR, Top-1, Top-3, NDCG@3, ROC-AUC, PR-AUC, F1; "acurácia" só no parser) rotuladas como calculadas sobre dados simulados, com baselines; mapa sem serviço de terceiros; tela de logística compara ONG mais próxima × ranking híbrido × híbrido com rota (simulação reprodutível).

### Publicação em nuvem (preparada, **não publicada**)
* **Guia para iniciantes:** `docs/DEPLOY.md` (Supabase → migrations/carga → Render → tokens → smoke test → revogar). **Licenças dos dados:** `docs/LICENCAS_DEMONSTRACAO.md`.
* `render.yaml` (Blueprint: API + frontend, plano gratuito, segredos `sync: false`), `scripts/load_to_cloud.py` (carga idempotente, exige `--confirm-cloud`, nunca imprime a URL), `scripts/smoke_cloud.py` (somente leitura, `--acordar`).
* Em `APP_ENV=production`: `/docs` desligado, CORS restrito (`CORS_ALLOW_ORIGINS`), cabeçalhos de segurança, log JSON, SSL obrigatório em banco remoto, limite de tentativas de autenticação inválidas por IP e resposta genérica a falhas. RLS em todas as tabelas (migration `0004`). Token opcionalmente expira (`create_user --expires-in-hours`). Variáveis: `.env.example`.
* Riscos residuais (TLS pela plataforma; rate limit global e rotação de tokens = Fase 4): `security/STRIDE.md` §15.

> **Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais.** Este aviso aparece em todas as telas.

### Observabilidade
`APP_ENV=production` liga log JSON (uma linha por evento); em `development` o log é legível. Toda resposta traz `X-Request-ID` (aceito do cliente só em formato seguro). O log de requisição não registra token, corpo, query string nem IP. Eventos de negócio (`ingestion.import_all`, `simulation.done`, `prediction.ranker`, `match.event`) usam apenas identificadores técnicos e contagens.

### Verificações locais desta etapa
```bash
ruff check .                                   # All checks passed!
bandit -r api app core database match ml pipelines routing scripts simulation quality eda -x tests --severity-level medium
python -m pytest                               # exige TEST_DATABASE_URL (banco *_test)
```
E2E local (HTTP real, três perfis): `API_BASE_URL=http://127.0.0.1:8000 E2E_OUT=docs/E2E_FASE3P2A_RESULTADO.json python -m scripts.e2e_flow` — inclui `/api/v1/admin/stats/*` com ADMIN 200 + auditoria e DONOR/ORG 403.

### Limitações (também exibidas na tela de IA)
Circularidade do simulador; desempenho em **lote misto desconhecido**; **sem conjunto `MANUALLY_LABELED`**; ONGs por pseudônimo (capacidade/horários declarados e simulados); token estático, sem TLS nem rate limit nesta fase. Evolução futura: lote misto por sublotes.
