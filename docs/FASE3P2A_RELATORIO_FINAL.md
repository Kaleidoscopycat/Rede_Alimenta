# Fase 3 · Parte 2 — Etapa A: relatório final

Escopo: dashboard do ADMIN, observabilidade, e2e local e rascunho de README/pitch. **Fora desta etapa:** Dockerfiles com `PORT`, RLS, `load_to_cloud`, `render.yaml`, `DEPLOY.md`, `smoke_cloud.py`, `docs/LICENCAS_DEMONSTRACAO.md`, banco/URL públicos e a Fase 4.

## 1. Alterações
* **API:** `/api/v1/admin/stats/*` (overview, donations-matches, meals-by-region, map, organizations, donors, public-data, territorial, ai, security) e `POST .../logistics/strategies`; todas só ADMIN, com auditoria `admin.access` (`stats.<tela>`).
* **Interface:** `app/page_dashboard.py` (11 telas + filtros UF/município/tipo ONG/tipo doador/categoria/origem/período), menu ampliado do ADMIN, layout largo só para o ADMIN, selos PÚBLICO/SIMULADO/MEDIDO.
* **Logística:** `routing/strategies.py` — ONG mais próxima × ranking híbrido × híbrido com rota (simulação reprodutível por semente).
* **Premissa de refeições:** 0,4 kg/refeição **centralizado** em `core/settings.ASSUMPTIONS` (`MEAL_KG_PER_MEAL`). *Defeito encontrado:* a Parte 1 tinha 0,4 fixo em `api/views.py` e nos schemas; corrigido.
* **Observabilidade:** `core/logging_setup.py` (JSON em `APP_ENV=production`, `X-Request-ID`, 500 genérico com `request_id`), eventos `ingestion.import_all`, `simulation.done`, `prediction.ranker`, `match.event`; pipelines/simulador usam a mesma configuração.
* **Segurança:** `api/security_reports.py` (indicador só com arquivos), `scripts/create_user.py --revoke <rótulo>` (auditoria `user.revoke`), STRIDE §14 (P3C-1…10), `security/reports/LEIA-ME.md` com as convenções `fase3a/` e `ci/antes|depois`.
* **Imagem da API:** `.dockerignore` deixa de excluir `security/reports` e `docker/Dockerfile.api` copia essa pasta (somente `COPY`; **sem** `PORT`, que é da Etapa B).
* **Docs:** `docs/DASHBOARD.md`, `docs/PITCH.md`, `README.md`.

## 2. Arquivos
Ver o `git status` ao final da resposta (modificados e novos listados separadamente).

## 3. Fontes de dados e selos
🟦 PÚBLICO: IPEA/OSC, RBBA, IBGE (municípios/população), PAA — 54.590 ONGs, 5.571 municípios, 27.855 indicadores, 7 fontes. 🟧 SIMULADO: doadores, lotes, desfechos, perfis e frota das ONGs (`simulation/`). 🟩 MEDIDO: nenhuma doação `USER_ENTERED` → a tela diz "Nenhuma doação real registrada."

## 4. Licenças
As licenças de IPEA/OSC, RBBA e centroides continuam **em revisão** (`docs/data/DATA_LICENSES.md`, NEEDS_REVIEW); uso exclusivamente acadêmico. O mapa não usa tiles nem chaves de terceiros, e nenhuma biblioteca nova foi adicionada. `docs/LICENCAS_DEMONSTRACAO.md` é da Etapa B.

## 5. Quantidade REAL × SIMULADA (carga usada no e2e local, tag `smoke`)
| Item | REAL (PÚBLICO) | SIMULADO | MEDIDO (USER_ENTERED) |
|---|---|---|---|
| Organizações | 54.590 | — | — |
| Perfis de ONG / veículos | — | 54.590 / 15.758 | 0 / 0 |
| Doadores | — | 1.000 | 0 |
| Doações / itens | — | 3.000 / 3.000 (+ as criadas pelo e2e) | 0 |
| Municípios / indicadores | 5.571 / 27.855 | — | — |

A carga completa (tag `main`) tem 8.000 doadores e 60.000 doações simuladas (`docs/data/IMPORT_REPORT_FASE2P1.json`).

## 6. Testes
**Validado localmente:** ruff `All checks passed!`; Bandit 0 achados (11.022 linhas; MÉDIA/ALTA = 0); pip-audit 0 vulnerabilidades (API e frontend); pytest **262 passed** (204 + 58 em duas rodadas, banco PostgreSQL local de teste), incluindo 22 de endpoints, 16 de telas (AppTest), 9 de observabilidade/segurança/revogação; e2e HTTP real com os três perfis (`docs/E2E_FASE3P2A_RESULTADO.json`): ADMIN 200 nas 10 telas + logística, 21 auditorias `stats.*`, DONOR e ORG 403 em todas, `X-Request-ID` presente.
**Só o CI ou o deploy confirmam:** build das imagens e `docker compose` (**Docker não está disponível aqui**), Trivy (fs e imagem; **sem Trivy local**), gitleaks, job `docker` do CI com o e2e atualizado, URL pública e banco em nuvem (Etapa B).

## 7. Métricas do modelo (rotuladas: calculadas sobre dados SIMULADOS; teste, 134.290 pares)
| | MRR | Top-1 | Top-3 | NDCG@3 |
|---|---|---|---|---|
| Aleatório (baseline) | 0,462 | 26,7% | 55,8% | 0,282 |
| ONG mais próxima (baseline) | 0,465 | 27,2% | 56,6% | 0,290 |
| Regra: elegível + categoria + distância (baseline) | 0,541 | 35,3% | 66,1% | 0,365 |
| Regressão logística | 0,649 | 48,8% | 76,1% | 0,464 |
| Random Forest | 0,681 | 53,2% | 78,7% | 0,498 |
| **HistGradientBoosting (escolhido)** | **0,695** | **54,6%** | **80,4%** | **0,515** |

Classificação (modelo escolhido): ROC-AUC 0,798 · PR-AUC 0,459 · F1 0,503. Parser (texto SIMULADO; "acurácia" só aqui): categoria 96,1% (visto) e 95,6% (família F4 nunca vista); sem `MANUALLY_LABELED`. Limitações: circularidade, lote misto desconhecido, ONGs por pseudônimo.

## 8. URL pública
**Não se aplica na Etapa A** (Etapa B).

## 9. Pendências
* Trivy de imagem do CI (4 HIGH → 0): para entrar no indicador, baixar os JSONs do GitHub Actions para `security/reports/ci/antes/` e `ci/depois/`; hoje o painel mostra **pendente**, sem estimativa.
* Validar build/Compose e o job `docker` do CI (o e2e agora checa o dashboard).
* Rotular manualmente textos reais (`MANUALLY_LABELED`); avaliar lote misto; rate limit e rotação de tokens (Fase 4).
* Arquivos temporários `_to_delete/` na raiz (pacotes de transferência de sessões anteriores) — apagar antes do commit; **não** versionar.
* Evolução futura (só documentada): lote misto por sublotes.

## 10. Próximo passo
Revisar o diff, fazer o commit com caminhos explícitos (lista de novos arquivos abaixo no `git status`) e iniciar a **Etapa B** (Dockerfiles com `PORT`, RLS, `load_to_cloud`, `render.yaml`, `DEPLOY.md`, `smoke_cloud.py`, licenças de demonstração).
