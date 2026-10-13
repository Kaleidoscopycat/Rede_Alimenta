# Fase 3 · Parte 2 — Etapa B: relatório final (preparo para nuvem)

Escopo: preparar código e arquivos para a nuvem **sem acessar contas**. Nada foi publicado, nenhum recurso foi criado no Supabase/Render, nenhuma credencial foi lida ou impressa. Fora do escopo: Fase 4.

## 1. Alterações
* **Contêineres:** `PORT` em forma shell (`${PORT:-8000}` / `${PORT:-8501}`), HEALTHCHECK coerente, sem pip nas imagens finais; Compose com `APP_ENV`.
* **Produção (`APP_ENV=production`, `core/hardening.py`):** `/docs`, `/redoc`, `/openapi.json` desligados; CORS só para `CORS_ALLOW_ORIGINS`; cabeçalhos de segurança; log JSON; SSL obrigatório em banco remoto; limite em memória de tentativas de auth inválidas por IP (429); 401 genérico; pool configurável; `postgres://`/`postgresql://` convertidos para o driver psycopg 3.
* **Banco:** migration `0004` (RLS em todas as tabelas + revoga `anon`/`authenticated` se existirem; reversível) e `0005` (`users.expires_at` opcional); `create_user --expires-in-hours`.
* **Carga:** `scripts/load_to_cloud.py` (migrations + PÚBLICO + SIMULADO; `--confirm-cloud`; idempotente; host mascarado; contagens por origem; estimativa × limite gratuito).
* **Verificação:** `scripts/smoke_cloud.py` (somente leitura; `--acordar`).
* **Frontend:** tolera cold start do Render (nova tentativa de GET + "acordando o servidor"); aviso acadêmico em todas as telas.
* **Docs/infra:** `render.yaml`, `docs/DEPLOY.md`, `docs/LICENCAS_DEMONSTRACAO.md`, README, `docs/PITCH.md`, STRIDE §15 (P3D-1…12), `.env.example`.

## 2. Arquivos
Novos: `core/hardening.py`, `database/migrations/versions/0004_*.py`, `0005_*.py`, `scripts/load_to_cloud.py`, `scripts/smoke_cloud.py`, `render.yaml`, `docs/DEPLOY.md`, `docs/LICENCAS_DEMONSTRACAO.md`, `docs/FASE3P2B_RELATORIO_FINAL.md`, `tests/test_p3d_*.py` (4). Modificados: ver `git status` na resposta.

## 3. Fontes de dados · 4. Licenças
Sem mudança de fontes. Licenças IPEA/OSC, RBBA, IBGE e coordenadas **não confirmadas**; decisão do grupo com o professor: uso acadêmico, não comercial, até a apresentação; depois, licenciar ou remover e apagar o banco (`docs/LICENCAS_DEMONSTRACAO.md`). Nenhuma licença foi inventada.

## 5. Quantidade REAL × SIMULADA
Carga completa estimada (não executada na nuvem): 54.590 ONGs, 5.571 municípios, 27.855 indicadores (PÚBLICO); 8.000 doadores e 60.000 doações simuladas (tag `main`); 0 MEDIDO. Tamanho estimado ≈ **133,4 MB** de 500 MB (estimativa por bytes/linha medidos localmente).

## 6. Testes
**Validado localmente:** ruff limpo; Bandit 0 achados (inclui nível baixo); pytest **307 passed** (todos os arquivos, em 4 lotes, PostgreSQL local) — 34 testes novos da Etapa B (produção, limitador, SSL, RLS up/down e cobertura de todas as tabelas, expiração de token, retry do cliente, `load_to_cloud`, `smoke_cloud`, aviso acadêmico, `render.yaml`/Dockerfiles/docs sem segredos).
**Só o CI/deploy confirmam:** build das imagens e Compose (**Docker indisponível aqui**), Trivy, gitleaks, RLS no Supabase real, comportamento do Render (Blueprint, `autoDeployTrigger`, hibernação), `load_to_cloud` contra o Supabase, `smoke_cloud` contra URLs reais.

## 7. Métricas do modelo
Inalteradas (Etapa A; calculadas sobre dados SIMULADOS): HistGradientBoosting MRR 0,695 · Top-1 54,6% · Top-3 80,4% · NDCG@3 0,515 · ROC-AUC 0,798 · PR-AUC 0,459 · F1 0,503.

## 8. URL pública
**Pendente de provisionamento.**

## 9. Pendências reais
Criar projeto Supabase e rodar `load_to_cloud --confirm-cloud` · conferir RLS no painel · criar serviços via Blueprint e preencher `DATABASE_URL`, `CORS_ALLOW_ORIGINS`, `API_BASE_URL` · gerar tokens ADMIN/demo com validade · rodar `smoke_cloud` · validar build/Compose/Trivy no CI · baixar JSONs do Trivy para `security/reports/ci/antes|depois/` · preencher data/professor em `LICENCAS_DEMONSTRACAO.md` · apagar `_to_delete/` antes do commit.

## 10. Próximo passo
Revisar o diff, commitar com caminhos explícitos, fazer o deploy pelo `docs/DEPLOY.md` e só então iniciar a Fase 4 (rate limit global, rotação de tokens, `verify-full`).
