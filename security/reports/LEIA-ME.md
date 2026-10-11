# Relatórios de segurança — antes × depois (Fase 2 Parte 2)

Fonte do painel "vulnerabilidades mitigadas": os JSON desta pasta (`antes/` e `depois/`) e `resumo_antes_depois.json`.
**Escopo:** código-fonte do projeto (Python) e dependências declaradas. Nada aqui mede a segurança em produção.

| Verificação | Ferramenta | Antes | Depois | Observação |
|---|---|---|---|---|
| SAST Python | Bandit 1.9.4 | 13 achados (13 LOW, 0 MEDIUM, 0 HIGH; 6.432 linhas) | **0 achados** (7.388 linhas; 7 `nosec` justificados) | 7 corrigidos no código; 6 suprimidos com justificativa em `SUPRESSOES.md`; +1 supressão em código novo (`routing/benchmark.py`, B311) |
| Dependências | pip-audit 2.10.1 | 0 vulnerabilidades conhecidas (102 dependências) | 0 (100 dependências, já com `ortools`; `mypy` removido) | Base de avisos do PyPI/OSV na data da execução |
| Segredos (histórico Git) | gitleaks 8.30.1 | 0 | 0 | |
| Segredos (árvore de arquivos) | gitleaks `--no-git` | — | 0 (após remover uma senha literal efêmera do workflow, tratada como achado) | O Postgres do CI agora usa senha gerada na execução (`openssl rand`) |
| Segredos/Misconfig em Dockerfiles | Trivy 0.75.0 (`fs`, scanners secret+misconfig) | 0 | 0 | Execução local apenas desses dois scanners |
| Estilo/erros | Ruff 0.17.0 | (sem linha de base) | `All checks passed!` | Regras E,F,W,B,S |
| **Vulnerabilidades em dependências/imagens** | **Trivy (`fs` vuln e `image`)** | **NÃO EXECUTADO localmente** | **NÃO EXECUTADO localmente** | Banco do Trivy inacessível no ambiente de desenvolvimento; executa no CI (job `docker`). **Pendência real.** |

## Bandit — o que foi corrigido (antes → depois)
| Arquivo | Regra | Tratamento |
|---|---|---|
| `database/importers.py` (2×), `database/session.py`, `ml/dataset.py`, `scripts/e2e_flow.py`, `scripts/measure_latency.py` | B101 (`assert` em código de produção/script — removido com `-O`) | substituído por exceção explícita |
| `ml/semantic/validity.py` | B110 (`try/except/pass`) | passa a registrar a falha em log; o comportamento seguro (campo ausente → bloqueio) foi mantido |
| `api/auth.py` | B105 | suprimido: prefixo público do token (não é segredo) |
| `scripts/bootstrap_db.py`, `scripts/e2e_flow.py` | B404, B603 | suprimidos: argumentos fixos, sem shell |
| `simulation/generator.py` | B311 | suprimido: PRNG reprodutível exigido pelo simulador |

Suíte de testes após as correções: ver relatório final (`docs/FASE2_P2_RELATORIO_FINAL.md`).
