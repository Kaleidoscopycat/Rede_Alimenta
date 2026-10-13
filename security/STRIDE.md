# Modelagem de ameaças STRIDE — Rede Alimenta IA (Fase 1 → Fase 2 Parte 2 / Checkpoint 2)

**Escopo:** fluxo DOADOR → ONG (a distribuição ONG → beneficiário está fora de escopo). **Estado (Fase 1):** MVP local; ainda não havia autenticação, banco de dados, nuvem nem CI/CD. **Atualizado na Fase 2 Parte 2** (§11 e §12): API autenticada, PostgreSQL, interface, rotas de coleta, contêineres e CI/CD (workflow escrito, **ainda não executado no GitHub**; imagens **ainda não construídas** no ambiente de desenvolvimento). Os status das §2–§10 são os da Fase 1, exceto onde a nota *(atualizado)* indica o contrário. Este documento classifica o que **já está mitigado no código**, o que é **risco aceito nesta fase** e o que **fica para fases futuras** (DevSecOps).

**Escalas:** Impacto e Probabilidade em Baixo / Médio / Alto, avaliadas qualitativamente pela equipe (não medidas). **Status:** `IMPLEMENTADO` (existe no repositório e é testado), `PARCIAL`, `PENDENTE`.

## 1. Ativos e fronteiras de confiança

| Ativo | Sensibilidade | Onde está hoje |
|---|---|---|
| Cadastro de organizações (IPEA/OSC, RBBA) | Público (pessoa jurídica); IDs pseudonimizados `ong_id` | `data/gold/organizations.parquet` |
| Atributos declarados das ONGs, frota, desfechos | **SIMULADOS** (`data_origin=SIMULATED`) | `data/simulated/*` |
| Texto livre do doador | Pode conter dado pessoal inserido por engano | Entrada de `POST /api/v1/predict` (campo `descricao_texto`) |
| Artefatos do modelo (`model.joblib`, `semantic_parser.joblib`) | Integridade crítica (pickle executa código ao carregar) | `ml/artifacts/` |
| Dados RAW + checksums | Integridade (cadeia de evidência) | `data/raw/`, `data/metadata/raw_checksums.json` |
| Código e dependências | Integridade | repositório local |

Fronteiras: (F1) cliente ↔ API; (F2) pipelines ↔ fontes públicas na internet; (F3) pipeline/treino ↔ disco; (F4) API ↔ artefatos do modelo; (F5) futura: API ↔ banco, ONG/doador ↔ cadastro, CI/CD ↔ registro de imagens.

## 2. API (`api/`) — F1

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Fase |
|---|---|---|---|---|---|---|---|
| A1 | S | Cliente se passa por doador/ONG; endpoints abertos | Médio | Alta | Nesta fase não há login. Fase 2: autenticação (OIDC/JWT), papéis doador/ONG/admin, chaves por cliente | **(atualizado)** autenticação por token implementada na Fase 2 Parte 1 — ver P2-1…P2-4; OIDC/JWT segue PENDENTE (P2-3) | 2 |
| A2 | T | Payload adulterado ou com campos extras (mass assignment) | Médio | Média | Pydantic com `extra="forbid"`, faixas e tipos estritos, enum de categorias, janelas validadas (`tests/test_api.py::test_entradas_invalidas`) | IMPLEMENTADO | 1 |
| A3 | R | Sem trilha de auditoria de quem pediu qual recomendação | Médio | Média | Log estruturado com `model_version`/`data_version`; Fase 2: log de auditoria imutável com identidade e correlation-id | PARCIAL | 2 |
| A4 | I | Mensagens de erro vazam detalhes internos / caminhos / stack | Médio | Média | Handler global devolve `"erro interno"` genérico; detalhe só no log (`api/main.py`) | IMPLEMENTADO | 1 |
| A5 | I | Resposta expõe dado pessoal | Alto | Baixa | Resposta contém apenas ID pseudonimizado, tipo, UF, município e distância; teste `test_resposta_nao_expoe_pessoa_fisica`. Não há CNPJ, razão social, endereço ou telefone na saída | IMPLEMENTADO | 1 |
| A6 | I | Inferência de endereço/localização exata de ONG | Médio | Média | Localização é `MUNICIPALITY_CENTROID` para 99,7% das ONGs; coordenada exata só para bancos RBBA já públicos | IMPLEMENTADO | 1 |
| A7 | D | Flood de requisições / `top_n` e texto grandes | Médio | Média | Limites: `descricao_texto` ≤ 500 car., `top_n` ≤ 15, `quantidade_kg` ≤ 100 000. Rate limiting e WAF: Fase 2/3 | PARCIAL | 2 |
| A8 | D | Regex/dateparser em texto adversarial (ReDoS) | Médio | Baixa | Comprimento máximo do texto; regex simples sem aninhamento; revisão e timeout na Fase 2 | PARCIAL | 2 |
| A9 | E | Acesso a endpoints administrativos | Alto | Baixa | Não há endpoints administrativos; Swagger exposto só em ambiente de desenvolvimento (desativar `/docs` em produção) | PARCIAL | 3 |
| A10 | T/I | CORS aberto, cabeçalhos de segurança ausentes, tráfego sem TLS | Médio | Média | Fase 3: TLS na borda, HSTS, CORS restrito, cabeçalhos de segurança | PENDENTE | 3 |

## 3. Cadastro de doadores e ONGs (futuro)

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Fase |
|---|---|---|---|---|---|---|---|
| C1 | S | Cadastro falso de ONG para desviar doações | Alto | Média | Validação cruzada com cadastros públicos (IPEA/OSC, RBBA) e verificação documental; aprovação manual | PENDENTE | 2 |
| C2 | T | ONG manipula atributos declarados (capacidade, câmara fria, categorias) para ganhar prioridade | Alto | Alta | O simulador já modela viés/ruído do declarado (cenário "otimista"); modelo treinado com declarado ruidoso; Fase 2: verificação por histórico real de coletas e auditoria | PARCIAL | 2 |
| C3 | I | Coleta excessiva de dados pessoais (LGPD) | Alto | Média | Minimização: só pessoa jurídica; sem pessoa física, sem restrição religiosa, sem dados de beneficiários; base legal e DPIA antes de dados reais | PARCIAL | 2 |
| C4 | R | Doador/ONG nega aceite ou coleta | Médio | Média | Fase 2: registro de eventos com carimbo de tempo | PENDENTE | 2 |
| C5 | E | Doador visualiza dados de outras ONGs/doadores | Alto | Média | Autorização por objeto (BOLA/IDOR) a ser exigida e testada | PENDENTE | 2 |

## 4. Dados em trânsito e em repouso

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Fase |
|---|---|---|---|---|---|---|---|
| D1 | I | Dados em repouso sem criptografia (disco local, backups) | Médio | Média | Dados atuais são públicos ou simulados; Fase 3: criptografia em repouso e gestão de chaves antes de qualquer dado real sensível | PENDENTE | 3 |
| D2 | T/I | Tráfego sem TLS | Médio | Média | Downloads das fontes usam HTTPS; API local sem TLS (aceito); Fase 3: TLS fim a fim | PARCIAL | 3 |
| D3 | I | Segredos em código/repositório | Alto | Baixa | Nenhum segredo existe hoje (nenhuma chave de API usada); `.gitignore` e varredura de segredos no CI na Fase 2 | PARCIAL | 2 |
| D4 | T | Parquet/CSV alterado manualmente | Médio | Média | Checksums do RAW verificados (`tests/test_ingestion.py`); manifesto com SHA-256; camadas derivadas reproduzíveis por `pipelines.run_all` | IMPLEMENTADO | 1 |

## 5. Datasets e pipelines (cadeia de suprimento de dados) — F2/F3

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Fase |
|---|---|---|---|---|---|---|---|
| P1 | T | Fonte pública alterada/comprometida no download | Alto | Baixa | SHA-256 por arquivo, comparação com baseline; divergência é registrada e não sobrescreve o RAW (`pipelines/download.py`); HTTPS | IMPLEMENTADO | 1 |
| P2 | S | Fonte falsa (mirror não oficial) | Alto | Baixa | Apenas fontes APPROVED, URLs registradas no manifesto; centroides de município de terceiros (Kelvins) marcados como PROXY e licença registrada | IMPLEMENTADO | 1 |
| P3 | T | Envenenamento por registros anômalos (coordenadas fora do Brasil, duplicados) | Médio | Média | Relatório automático de qualidade; `geo_quality`; `rankable_by_distance` exige coordenada válida | IMPLEMENTADO | 1 |
| P4 | I | PII em dados públicos (IPEA/OSC) | Médio | Baixa | Apenas campos de pessoa jurídica no silver/gold; `ong_id` pseudonimizado; teste de ausência de colunas PII; varredura por valor (`quality/data_quality.py`) | IMPLEMENTADO | 1 |
| P5 | R | Sem rastreabilidade de origem | Médio | Média | Colunas `data_origin`, `source_id`, `pipeline_version`; manifesto com URL, timestamp, checksum, versão, tamanho e nº de registros | IMPLEMENTADO | 1 |
| P6 | D | Falha de download interrompe pipeline | Baixo | Média | Falhas registradas, camadas anteriores preservadas; execução idempotente | IMPLEMENTADO | 1 |
| P7 | T | Dependências Python comprometidas | Alto | Baixa | Versões fixadas e SCA (pip-audit) a adicionar no CI | PENDENTE | 2 |

## 6. Simulador

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Fase |
|---|---|---|---|---|---|---|---|
| S1 | I | Dado SIMULADO confundido com REAL e usado como evidência | Alto | Média | `data_origin=SIMULATED`, `generator_version`, `seed`, `dataset_version` em todas as tabelas (testado); métricas rotuladas "calculadas sobre dados SIMULADOS"; API devolve `data_origin` | IMPLEMENTADO | 1 |
| S2 | T | Alteração silenciosa de parâmetros muda os resultados | Médio | Média | Parâmetros versionados com hash (`params_hash`), `run_params.json`, determinismo por seed (testado) | IMPLEMENTADO | 1 |
| S3 | I | Geração acidental de PII (nomes, CPF, e-mail) nos textos | Alto | Baixa | Sem Faker; teste T2 (zero CPF/CNPJ/telefone/e-mail/URL); ONGs e municípios sempre reais, pessoas físicas inexistentes | IMPLEMENTADO | 1 |
| S4 | I | Viés/discriminação incorporados às premissas (ex.: restrição religiosa) | Alto | Média | Sem atributo religioso; sem `aceita_alergenicos`; premissas documentadas com fonte/PREMISSA e revisão pela equipe | IMPLEMENTADO | 1 |

## 7. Modelo de IA e parser semântico — F4

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Fase |
|---|---|---|---|---|---|---|---|
| M1 | T | Artefato `.joblib` substituído (pickle executa código arbitrário ao carregar) | Alto | Baixa | Hash SHA-256 do modelo verificado no carregamento (`Ranker.__init__`; testado); carregar só artefatos produzidos pela própria equipe; Fase 2: assinatura (Sigstore/cosign) e bucket com acesso restrito; considerar ONNX | PARCIAL | 2 |
| M2 | T | Envenenamento de treino (rótulos de feedback falsos) | Alto | Média | Fase atual treina só em simulado; em produção exigir confirmação humana, detecção de anomalias e reprocessamento controlado | PENDENTE | 3 |
| M3 | I | Extração de modelo/inversão por muitas consultas | Médio | Baixa | Resposta devolve top-N limitado e probabilidades arredondadas; rate limit e autenticação na Fase 2 | PARCIAL | 2 |
| M4 | T | Entrada adversarial no texto (instruções, números absurdos, validade falsa para esconder perecibilidade) | Alto | Média | Parser com confiança e fila de confirmação humana (`needs_human_confirmation`); alerta de inconsistência; bloqueio de lote vencido; custo assimétrico (subestimar perecibilidade é pior) | IMPLEMENTADO | 1 |
| M5 | I | Falsa sensação de precisão (métrica simulada tratada como real) | Alto | Alta | Campo `aviso` em toda resposta; `/api/v1/model/info` expõe `data_origin`; relatório explicita circularidade | IMPLEMENTADO | 1 |
| M6 | R | Decisão sem explicação | Médio | Média | `factors` (oclusão por grupos de fatores) e `elegivel_regra`; importâncias globais em `metrics.json` | IMPLEMENTADO | 1 |
| M7 | E | Recomendar ONG inadequada para alimento de risco (cadeia fria) | Alto | Média | Regras de elegibilidade sobre refrigeração declarada, capacidade e categoria; sempre confirmação humana antes do despacho; avaliar segurança alimentar com especialista | PARCIAL | 2 |
| M8 | D | Modelo indisponível derruba o serviço | Médio | Baixa | `/ready` retorna 503 se o modelo não carregou; `/health` independente | IMPLEMENTADO | 1 |

## 8. Infraestrutura futura (CI/CD, contêineres, nuvem)

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação planejada | Status | Fase |
|---|---|---|---|---|---|---|---|
| I1 | T | Pipeline de CI/CD comprometido | Alto | Baixa | Ações fixadas por hash, permissões mínimas, revisão obrigatória | **PARCIAL (atualizado)** — ações fixadas por SHA e `permissions: contents: read` IMPLEMENTADOS em `.github/workflows/ci.yml` (validado com actionlint); **workflow não executado no GitHub**; revisão obrigatória/proteção de branch PENDENTES (configuração do repositório) | 2 |
| I2 | E | Contêiner executa como root, imagem desatualizada | Alto | Média | Usuário não-root, imagem mínima, scan (Trivy), SBOM | **PARCIAL (atualizado)** — usuário não-root (uid 10001), base `python:3.10-slim`, `cap_drop: ALL` e `no-new-privileges` escritos; Bandit/Trivy no CI; **imagem não construída nem escaneada (Trivy) localmente**; SBOM PENDENTE | 3 |
| I3 | I | Segredos de produção expostos | Alto | Média | Gerenciador de segredos, rotação, scan de segredos no CI | **PARCIAL (atualizado)** — sem segredos em imagem/repositório (`.env.example` sem credenciais, `.dockerignore`, gitleaks no CI e gitleaks local limpo, senha do Postgres do CI gerada na execução); gerenciador de segredos/rotação PENDENTES | 3 |
| I4 | D | Sem observabilidade/alertas | Médio | Média | Métricas, logs centralizados, alertas, SLO | PENDENTE | 3 |
| I5 | T/I | Configuração de nuvem permissiva | Alto | Média | IaC com verificação (tfsec/Checkov), princípio do menor privilégio | PENDENTE | 3 |

## 9. Riscos residuais aceitos no Checkpoint 1

1. **API sem autenticação, rate limit e TLS** (A1, A7, A10): aceitável somente porque roda localmente com dados públicos/simulados.
2. **Artefatos em `joblib`** (M1): mitigado por hash, mas sem assinatura.
3. **Declarado das ONGs 100% simulado**: toda a avaliação de risco C2 depende de dados reais de cadastro/coleta que ainda não existem.
4. **Textos de doação 100% simulados** (M4): robustez a entradas reais não foi medida (conjunto `MANUALLY_LABELED` ausente).

## 10. Rastreabilidade para testes

`tests/test_api.py` (A2, A4, A5, M5, M8), `tests/test_ingestion.py` (D4, P1, P5), `tests/test_transform.py` (P3, P4), `tests/test_simulator.py` (S1–S4), `tests/test_features_model.py` (M1, M6, ausência de vazamento de latentes), `tests/test_semantic.py` (M4). Ameaças marcadas PENDENTE não têm teste e devem entrar no backlog das próximas fases.

## 11. Fase 2 · Parte 1 — plataforma, API autenticada, PostgreSQL, motor de match

Atualiza A1/A3 (autenticação mínima e auditoria, **implementadas**). A7/A10 permanecem; **TLS e rate limit estão PENDENTES** (Parte 2/Fase 3).

| ID | STRIDE | Ameaça | Impacto | Prob. | Mitigação | Status | Teste |
|---|---|---|---|---|---|---|---|
| P2-1 | S | Uso de endpoints sem identidade | Alto | Alta | Token por usuário (`rai_…`, 256 bits) exigido em todo `/api/v1`; públicos só `/health`, `/ready`, OpenAPI | IMPLEMENTADO | `test_p2_auth.py`, `test_contrato_openapi` |
| P2-2 | S/I | Vazamento/roubo do token | Alto | Média | Só o hash SHA-256 é gravado; token exibido uma vez; nunca registrado em log/auditoria; segredos só por variável de ambiente | PARCIAL | `test_token_invalido_401_e_nao_grava_token` |
| P2-3 | S | **Limitação do esquema:** tokens estáticos, sem expiração, rotação, escopos finos ou revogação em massa | Médio | Média | Aceito nesta fase; migrar para OIDC/JWT com expiração e rotação (Fase 3) | **PENDENTE (limitação conhecida)** | — |
| P2-4 | E | Perfil errado ou acesso a recurso de outro usuário (IDOR) | Alto | Média | Autorização por perfil (DONOR/ORG/ADMIN) e por posse do recurso (403); ONG só vê a própria proposta | IMPLEMENTADO | `test_perfil_errado_403`, `test_recurso_de_outro_usuario_403` |
| P2-5 | R | Falta de trilha de falhas de acesso | Médio | Média | `audit_logs` (sessão separada, sobrevive a rollback) para 401/403 e operações de match, sem o token | IMPLEMENTADO | `test_p2_auth.py` |
| P2-6 | D | Flood de requisições / abuso de `/matches` | Médio | Média | Limites de entrada (Pydantic) já existem; **rate limit NÃO implementado** | **PENDENTE** | — |
| P2-7 | I/T | Tráfego sem TLS entre UI/API/banco | Alto | Média | Execução local (127.0.0.1) apenas; **TLS NÃO implementado** | **PENDENTE** | — |
| P2-8 | T | Dado simulado gravado como real / USER_ENTERED | Alto | Média | `CHECK` no banco (SIMULATED exige generator/dataset/seed; USER_ENTERED os proíbe); contas demo só operam SIMULATED; origem herdada do doador | IMPLEMENTADO | `test_p2_db_import.py` |
| P2-9 | T | Reserva de capacidade duplicada (corrida) | Médio | Média | Reserva em transação com `SELECT … FOR UPDATE` e reavaliação das regras no momento da proposta | IMPLEMENTADO | `test_concorrencia_nao_ultrapassa_capacidade` |
| P2-10 | T | Doação vencida/sem validade vira match | Alto | Média | Regras R-VAL-1/2 e revalidação no match; match só após confirmação humana | IMPLEMENTADO | `test_p2_parser_api.py`, `test_validade_vence_antes_do_match` |
| P2-11 | I | Sugerir que alimento é próprio para consumo | Alto | Baixa | Avisos em toda resposta de parse/match: a plataforma não atesta segurança do alimento | IMPLEMENTADO | `test_scores_separados_e_final_ponderado` |
| P2-12 | I | Entidade pública tratada como cliente | Médio | Média | `platform_status = PUBLIC_RECORD`; regra `E_NAO_CADASTRADA` para doações reais | IMPLEMENTADO | `test_registro_publico_so_nao_cadastrada_para_doacao_real` |
| P2-13 | I | Dependências novas (SQLAlchemy, Alembic, psycopg, Streamlit, scipy) | Médio | Média | Versões fixadas em `requirements.txt`; **varredura de dependências/SAST (Bandit/Trivy) fica para a Parte 2** | **PARCIAL (atualizado na Parte 2)** — pip-audit (0 vulnerabilidades em 100 dependências) e Bandit (0 achados) executados localmente, com relatórios antes/depois em `security/reports/`; **Trivy de dependências/imagem NÃO executado localmente (pendente no CI)** | — |

## 12. Fase 2 · Parte 2 — rotas de coleta, contêineres, CI/CD, administração e deploy

**Severidade** é qualitativa (Impacto × Probabilidade), avaliada pela equipe. **Status:** `IMPLEMENTADO` (existe no repositório e foi verificado como indicado), `PARCIAL`, `PENDENTE`. Itens verificados só por inspeção ou emulação dizem isso na coluna Verificação.

### 12.1 Risco registrado na validação da Parte 1 — divulgação de informação (MITIGADO na Fase 3 Parte 1 — ver §13)

| ID | STRIDE | Ameaça | Impacto | Prob. | Severidade | Mitigação planejada | Status | Verificação |
|---|---|---|---|---|---|---|---|---|
| **P2B-1** | **I** | **Divulgação de informação:** (situação encontrada na Parte 1) a API entregava a qualquer perfil autenticado os scores internos da IA, os componentes das regras, os pesos, a elegibilidade e o ranking completo de ONGs; a ONG recebia também a posição no ranking. | Médio–Alto | Alta | **ALTA** | **Fase 3 Parte 1, seção 3 (Etapa A):** `response_model` por perfil na API (`api/schemas_views.py`): DONOR vê só a situação e a ONG que aceitou; ORG vê a doação, análise textual e a própria candidatura sem scores nem posição; ranking, scores, modelo e predictions só ADMIN, com auditoria `admin.access`. | **IMPLEMENTADO (Etapa A)** | `tests/test_p3a_visibilidade_perfil.py` (substitui o antigo `test_p2b_divulgacao_scores_pendente.py`, que era *xfail* estrito); e2e com tokens por perfil verifica 403 nas rotas ADMIN e ausência de scores. Detalhes: `docs/ROLE_VISIBILITY.md`. Residual: ver P3A-9 e P3A-10. Complemento da Etapa B: P3A-13 (saída do parser fora das respostas do doador). |

### 12.2 Rotas de coleta (`routing/`, `api/routers/routes.py`) — F1/F5

| ID | STRIDE | Ameaça | Sev. | Mitigação | Status | Verificação |
|---|---|---|---|---|---|---|
| P2B-2 | E | ONG planeja ou lê rota de outra ONG (IDOR); doador acessa rotas | Alta | Só `ORG`/`ADMIN`; `ORG` limitada às doações **aceitas pela própria ONG** e a veículos da própria ONG; GET devolve 403 para rota de outra ONG | IMPLEMENTADO | `tests/test_p2b_routes_api.py` (403/401) |
| P2B-3 | T | Payload adulterado (campos extras, listas enormes, margens absurdas) | Média | `extra="forbid"`, 1–12 doações, `safety_margin_h` 0–48 h, UUIDs validados | IMPLEMENTADO | `test_validacao_de_entrada` |
| P2B-4 | T | Rota que viola capacidade, janela, validade ou refrigeração (risco de segurança alimentar) | Alta | Verificador independente (`routing.core.evaluate`) reprova qualquer rota inviável; solver cai para o baseline se reprovado; lotes que não cabem ficam em `unassigned` com motivo; margem de segurança configurável | IMPLEMENTADO | `tests/test_p2b_routing_core.py`, `test_lote_refrigerado_em_veiculo_comum…`, `test_prazo_de_validade…` |
| P2B-5 | D | Solver consome CPU (planejamento repetido com muitos pontos) | Média | Limite de tempo do solver (`ROUTE_SOLVER_TIME_LIMIT_S`, padrão 3 s), no máximo 12 paradas e horizonte de 12 h; **sem rate limit** (ver P2-6) | PARCIAL | limite de paradas testado; tempo medido no benchmark; rate limit PENDENTE |
| P2B-6 | I/T | Rota SIMULADA apresentada como real ou gravada como `USER_ENTERED` | Alta | `data_origin` da rota = `USER_ENTERED` só se **todas** as entradas forem; senão `SIMULATED` com rastreio (gerador/semente/dataset); rótulo "SIMULAÇÃO … estimativas, não rota viária" em toda resposta; `CHECK` no banco | IMPLEMENTADO | `test_plano_com_sucesso_persiste_solver_e_baseline` |
| P2B-7 | I | Coordenadas dos doadores nas paradas são entregues a `ORG`/`ADMIN` | Média | Hoje: centroide municipal SIMULADO (`location_precision` informado). Para dados reais, restringir a localização exata ao pós-aceite e por perfil na Fase 3 | PENDENTE (para dados reais) | — |
| P2B-8 | R | Planejamento sem trilha | Média | Auditoria `route.plan` (OK/DENIED) com papel, recurso e código; parâmetros e versão do algoritmo gravados na rota | IMPLEMENTADO | `test_rota_registra_auditoria` |
| P2B-9 | T | Estimativa de tempo/distância tratada como viária | Média | Metodologia declarada (haversine × desvio ÷ velocidade, igual à Parte 1), gravada em `routes.distance_basis`/`parameters`; OSRM/OSM (ODbL) fica como extensão | IMPLEMENTADO (limitação documentada) | `test_premissas_iguais_as_da_parte_1` |

### 12.3 Contêineres, CI/CD e dependências — F5

| ID | STRIDE | Ameaça | Sev. | Mitigação | Status | Verificação |
|---|---|---|---|---|---|---|
| P2B-10 | E | Contêiner como root / capacidades excessivas | Alta | `USER` uid 10001, `cap_drop: ALL`, `no-new-privileges`, imagem `slim` multi-estágio, apenas os módulos necessários copiados | PARCIAL | Revisão do Dockerfile/Compose + Trivy misconfig local limpo; **imagem não construída aqui** (sem Docker); build no CI |
| P2B-11 | I | Segredos na imagem ou no repositório | Alta | `.dockerignore` exclui `.env`, dados e testes; `.env.example` sem credenciais; senha do Postgres do CI gerada na execução; gitleaks (histórico e árvore) limpo | IMPLEMENTADO | gitleaks e Trivy secret locais; `security/reports/depois/` |
| P2B-12 | I/E | Banco exposto ao host/rede | Alta | Compose padrão **não publica** a porta do Postgres; API/frontend ligados a `127.0.0.1`; credenciais por `.env`; `docker-compose.ci.yml` publica o banco só em `127.0.0.1` no CI | PARCIAL | Revisão do Compose; **`docker compose up` não executado aqui** |
| P2B-13 | T | Cadeia de suprimentos do CI/CD (ação comprometida, tag móvel) | Alta | Ações fixadas por SHA, `permissions: contents: read`, binários baixados com checksum (gitleaks), versões fixadas | PARCIAL | actionlint limpo; **workflow não executado no GitHub**; proteção de branch/revisão obrigatória PENDENTES |
| P2B-14 | T/I | Dependências ou imagem base vulneráveis | Alta | pip-audit e Bandit no CI e localmente (antes/depois em `security/reports/`); Trivy `fs` e `image` no CI com *gate* em CRITICAL corrigível | PARCIAL | pip-audit 0 / Bandit 0 locais; **Trivy de vulnerabilidades não executado** (DB inacessível localmente) |
| P2B-15 | T | Alerta suprimido sem registro | Média | Toda supressão tem justificativa em `security/reports/SUPRESSOES.md` | IMPLEMENTADO | Bandit: 7 `nosec`, todos listados |
| P2B-16 | T | Migrações divergentes entre ambientes | Média | Alembic versionado (0001, 0002); serviço `migrate` no Compose antes da API; teste de *head* | IMPLEMENTADO (testes locais) | `test_migration_head_e_tabelas`; execução no Compose pendente |
| P2B-17 | I | Mypy/tipagem como controle | Baixa | **Não adotado** (falha interna da ferramenta); registrado | NÃO ADOTADO | — |

### 12.4 Dados, licenças, administração e deploy

| ID | STRIDE | Ameaça | Sev. | Mitigação | Status | Verificação |
|---|---|---|---|---|---|---|
| P2B-18 | I | Redistribuição de bases brutas com licença **não confirmada** (NEEDS_REVIEW, `publication_cleared=false`) | Alta | `data/` fora do repositório e das imagens (`.gitignore`/`.dockerignore`); nenhum endpoint ou botão de exportação/download de bases brutas; aviso acadêmico visível na interface; indicadores agregados na exibição pública | IMPLEMENTADO | `tests/test_p2b_uso_academico.py`; `docs/data/DATA_LICENSES.md` |
| P2B-19 | E | Conta ADMIN com poder total (criar usuários, ver tudo) sem MFA, token estático sem expiração | Alta | Criação de usuários por endpoint de ADMIN e por `scripts/create_user.py`; ações auditadas; **sem MFA, expiração ou rotação** (P2-3) | PARCIAL | `test_p2_auth.py`; OIDC/MFA PENDENTES |
| P2B-20 | I/T | Deploy sem TLS, sem rate limit, sem WAF; segredos de produção | Alta | **Não há deploy em nuvem nesta parte**; o Compose é de desenvolvimento/demonstração local (`127.0.0.1`). TLS, rate limit, WAF, gerenciador de segredos e IaC verificada permanecem PENDENTES (P2-6, P2-7, I3, I5) | **PENDENTE** | — |
| P2B-21 | T | Artefatos `joblib` (modelo/parser) comprometidos ao serem carregados no contêiner | Alta | Verificação de *hash* na carga (M1) e artefatos copiados de caminho fixo; sem assinatura | PARCIAL | `tests/test_features_model.py` |
| P2B-22 | I | Métrica de dados simulados lida como desempenho real | Média | Rótulo "calculada sobre dados simulados" em relatórios, API (`/model/info`) e benchmark de rotas; MANUALLY_LABELED não existe | IMPLEMENTADO | `docs/MODEL_REPORT.md`, `docs/ROUTING_BENCHMARK.json` |

### 12.5 Riscos residuais ao final da Parte 2
1. **P2B-1** (scores/ranking expostos a todos os perfis) — mitigado na Fase 3 Parte 1 (Etapa A); ver §13.
2. TLS, rate limit, autenticação com expiração/rotação/MFA e gerenciador de segredos (P2-3, P2-6, P2-7, P2B-19, P2B-20).
3. Resultados do Trivy (vulnerabilidades de dependências e imagens) e a execução real do pipeline no GitHub e do `docker compose up` — **ainda não verificados** (ver `docs/FASE2_P2_RELATORIO_FINAL.md`).
4. Desempenho do parser e do modelo em textos e dados **reais** é **desconhecido** (sem rotulagem manual; toda métrica é sobre dados simulados).

### 12.6 Rastreabilidade para testes (Parte 2)
`tests/test_p2b_routing_core.py` (P2B-4, P2B-9), `tests/test_p2b_routes_api.py` (P2B-2, P2B-3, P2B-4, P2B-6, P2B-8), `tests/test_p3a_visibilidade_perfil.py` (P2B-1; antes *xfail* estrito em `test_p2b_divulgacao_scores_pendente.py`, hoje exigido), `tests/test_portabilidade.py` (portabilidade do `streamlit run`), `tests/test_p2b_uso_academico.py` (P2B-18).

## 13. Fase 3 · Parte 1 (Etapas A e B) — doação com itens, visibilidade por perfil e interface

**Status:** `IMPLEMENTADO` = no repositório e verificado como indicado; `PARCIAL`; `PENDENTE`. Verificações marcadas **CI** só serão confirmadas no GitHub (não há Docker neste ambiente).

| ID | STRIDE | Ameaça | Sev. | Mitigação | Status | Verificação |
|---|---|---|---|---|---|---|
| P3A-1 | I | Doador ou ONG recebe scores, ranking, elegibilidade, pesos, latências ou posição | Alta | Schemas de resposta por perfil (`DonorMatchView`, `OrgMatchView`, `AdminMatchView`, união discriminada por `perfil`); o `response_model` descarta chaves extras (defesa em profundidade); eventos do doador/ONG sem `detail`, `ong_id` e `rank_position` | IMPLEMENTADO | `tests/test_p3a_visibilidade_perfil.py` |
| P3A-2 | E | DONOR/ORG usa rotas exclusivas do ADMIN (`/matches/{id}/ranking`, `/predictions`, `/model/info`) | Alta | `require_roles("ADMIN")`; negativas auditadas (`authz.role_denied`) | IMPLEMENTADO | `test_apenas_admin_ve_ranking_modelo_e_predictions`, `test_negativas_de_acesso_sao_auditadas`; e2e |
| P3A-3 | R | Acesso do ADMIN a dados restritos sem trilha | Média | `audit_admin=` em `require_roles` grava `admin.access` (recurso e query; nunca o token) | IMPLEMENTADO | `test_acesso_admin_e_auditado_sem_token`; e2e conta os registros |
| P3A-4 | T/I | Item com `data_origin` diferente do da doação (dado simulado apresentado como real, ou o contrário) | Alta | FK composta `(donation_id, data_origin)` → `donations(id, data_origin)`; item herda a origem e o rastreio do simulador | IMPLEMENTADO | `test_item_herda_origem_da_doacao_e_o_banco_recusa_origem_diferente` |
| P3A-5 | T | Peso estimado (volume → kg por massa por litro, **premissa sem fonte**) tratado como medido | Média | `weight_basis`, `weight_estimated`, nota e alerta em toda resposta; densidade padrão configurável (`DONATION_DEFAULT_DENSITY_KG_L`); sugestões do texto ficam pendentes | IMPLEMENTADO (limitação documentada) | `test_item_em_volume_usa_massa_por_litro_da_taxonomia_e_avisa`, `tests/test_p3a_conversao_agregacao.py` |
| P3A-6 | T | Validade só mês/ano lida como data exata: o último dia do mês é a leitura **menos** restritiva (o produto pode vencer antes) | Média | Regra da equipe aplicada com aviso explícito, campo PENDENTE de confirmação quando vem do texto, nota em toda resposta; a validade do lote é a do item mais próximo | PARCIAL (risco residual: o doador que informa só mês/ano assume a data) | `test_item_manual_converte_para_kg_e_agrega_no_cabecalho`, `test_regressao_quatro_itens…` |
| P3A-7 | T | Sugestão do parser gravada como fato (quantidade, validade, categoria, refrigeração) | Alta | Itens do texto nascem `TEXTO_SUGERIDO` com `pending_fields`; sem confirmação do item e de cada campo a doação não passa de `PENDING_CONFIRMATION`; o parser é função pura, a pré-visualização não grava doação | IMPLEMENTADO | `tests/test_p3a_parser_itens.py`, `test_pre_visualizacao_do_texto_nao_grava_doacao`, `test_itens_sugeridos_do_texto_exigem_confirmacao` |
| P3A-8 | D | Rascunho com milhares de itens / peso absurdo | Média | `DONATION_MAX_ITEMS` (padrão 30), `DONATION_MAX_TOTAL_KG`, entradas estritas (`extra="forbid"`, limites por campo); **sem rate limit** (P2-6) | PARCIAL | `test_limite_de_itens_configuravel`, `test_entradas_estritas` |
| P3A-9 | I | Lote misto avaliado por modelo treinado só com lotes de **uma** categoria | Média | Elegibilidade exige que a ONG aceite **todas** as categorias; `ML_SCORE` usa a categoria predominante; limitação de desempenho DESCONHECIDO só ao ADMIN; doador e ONG veem apenas a marca de lote misto | PARCIAL (desempenho em lote misto desconhecido) | `tests/test_p3a_lote_misto_match.py` |
| P3A-10 | I | Pseudônimo da ONG que aceitou (e distância) exibidos ao doador; ONG que vê o município do doador; coordenadas exatas após dados reais | Média | Doador vê o pseudônimo só após o aceite; ONG vê tipo/porte/município do doador (não o id); **localização exata e contato só após cadastro real (P2B-7) permanecem PENDENTES** | PARCIAL | `test_doador_nao_recebe_scores_ranking_nem_elegibilidade` |
| P3A-11 | T | Migration 0003 irreversível ou destrutiva | Média | Downgrade manual testado com dados; itens históricos do simulador não são alterados | IMPLEMENTADO (local) | `tests/test_p3a_xx_migracao_reversivel.py`; **CI:** serviço `migrate` do Compose |
| P3A-12 | I | Tokens por perfil no CI vazando em log/imagem | Alta | Gerados no job, mascarados (`::add-mask::`), lidos por `create_user --token-env` (não impresso), **não** passados aos contêineres; `.env.example` só documenta nomes | IMPLEMENTADO (inspeção); **execução no GitHub PENDENTE** | revisão de `ci.yml`, `docker-compose.ci.yml`, `scripts/create_user.py` |
| P3A-13 | I | **Saída do parser (`fields`: valor extraído, confiança, decisões; `categoria_conf`; versão/limiar) devolvida ao doador** (`DonorDonationView` e `/parse` do fluxo de lote único) — viola a regra de visibilidade: esconder na tela não protege quem chama a API com o token do doador | Média | **AJUSTE B0 (Etapa B):** `fields` removido do `DonorDonationView`; `/parse` antigo descontinuado para DONOR (410); `parse-preview` do doador sem confiança/versão/limiar; limitação do modelo (lote misto) só ao ADMIN; varredura recursiva exige ausência dessas chaves em DONOR e ORG | IMPLEMENTADO | `tests/test_p3b_campos_ia_proibidos.py`, `test_p3a_visibilidade_perfil.py`; e2e (`doador_recebe_saida_do_parser`) |

### 13.1 Riscos residuais ao final da Etapa A
1. Desempenho do ranker em **lote misto** e do parser em **texto real** desconhecidos (sem conjunto `MANUALLY_LABELED`).
2. Conversões para kg (massa por litro e massa unitária por embalagem) são **premissas da taxonomia v0.2, sem fonte**.
3. A base de ONGs só tem pseudônimo (sem nome): a interface não pode mostrar nome de ONG ao doador.
4. TLS, rate limit, expiração/rotação/MFA de tokens (P2-3, P2-6, P2B-19, P2B-20) seguem PENDENTES.

### 13.2 Riscos da interface (Etapa B)
| ID | STRIDE | Risco | Tratamento | Status |
|---|---|---|---|---|
| P3B-1 | T/I | **Injeção de Markdown** em texto digitado por outra pessoa (nome do alimento do doador visto pela ONG): imagem/link externo, negrito, `$..$`, `:cor[..]` — rastreamento por imagem externa e links enganosos | `esc()`/`limpar()` em `app/ui_common.py` escapam o texto de terceiros antes de `st.markdown`/`st.write`/`st.caption`; nenhum `unsafe_allow_html` | IMPLEMENTADO (`test_nome_de_alimento_malicioso_*`, `test_esc_neutraliza_*`) |
| P3B-2 | I | Token do usuário na sessão do Streamlit (campo de senha; guardado só na memória da sessão, nunca em arquivo/log) | Sem gravação em disco; token estático segue como limitação (P2-3, P2B-19, P2B-20) | RESIDUAL |
| P3B-3 | E | A tela mostrar ao doador/ONG algo que a API não permitiria | A barreira é a API (`response_model` por perfil); a tela só apresenta; AppTest por perfil exige ausência de jargão/tabelas de score | IMPLEMENTADO |
| P3B-4 | R | Dupla ação (clique repetido) em Aceitar/Recusar/Enviar | Confirmação em 2 passos; API idempotente/409 em doação alterada; tela bloqueia após o envio | IMPLEMENTADO |

## 14. Dashboard do ADMIN e observabilidade (Fase 3 Parte 2 · Etapa A)
| ID | STRIDE | Risco | Tratamento | Status | Verificação |
|---|---|---|---|---|---|
| P3C-1 | E/I | DONOR ou ORG acessa estatísticas agregadas (`/api/v1/admin/stats/*`) ou a simulação de logística | `require_roles("ADMIN", audit_admin="stats.<tela>")` em todas as rotas; a tela só apresenta | IMPLEMENTADO | `tests/test_p3c_admin_stats.py` (403 para DONOR/ORG, 401 sem token); e2e local com os 3 perfis |
| P3C-2 | R | Consulta de dashboard sem trilha | Cada chamada grava `admin.access` com recurso `stats.<tela>` e os parâmetros de consulta (nunca o token) | IMPLEMENTADO | teste de auditoria; e2e (21 auditorias gravadas) |
| P3C-3 | T/I | Número simulado apresentado como real, ou origens somadas num mesmo indicador | Toda linha leva `data_origin` + selo (PÚBLICO/SIMULADO/MEDIDO); consultas agrupam por origem; sem doação USER_ENTERED a tela diz "Nenhuma doação real registrada."; "kg salvos" não é rótulo | IMPLEMENTADO | `tests/test_p3c_ui_dashboard.py` |
| P3C-4 | I | Indicador de segurança inflado ou inventado | Só conta par antes/depois de arquivos presentes (com SHA-256); Trivy de imagem do CI sem JSON = "pendente", sem estimativa | IMPLEMENTADO | `tests/test_p3c_observabilidade_seguranca.py` |
| P3C-5 | I | Log com token, corpo, query string ou IP | Middleware loga método, caminho (sem query), status e duração; sem cabeçalhos/corpo/IP; eventos de negócio só com ids técnicos e contagens | IMPLEMENTADO | teste de log (`api.request`) |
| P3C-6 | T | Cabeçalho `X-Request-ID` malicioso (injeção em log/resposta) | Só aceito se casar `^[A-Za-z0-9._-]{8,64}$`; senão gera uuid4 | IMPLEMENTADO | `test_request_id_validacao` |
| P3C-7 | I | Terceiros no mapa (tiles, chaves) expõem o uso ou exigem licença | Mapa sem mapa-base de terceiros nem chave; pontos/calor/rotas sobre fundo neutro | IMPLEMENTADO | revisão de `app/page_dashboard.py` |
| P3C-8 | E | Token ADMIN de defesa permanece válido | `scripts/create_user.py --revoke <rótulo>` desativa e audita (`user.revoke`); token nunca impresso | IMPLEMENTADO | `test_revogar_token_por_rotulo` |
| P3C-9 | D | Consultas pesadas do dashboard / simulação de logística repetida | Agregações em SQL, limites e paginação (≤200 linhas); simulação limitada (2–24 lotes, solver ≤3 s). **Sem rate limit** (P2-6) | PARCIAL | limites validados por Pydantic |
| P3C-10 | I | Relatórios de segurança copiados para a imagem da API | Somente JSON/texto dos relatórios (sem segredos; gitleaks 0); `.md` continua fora da imagem | IMPLEMENTADO (local) | `.dockerignore` e `Dockerfile.api` (build só confirma o CI) |
