# Relatório final — Fase 2 · Parte 2 (Rotas, Docker e DevSecOps) — Checkpoint 2

**Rótulos:** ONGs, municípios e indicadores são registros públicos reais (licença **NÃO CONFIRMADA**, uso acadêmico). Doadores, lotes, frota, janelas e desfechos são **SIMULATED**. Toda métrica é calculada sobre dados simulados e **não** é desempenho real. Não houve avanço para a Fase 3.

## Checklist final (estado verdadeiro)
- [x] Correção do `streamlit_app.py` (importação sem PYTHONPATH) — validada por 7 testes (inclui AppTest a partir de outro diretório) e por `streamlit run app/streamlit_app.py` a partir da raiz, sem `python -m` e sem PYTHONPATH (health ok), **em Linux**. Execução em Windows real **não** foi feita neste ambiente.
- [ ] Docker funcionando (api, frontend, postgres) — **NÃO VERIFICADO**: o ambiente de desenvolvimento não tem Docker nem acesso aos registries. Dockerfiles e Compose foram escritos e só **emulados** (mesmos arquivos copiados pelo Dockerfile, venv mínimo): API `/ready` ok, carga de 8.000 doadores/60.000 doações, frontend sem exceções.
- [ ] `docker compose up` com o fluxo completo — **NÃO EXECUTADO**. O fluxo completo foi executado com sucesso contra API+PostgreSQL locais (equivalente funcional), via `scripts/e2e_flow.py`.
- [ ] Pipeline CI/CD verde — **NÃO VERIFICADO**: `.github/workflows/ci.yml` está escrito, validado com actionlint e seus passos foram replicados localmente; **nunca rodou no GitHub**.
- [~] Relatórios Bandit e Trivy (antes e depois) — **Bandit: sim** (13 → 0). **Trivy: só os scanners secret/misconfig** (Dockerfiles limpos); **vulnerabilidades de dependências e imagens NÃO executadas** (banco do Trivy inacessível aqui) — rodam no CI.
- [x] STRIDE atualizado (`security/STRIDE.md` §11–12), com o risco de divulgação de scores/ranking (P2B-1) como **PENDENTE**.
- [x] Roteirização com baseline e comparação (SIMULAÇÃO) — implementada; extensões listadas como pendência.
- [x] Testes passando: **112 passed, 2 xfailed** (os 2 xfail estritos descrevem a mitigação pendente de P2B-1).

## 1. Alterações realizadas
0. **Portabilidade:** bootstrap de `sys.path` (a partir de `Path(__file__)`, sem duplicar) em `app/streamlit_app.py` e nos scripts de `scripts/`. Exclusivos de Linux: `scripts/pg_local.sh`, `scripts/e2e_run.sh` (equivalentes PowerShell/Docker no README).
1. **Rotas:** migration `0002` (`vehicles`, `routes`, `route_stops`, todas com `data_origin`), núcleo `routing/` (matriz haversine×desvio, verificador, vizinho mais próximo, OR-Tools), serviço de persistência, `POST /api/v1/routes/plan` e `GET /api/v1/routes/{id}`, importação de 15.758 veículos SIMULADOS, `routing/benchmark.py`, `docs/ROUTING.md`.
2. **Docker:** `docker/Dockerfile.api`, `docker/Dockerfile.frontend`, `docker-compose.yml` (postgres, migrate, api, frontend, seed sob perfil), `docker-compose.ci.yml`, `.dockerignore`, `.env.example` sem credenciais, requirements separados (api/frontend/dev). Não-root, `cap_drop: ALL`, banco não publicado.
3. **CI/CD e segurança:** workflow com lint, testes, Bandit, pip-audit, Trivy (fs/config/imagem), gitleaks e fluxo Compose; ações fixadas por SHA; relatórios em `security/reports/` (antes/depois, `LEIA-ME.md`, `SUPRESSOES.md`). Correções de código: 6 `assert` → exceções, `try/except/pass` → log, limpeza do Ruff (imports/variáveis não usados). Senha literal do Postgres no CI trocada por senha gerada na execução.
4. **STRIDE:** §12 nova (22 itens) e status de A1/I1/I2/I3/P2-13 atualizados.
Outros: aviso "dados públicos usados para fins acadêmicos; licença de reutilização não confirmada" na interface; `ortools` adicionado; `mypy` removido (INTERNAL ERROR com 2.4.0) — **tipagem não adotada**.

## 2. Arquivos
Criados: `routing/{__init__,core,service,benchmark}.py`, `api/routers/routes.py`, `database/migrations/versions/0002_rotas_de_coleta.py`, `docker/Dockerfile.{api,frontend}`, `docker-compose{,.ci}.yml`, `.dockerignore`, `.gitattributes`, `.github/workflows/ci.yml`, `ruff.toml`, `requirements-{api,frontend,dev}.txt`, `tests/test_{portabilidade,p2b_routing_core,p2b_routes_api,p2b_divulgacao_scores_pendente,p2b_uso_academico}.py`, `security/reports/**`, `docs/{ROUTING.md,ROUTING_BENCHMARK.json,E2E_FASE2P2_SMOKE_RESULTADO.json,FASE2_P2_RELATORIO_FINAL.md}`, `docs/data/{IMPORT_REPORT_FASE2P2.json,SOFTWARE_LICENSES.md}`.
Modificados: `api/main.py`, `app/{streamlit_app,api_client}.py`, `core/settings.py`, `database/{models,importers}.py`, `scripts/*.py`, `requirements.txt`, `.env.example`, `README.md`, `security/STRIDE.md`, `docs/data/{DATA_LICENSES,PENDING_LICENSE_CONFIRMATIONS}.md`, testes `test_p2_db_import.py`/`test_p2_match.py` (head 0002; contrato OpenAPI com rotas) e limpezas do Ruff em vários módulos.

## 3. Fontes de dados
Nenhuma fonte nova (decisão da equipe). Reais já incorporadas: IPEA/OSC, RBBA, IBGE (municípios, população, coordenadas). Simulados: doadores, lotes, frota, perfis, desfechos (simulador documentado, semente 20261003).

## 4. Licenças
Dados: todas NEEDS_REVIEW, `publication_cleared=false` (teste automático); sem redistribuição de bases brutas. Software: OR-Tools **Apache-2.0** (metadados do pacote); ver `docs/data/SOFTWARE_LICENSES.md`.

## 5. Registros
REAIS (sem reprocessamento nesta parte; contagens conferidas no banco): 54.590 ONGs (+ 54.590 localizações), 5.571 municípios, 27.855 indicadores. SIMULADOS importados: 54.590 perfis de ONG, **15.758 veículos (novo)**, 8.000 doadores, 60.000 doações/itens. USER_ENTERED: 0.

## 6. Testes
`pytest`: **112 passed, 2 xfailed** (antes: 83). Novos: 7 portabilidade, 9 núcleo de rotas (restrições, verificador, ótimo por força bruta, baseline × solver), 9 endpoints, 4 uso acadêmico, 2 xfail (P2B-1). `ruff`: limpo. Fluxo e2e (carga `smoke` regenerada): doação → parse → match → recusa → aceite → rota PLANNED → COLLECTED.

## 7. Métricas do modelo (SIMULADAS)
Não foram recalculadas. Vigentes (`docs/MODEL_REPORT.md`, calculadas sobre dados simulados): HGB MRR 0,695, Top-1 0,546, ROC-AUC 0,798, PR-AUC 0,459. Desempenho em dados reais: **DESCONHECIDO**. Rotas (SIMULAÇÃO, 30 instâncias): solver entregou mais lotes em 7/30 (vizinhos) e 3/30 (mesmo município), nunca menos; ver `docs/ROUTING.md`.

## 8. Bandit/Trivy
Bandit: 13 LOW → **0** (7 `nosec` justificados). pip-audit: 0/0. gitleaks: histórico 0; árvore 1 (senha literal do CI, corrigida) → 0. Trivy secret/misconfig: 0. **Trivy vulnerabilidades/imagem: não executado.** Detalhes: `security/reports/LEIA-ME.md`.

## 9. Pendências reais
1. Rodar `docker compose up` com Docker e confirmar o fluxo completo.
2. Executar o workflow no GitHub e corrigir o que falhar; só então chamar de "verde".
3. Trivy de vulnerabilidades e de imagens (resultado desconhecido).
4. **P2B-1** (scores/ranking expostos a todos os perfis) — Fase 3 Parte 1 §3.
5. TLS, rate limit, tokens com expiração/MFA, gerenciador de segredos, proteção de branch.
6. Rotas: malha viária real, várias ONGs/veículos, interface; cenário de mesmo município é degenerado.
7. Tipagem (mypy) não adotada; execução em Windows real não testada.
8. Parser/modelo em dados reais: desempenho desconhecido (sem rotulagem manual).

## 10. Próximo passo recomendado
Fechar primeiro as pendências 1–3 (rodar Docker e CI e corrigir o que aparecer). Só depois iniciar a Fase 3 Parte 1, começando pelos esquemas de resposta por perfil (P2B-1).
