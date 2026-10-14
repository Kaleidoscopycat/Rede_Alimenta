# Implantação — Rede Alimenta IA

> Conferido em `.github/workflows/ci.yml`, `render.yaml`, `docker/`, `docker-compose.yml`, `docs/DEPLOY.md`, `core/settings.py`, `core/hardening.py` e no relatório de estado do deploy do projeto (14/10/2026). O que depende de GitHub Actions, Docker, Render ou Supabase está marcado **"confirmado pelo CI"** ou **"não verificado neste ambiente"**: o ambiente em que esta documentação foi escrita não tem Docker, GitHub nem nuvem.

## 1. Pipeline e hospedagem

```mermaid
flowchart LR
    DEV["Responsável<br/>(commit e push)"] --> GH["GitHub<br/>repositório"]

    subgraph CI["GitHub Actions (ci.yml)"]
        LINT["lint: Ruff"]
        TEST["testes: pytest + PostgreSQL 16"]
        BAN["SAST: Bandit"]
        DEP["dependências e segredos:<br/>pip-audit, Trivy fs, gitleaks"]
        DKR["Docker: build, Trivy config e imagem,<br/>fluxo e2e via Docker Compose"]
    end

    GH --> LINT
    GH --> TEST
    GH --> BAN
    GH --> DEP
    LINT --> DKR
    TEST --> DKR

    GH -->|"autoDeployTrigger: checksPass<br/>(render.yaml)"| RND

    subgraph RND["Render (planos gratuitos, 2 serviços Docker)"]
        FE["rede-alimenta-frontend<br/>Streamlit"]
        API["rede-alimenta-api<br/>FastAPI + uvicorn"]
    end

    subgraph SUP["Supabase (plano gratuito)"]
        PG[("PostgreSQL<br/>Session pooler :5432<br/>SSL (require) · RLS")]
    end

    U(["Navegador"]) -->|"HTTPS (TLS do Render)"| FE
    FE -->|"HTTPS + Bearer token"| API
    API -->|"SSL, usuário dono"| PG
    OP(["Responsável (terminal)"]) -->|"load_to_cloud,<br/>create_user"| PG
```

| Etapa | O que roda | Situação |
|---|---|---|
| Lint, testes, Bandit, pip-audit, Trivy, gitleaks, Docker e2e | `ci.yml` (ações fixadas por SHA, `permissions: contents: read`) | Execução no GitHub **confirmada pelo CI** (informada pelo responsável; não verificada aqui) |
| Publicação | Render lê `render.yaml` (Blueprint); `autoDeployTrigger: checksPass` | URLs públicas informadas pelo responsável (14/10/2026); **não verificado neste ambiente** |
| Banco | Supabase (projeto `rede-alimenta`, região informada: Virginia/EUA), carga por `scripts/load_to_cloud.py --confirm-cloud` | Informado pelo responsável; RLS conferido pelo passo 4 do `docs/DEPLOY.md` (**não verificado neste ambiente**) |
| Hibernação | Render gratuito hiberna após ~15 min sem uso (cerca de 1 min para acordar); Supabase gratuito pausa por inatividade | Risco aceito (STRIDE P3D-11) |

## 2. Onde ficam os segredos

```mermaid
flowchart TB
    subgraph NAO["NUNCA no repositório, imagens nem chat"]
        S1["DATABASE_URL (senha do banco)"]
        S2["Tokens DONOR / ORG / ADMIN (exibidos uma vez)"]
        S3["Senha do banco no painel do Supabase"]
    end

    subgraph ONDE["Onde cada um vive"]
        R1["Render › Environment da API<br/>DATABASE_URL, CORS_ALLOW_ORIGINS<br/>(sync: false no render.yaml)"]
        R2["Gerenciador de senhas do responsável<br/>(tokens e senha do banco)"]
        R3["Banco: apenas o hash SHA-256 do token"]
        R4["CI: senha efêmera do Postgres gerada na execução<br/>(::add-mask::) · tokens e2e por perfil, só no job"]
    end

    S1 --> R1
    S1 --> R2
    S2 --> R2
    S2 --> R3
    S3 --> R2
```

O `render.yaml` contém **apenas** nomes de variáveis e valores não secretos; `.env.example` só documenta nomes; `.dockerignore` exclui `.env`, `data/` e testes das imagens; gitleaks (histórico e árvore) deu 0 achados nos relatórios `security/reports/depois/` (local) e roda também no CI.

## 3. Fronteiras de confiança

```mermaid
flowchart LR
    subgraph Z0["Zona 0: Internet / navegador (não confiável)"]
        B["Navegador"]
        ATT["Qualquer cliente HTTP"]
    end

    subgraph Z1["Zona 1: plataforma Render (TLS, proxy)"]
        FE["Frontend Streamlit"]
        API["API FastAPI<br/>autenticação + autorização"]
    end

    subgraph Z2["Zona 2: Supabase"]
        DB[("PostgreSQL<br/>RLS, SSL require")]
    end

    subgraph Z3["Zona 3: cadeia de suprimento"]
        GH["GitHub + CI"]
        PKG["PyPI / imagens base"]
    end

    B -- "F1 HTTPS" --> FE
    ATT -- "F1 HTTPS (API pública)" --> API
    FE -- "F2 HTTPS + token do usuário" --> API
    API -- "F3 SSL, sem verificação do servidor" --> DB
    GH -- "F4 deploy (checksPass)" --> API
    PKG -- "F5 dependências fixadas, pip-audit/Trivy" --> GH
```

| Fronteira | Controle real | Limite conhecido |
|---|---|---|
| F1 Internet → API/frontend | TLS do Render; CORS restrito; cabeçalhos de segurança; `/docs` desligado; token Bearer; limite de **tentativas inválidas** por IP; **rate limit global** por token/IP | **API pública com token estático** (rotação manual); rate limit global **por instância e em memória**; sem WAF |
| F2 frontend → API | token do usuário na sessão do Streamlit (memória, nunca em disco); visibilidade por perfil aplicada **na API** | o frontend chama pelo servidor: o IP visto pela API tende a ser o do frontend |
| F3 API → banco | usuário dono; `sslmode=require` (criptografa); RLS + `REVOKE` de `anon`/`authenticated` | `require` **não verifica o servidor** (sem `verify-full`/CA); sem backup gerenciado |
| F4 GitHub → Render | deploy só depois dos checks (`checksPass`) | proteção de branch/revisão obrigatória são configurações do repositório (pendentes) |
| F5 dependências | versões fixadas; pip-audit, Trivy e gitleaks no CI | Trivy de imagem: JSONs antes/depois ainda não versionados em `security/reports/ci/` |

## 4. Execução local (alternativa à nuvem)

`docker compose up` sobe `postgres` (sem porta publicada), `migrate`, `api` e `frontend` em `127.0.0.1`, com `cap_drop: ALL` e `no-new-privileges`. O Compose **não** foi executado no ambiente em que esta documentação foi escrita (sem Docker); a execução ponta a ponta é confirmada pelo CI. Passo a passo: `docs/REPRODUCIBILITY.md`.

## 5. Validação dos diagramas Mermaid

Os **8 diagramas** deste diretório (`architecture.md` ×1, `data-flow.md` ×4, `deployment.md` ×3) foram **renderizados sem erro** nesta sessão com `@mermaid-js/mermaid-cli` 11.4.2 (Chromium headless), um a um. O primeiro teste achou um erro de sintaxe (ponto e vírgula dentro de mensagem do diagrama de sequência), corrigido e renderizado de novo. Renderizadores diferentes (GitHub, mermaid.live) podem usar outra versão do Mermaid; se algum bloco não aparecer, cole-o em <https://mermaid.live>. Os SVGs gerados não foram versionados.
