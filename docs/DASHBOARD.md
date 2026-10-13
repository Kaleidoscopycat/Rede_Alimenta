# Dashboard do ADMIN — Fase 3 Parte 2 · Etapa A

Painel do perfil **ADMIN** (Streamlit, `app/page_dashboard.py`). A interface só fala HTTP com `/api/v1/admin/stats/*`; **a barreira é a API**: DONOR e ORG recebem 403 (sem token, 401) e cada consulta grava `admin.access` em `audit_logs` (recurso `stats.<tela>`, parâmetros de consulta; nunca o token).

> Doadores, lotes e desfechos são **SIMULADOS**. ONGs, municípios e indicadores territoriais são **registros públicos reais** (licença em revisão; uso exclusivamente acadêmico). Nenhuma métrica aqui descreve desempenho no mundo real.

## 1. Selos de origem
| Selo | `data_origin` | Significa |
|---|---|---|
| 🟦 PÚBLICO | `PUBLIC` | fonte oficial (IPEA/OSC, RBBA, IBGE, PAA…) |
| 🟧 SIMULADO | `SIMULATED` | simulador documentado (`simulation/`), reprodutível por semente |
| 🟩 MEDIDO | `USER_ENTERED` | entrada real feita na plataforma |

Origens **nunca são somadas** num mesmo número. Sem nenhuma doação `USER_ENTERED`, as telas mostram **"Nenhuma doação real registrada."**

## 2. Indicadores pedidos
| Ref. | Indicador | Como é calculado | Observação |
|---|---|---|---|
| A | **kg ofertados** e **kg coletados** | soma de `quantity_kg` das doações cadastradas (ofertado) e das doações com match `COLLECTED` (coletado), por origem | "kg salvos" **não** é usado como rótulo |
| B | **Refeições por região** (macro, UF, município) | kg ÷ premissa da equipe (**0,4 kg/refeição**, `MEAL_KG_PER_MEAL`) | a premissa é exibida na tela; não é dado de fonte pública |
| C | **Métricas da IA** | lidas dos artefatos versionados (`ml/artifacts`) com os **nomes reais**: MRR, Top-1, Top-3, NDCG@3, ROC-AUC, PR-AUC, F1 (ranker); **acurácia só no parser** | rotuladas "calculadas sobre dados simulados"; baselines ao lado |
| D | **Tempo médio de match** | `match_events`: registro → 1ª proposta, proposta → resposta, registro → aceite; latência do ranking (média, p50, p95) | tempos de resposta de ONGs vêm de operadores de teste |
| E | **Vulnerabilidades mitigadas (SAST)** | antes − depois **somente** com os dois JSONs presentes (SHA-256 exibido) | Trivy de imagem do CI: ver §5 |

## 3. Telas (menu do ADMIN)
Overview · Doações e matches · Mapa · Organizações · Doadores · Dados públicos · Indicadores territoriais · IA · Recomendações · Logística · Segurança e sistema · Visão técnica (admin, da Fase 3 Parte 1).

Filtros (quando se aplicam): UF, município (IBGE), tipo de ONG, tipo de doador, categoria, origem e período.

* **Mapa** — sem mapa-base de terceiros (sem chave, sem licença extra): calor de ONGs, pontos de ONGs (limitados), doadores, doações (kg) e rotas de coleta planejadas. Localização de ONG/doador por **centroide de município** salvo exceções públicas (RBBA); distâncias são linha reta × desvio, **não rota viária**.
* **Recomendações** — o ADMIN escolhe um doador SIMULADO, informa o lote e recebe o ranking de ONGs (`POST /api/v1/predictions`, auditado). Não cria doação nem match.
* **Logística** — simulação reprodutível por semente (`POST /api/v1/admin/stats/logistics/strategies`, `routing/strategies.py`) que compara, sobre os mesmos lotes SIMULADOS e o mesmo relógio de referência:
  1. **A · ONG mais próxima** (regras eliminatórias reaplicadas; destinos inelegíveis são informados);
  2. **B · ranking híbrido** (elegibilidade + ML simulado + regras + distância, com reserva de capacidade);
  3. **C · híbrido com rota** (lotes da mesma ONG agrupados; vizinho mais próximo + OR-Tools, ambos verificados).
  Métricas: lotes entregues no prazo, km e minutos estimados, ONGs distintas, motivos de não entrega.
* **Segurança e sistema** — relatórios (Bandit, pip-audit, Trivy, gitleaks), pendências, auditoria das últimas 24 h e estado do serviço.

## 4. Limitações exibidas na tela de IA
1. **Circularidade** — os rótulos vêm de um simulador definido pela equipe.
2. **Lote misto** — o ranker foi avaliado só com lotes de uma categoria; desempenho em lote misto é **desconhecido** (a parcela de lotes mistos aparece quando há doações cadastradas pela plataforma).
3. **Sem `MANUALLY_LABELED`** — o parser nunca foi avaliado em texto real.
4. **ONGs por pseudônimo** — capacidade, horários e frota são declarados/simulados.

## 5. Segurança — como o indicador é calculado
`security/reports/antes` e `depois` (Fase 2) não são sobrescritos; o estado atual fica em `security/reports/fase3a/`. Para contar as **4 HIGH → 0** do Trivy de imagem do CI, coloque os JSONs baixados do GitHub Actions em `security/reports/ci/antes/` e `security/reports/ci/depois/`. Sem eles a tela mostra **pendente**, sem estimativa.

## 6. Configuração
| Variável | Padrão | Efeito |
|---|---|---|
| `MEAL_KG_PER_MEAL` | `0.4` | kg por refeição (premissa); valor ≤ 0 impede a inicialização |
| `APP_ENV` | `development` | `production` liga log JSON; qualquer outro valor é recusado |
| `LOG_LEVEL` | `INFO` | nível de log |
| `SECURITY_REPORTS_DIR` | `security/reports` | origem dos relatórios lidos pela API |

## 7. Observabilidade
Log de requisição em uma linha (método, caminho **sem query string**, status, duração), `X-Request-ID` aceito só no formato seguro (`^[A-Za-z0-9._-]{8,64}$`) ou gerado, devolvido na resposta e presente em todo log da requisição; erros inesperados viram 500 genérico com o `request_id`. Eventos estruturados (`evt`): `ingestion.import_all`, `simulation.done` (semente, versões, contagens), `prediction.ranker` (latência, versão) e `match.event` (tipo, estados). Nenhum evento registra token, corpo, IP ou texto digitado.

## 8. Evolução futura (não implementada)
**Lote misto por sublotes**: dividir uma doação com várias categorias em sublotes por categoria/validade/refrigeração, ranquear e rotear cada sublote separadamente e acompanhar a parcela atendida. Hoje o lote misto é tratado como um único lote (a ONG precisa aceitar todas as categorias; o ML usa a categoria predominante).

## 9. Validado localmente × só CI/deploy
Veja o relatório final da Etapa A (`docs/FASE3P2A_RELATORIO_FINAL.md`).
