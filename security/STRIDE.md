# Modelagem de ameaças STRIDE — Rede Alimenta IA (Fase 1 / Checkpoint 1)

**Escopo:** fluxo DOADOR → ONG (a distribuição ONG → beneficiário está fora de escopo). **Estado:** MVP local; ainda não há autenticação, banco de dados, nuvem nem CI/CD. Este documento classifica o que **já está mitigado no código**, o que é **risco aceito nesta fase** e o que **fica para fases futuras** (DevSecOps).

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
| A1 | S | Cliente se passa por doador/ONG; endpoints abertos | Médio | Alta | Nesta fase não há login. Fase 2: autenticação (OIDC/JWT), papéis doador/ONG/admin, chaves por cliente | PENDENTE (risco aceito no MVP local) | 2 |
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
| I1 | T | Pipeline de CI/CD comprometido | Alto | Baixa | Ações fixadas por hash, permissões mínimas, revisão obrigatória | PENDENTE | 2 |
| I2 | E | Contêiner executa como root, imagem desatualizada | Alto | Média | Usuário não-root, imagem mínima, scan (Trivy), SBOM | PENDENTE | 3 |
| I3 | I | Segredos de produção expostos | Alto | Média | Gerenciador de segredos, rotação, scan de segredos no CI | PENDENTE | 3 |
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
| P2-13 | I | Dependências novas (SQLAlchemy, Alembic, psycopg, Streamlit, scipy) | Médio | Média | Versões fixadas em `requirements.txt`; **varredura de dependências/SAST (Bandit/Trivy) fica para a Parte 2** | PENDENTE | — |
