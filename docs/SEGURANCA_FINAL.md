# Segurança final — Rede Alimenta IA (Fase 4 · Etapas A e B)

> Consolida os controles, as varreduras e os riscos residuais da demonstração publicada. **Legenda de verificação** usada em todo o documento:
> * **executado aqui** = rodado no ambiente de desenvolvimento desta sessão (Linux, Python 3.10.12, PostgreSQL 16.2 local, sem Docker, sem GitHub, sem acesso à nuvem do projeto), em 14/10/2026;
> * **confirmado pelo CI** = só o GitHub Actions comprova (o responsável informa CI verde; esta sessão não o viu);
> * **não verificado neste ambiente** = depende de Render, Supabase, GitHub ou Docker.
> Nenhum resultado abaixo foi presumido. Modelagem de ameaças: `security/STRIDE.md` (§16 = estado final). Privacidade: `docs/LGPD.md`.

## 1. Resultados das verificações

| Verificação | Resultado | Onde | Verificação |
|---|---|---|---|
| **pytest (suíte completa)** | **334 passaram, 0 falharam, 0 puladas** (36 arquivos de teste; 4 lotes: 94 + 132 + 39 + 69; 23 testes novos da Etapa B), contra PostgreSQL local | `tests/` | executado aqui (14/10/2026, após a Etapa B) |
| **Ruff 0.17.0** | `All checks passed!` | `ruff check .` | executado aqui |
| **Bandit 1.9.4** (SAST) | **0 achados** (LOW 0, MEDIUM 0, HIGH 0) em 11.836 linhas (a Etapa B acrescentou código; um falso positivo B105 numa chave de dicionário foi resolvido renomeando a chave, sem `# nosec` novo); 10 supressões `# nosec` específicas, todas registradas em `security/reports/SUPRESSOES.md` (3 foram registradas nesta fase) | `api app core database match ml pipelines routing scripts simulation quality eda` (excl. `tests`) | executado aqui |
| **pip-audit 2.10.1** (dependências) | `No known vulnerabilities found` para `requirements-dev.txt` (inclui API e frontend), resolvido com a base de avisos da data da execução | `pip-audit -r requirements-dev.txt` | executado aqui |
| Contrato OpenAPI | `docs/openapi.json` confere com o gerado pela aplicação; nenhum campo de IA nos modelos de DONOR e ORG | `tests/test_p4a_openapi.py` (4 testes) | executado aqui |
| Diagramas | 8 diagramas Mermaid renderizados sem erro (mermaid-cli 11.4.2) | `docs/architecture/` | executado aqui |
| gitleaks (histórico e árvore) | 0 achados | `security/reports/depois/` (Fase 2) | execução anterior, registrada no repositório; no CI roda a cada push (**confirmado pelo CI**) |
| **Trivy** (dependências, configuração, **imagem**) | gate HIGH/CRITICAL corrigível; "4 HIGH → 0" da imagem é afirmação do CI | `.github/workflows/ci.yml` | **confirmado pelo CI** — o Trivy não roda aqui; JSON antes/depois ainda **não versionados** em `security/reports/ci/` (pendência) |
| Docker build, Compose e2e | fluxo completo em contêineres | job `docker` do CI | **confirmado pelo CI** — sem Docker aqui |
| **e2e local com HTTP real** (API + Streamlit + 3 perfis, `scripts/e2e_run.sh`), com o rate limit nos padrões | `exit_e2e=0` (banco local migrado até `0005`) | `scripts/e2e_flow.py` | executado aqui (não é o e2e em Docker Compose do CI) |
| Smoke da nuvem (`smoke_cloud`) | tudo `[OK]`, incluindo campos de IA ocultos para DONOR e ORG | relatório de deploy do projeto | informado pelo responsável; **não verificado neste ambiente** |

Observações sobre a execução:
* O `pip-audit` do **ambiente** da sessão (sem `-r`) reportou 22 avisos em `pip 22.0.2` e `setuptools 59.6.0`. Eles são ferramentas do ambiente temporário (não estão em nenhum `requirements*.txt` e são **removidos das imagens** pelos Dockerfiles); as outras 101 dependências instaladas tiveram 0 avisos. A medida que vale para o projeto é a de `-r requirements-dev.txt`, acima.
* Os testes usaram o conjunto simulado `smoke` que já estava na máquina, gerado com um hash de parâmetros anterior (`0.2.0+de66952e+20261003`); a regeneração atual dá `0.2.0+477ed37e+20261003` (o mesmo de `main`). O CI regenera o `smoke` a cada execução. Não afeta os resultados acima, mas vale regenerar localmente (`docs/REPRODUCIBILITY.md`).
* Apenas `rede_alimenta_test` (banco temporário em `/tmp`) foi tocado pelos testes; nenhum banco real ou em nuvem foi acessado.

## 2. Controles implementados (e a prova de cada um)

| Controle | Implementação | Prova |
|---|---|---|
| Autenticação Bearer por perfil (DONOR/ORG/ADMIN), token de 256 bits, **só o hash SHA-256 no banco**, exibido uma vez | `api/auth.py`, `scripts/create_user.py` | `tests/test_p2_auth.py` (`test_token_invalido_401_e_nao_grava_token`, `test_rotas_publicas_sem_token`) |
| Autorização por perfil e por posse do recurso (IDOR) | `require_roles`, `forbid` | `test_perfil_errado_403`, `test_recurso_de_outro_usuario_403` |
| **Visibilidade por perfil aplicada na API** (sem scores/ranking/saída do parser para DONOR e ORG) | `api/schemas_views.py` | `tests/test_p3a_visibilidade_perfil.py`, `tests/test_p3b_campos_ia_proibidos.py`, `tests/test_p4a_openapi.py` |
| Resposta de autenticação genérica (não revela se o token existe, expirou ou está inativo) | `api/auth.py` | `tests/test_p3d_banco_producao.py` |
| Expiração opcional e revogação de token | `users.expires_at`, `--expires-in-hours`, `--revoke` | `test_token_expirado_e_recusado_*`, `test_revogar_token_por_rotulo` |
| Limite de **tentativas inválidas** por IP (429 + `Retry-After`) | `core/hardening.py::AuthFailureLimiter` | `test_limitador_*` |
| **Rate limit global por requisição (Etapa B)**: chave = hash do token (ou IP sem token), teto por IP, 1.200/min por token, 240/min por IP sem token, 6.000/min de teto; `/health` e `/ready` isentos; 429 genérico + `Retry-After`; log JSON sem token e sem gravar no banco; desligável (`RATE_LIMIT_ENABLED`); contador no painel ADMIN (`/api/v1/admin/stats/security`, campo `rate_limit`). **Por instância e em memória** | `core/hardening.py::RateLimitMiddleware`, `api/main.py` | `tests/test_p4b_rate_limit.py` (15 testes); atrás do proxy do Render: **não verificado neste ambiente** |
| **Rotação de token (Etapa B)**: `create_user --rotate <rótulo>` em uma transação (novo token com mesmo perfil/vínculo/`--demo`, anterior desativado, auditoria `user.rotate` sem token, token novo impresso uma vez) | `scripts/create_user.py::rotate` | `tests/test_p4b_rotacao.py` (8 testes) |
| Auditoria de 401/403/429 e de acessos ADMIN, sem token | `audit_logs` | `test_acesso_admin_e_auditado_sem_token`, `tests/test_p3c_admin_stats.py` |
| Cabeçalhos de segurança, CORS restrito, `/docs` `/redoc` `/openapi.json` desligados em produção | `core/hardening.py`, `api/main.py` | `tests/test_p3d_producao.py` |
| **RLS** em todas as tabelas e `REVOKE` de `anon`/`authenticated` | migration `0004` | `test_rls_em_todas_as_tabelas`; no Supabase real: **não verificado neste ambiente** |
| SSL obrigatório em banco remoto em produção | `core/settings.py` | `test_production_exige_ssl_*` |
| Segredos fora do repositório e das imagens; `render.yaml` sem valores | `.dockerignore`, `.env.example`, `render.yaml` | gitleaks (histórico e árvore: 0); `tests/test_p3d_arquivos_nuvem.py` |
| Contêiner não-root, `cap_drop: ALL`, `no-new-privileges`, pip removido da imagem final | `docker/`, `docker-compose.yml` | revisão do Dockerfile; build e Trivy **confirmados pelo CI** |
| Sanitização do texto de terceiros **na interface** (sem imagem/link/HTML) | `app/ui_common.py` | `tests/test_p3b_ui_apptest.py` |
| Verificação de hash do modelo ao carregar | `Ranker.__init__` | `tests/test_features_model.py` |
| Integridade da origem dos dados (`SIMULATED` exige rastreio; item herda a origem da doação) | `CHECK`s e FK composta | `tests/test_p2_db_import.py`, `tests/test_p3a_rascunho_api.py` |
| Validação de entrada (`extra="forbid"`, faixas, enums) e erro genérico 500 | Pydantic, `RequestContextMiddleware` | `tests/test_api.py::test_entradas_invalidas` |
| Contrato da API versionado, com erros padronizados e exemplos genéricos | `api/openapi_docs.py`, `docs/openapi.json` | `tests/test_p4a_openapi.py` |

## 3. Vulnerabilidades remanescentes e riscos residuais (por gravidade)

Resumo de `security/STRIDE.md` §16 (IDs `P4A-n`), com o estado real:

**Alta**
1. **API pública com token estático** (P4A-1): **rotação só manual** (`--rotate`, Etapa B), sem rotação automática, escopos nem MFA; expiração opcional e revogação manual.
2. **Rate limit global PARCIAL** (P4A-2, rebaixado de Alta para Média na Etapa B): existe, mas é **por instância e em memória** (não distribuído, zera ao reiniciar), com janela fixa (até 2× o limite na virada), sem WAF e sem proteção contra DDoS de rede; o comportamento atrás do proxy do Render não foi verificado aqui. Ao escalar: Redis ou gateway.
3. **Painel do ADMIN** com poder total e sem MFA (P4A-9).
4. **Cadeia de suprimento do CI** (P4A-11): ações fixadas por SHA e permissões mínimas, mas proteção de branch e revisão obrigatória pendentes no GitHub.
5. **Segredos com rotação manual** (P4A-14): sem gerenciador de segredos.

**Média**
6. **Amplificação por auditoria** (P4A-3, **novo achado desta fase**): toda negativa (inclusive `auth.rate_limited`) grava uma linha em `audit_logs`; sem retenção nem teto. Um atacante pode encher o banco gratuito.
7. **IP em `audit_logs` sem retenção e log de acesso do uvicorn com IP e query string** (P4A-4, **novo achado**; `docs/LGPD.md` R1 e R4). Desligar o log de acesso exige alterar Dockerfile/`render.yaml`, o que a Fase 4 proíbe.
8. **Banco com `sslmode=require` sem `verify-full`** (P4A-5): cifra, mas não verifica o servidor. `verify-full` depende da CA do Supabase e de teste contra a nuvem (impossíveis aqui).
9. **Limitador em memória por instância** (P4A-6): zera ao reiniciar ou hibernar; não é distribuído.
10. **Hibernação e pausa dos planos gratuitos** (P4A-7).
11. **Sem backup gerenciado** (P4A-8): perda do projeto Supabase é irreversível para `audit_logs` e contas.
12. **Artefatos `joblib` sem assinatura** (P4A-15): só hash.

**Baixa**
13. JSON do Trivy de imagem ainda sem versão em `security/reports/ci/` (P4A-10): o painel mostra "pendente".
14. Rótulo de conta sem validação de "nome de pessoa" (P4A-16).

**Limitações de IA que são risco de produto** (não de infraestrutura): métricas só sobre dados simulados; lote misto desconhecido; sem conjunto `MANUALLY_LABELED` (`docs/MODEL_CARD.md`).

## 4. Pendências reais do responsável

* Fazer o **commit e o push** (esta fase não commita) e conferir o **CI verde** após o push.
* Baixar os **JSON do Trivy de imagem** do job `docker` para `security/reports/ci/antes|depois/` (o painel só conta "4 → 0" com os dois lados).
* Configurar **proteção de branch e revisão obrigatória** no GitHub (P4A-11).
* Decidir sobre o **log de acesso do uvicorn** (`--no-access-log`) e sobre a **retenção do IP** em `audit_logs` (LGPD R1/R4).
* Gerar novo **token ADMIN** na manhã da defesa e **revogar** tudo depois; apagar o projeto Supabase e os serviços do Render conforme `docs/LICENCAS_DEMONSTRACAO.md`.
* Capturas de tela do README (`README.md`, seção "Capturas de tela a inserir").

## 5. O que este documento não afirma

Não afirma segurança em produção: nenhuma varredura dinâmica (DAST), teste de carga nem teste de intrusão foi feito, e o que roda na nuvem real **não foi verificado neste ambiente**. As varreduras acima são estáticas (código e dependências) e os testes são automatizados, locais.
