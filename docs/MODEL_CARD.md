# Model Card — Rede Alimenta IA

> **Leia primeiro.** Todas as métricas deste cartão foram calculadas sobre dados **SIMULADOS** (`data_origin = SIMULATED`) e **não representam desempenho no mundo real**. Os rótulos vêm de um simulador definido pela própria equipe: o modelo aprende o simulador (circularidade, seção 9). Todos os números abaixo vêm de `docs/MODEL_REPORT.md`, `ml/artifacts/ranker/{metadata,metrics,robustness}.json` e `ml/artifacts/semantic/metrics.json` (fonte indicada em cada seção). Nenhum número foi calculado ou estimado para este cartão; contagens de arquivo vêm de execuções desta sessão e estão marcadas.

## 1. Visão geral

| | |
|---|---|
| Sistema | Recomendação **doador → ONG** (ranking de ONGs candidatas) + análise semântica do texto livre do lote |
| Componentes | (1) **Ranker** (`ranker-1.0.0`), (2) **Parser semântico** (texto → categoria, perecibilidade, refrigeração, quantidade, validade), (3) motor de match com regras eliminatórias (`match-engine-1.0.0`) |
| Versão do ranker | `ranker-1.0.0`, treinado em 2026-10-03, semente 20261003, `scikit-learn 1.7.2` (`metadata.json`) |
| Artefato e integridade | `ml/artifacts/ranker/model.joblib`, SHA-256 `0849a3ac…77a7` verificado no carregamento (`metadata.json`; STRIDE M1). `joblib` executa código ao carregar: só artefatos da própria equipe |
| Dados de treino | simulado `0.2.0+477ed37e+20261003` + real `pipeline-1.0.0+raw_checksums:731ccb918075` (`metadata.json`) |
| Escopo | **Fora de escopo:** qualquer previsão sobre pessoas beneficiadas |
| Licença do software | Apache-2.0 (`LICENSE`). Licenças dos dados: `docs/data/DATA_LICENSES.md` (várias **não confirmadas**) |

## 2. Objetivo

Dado um lote de alimento de um doador, **ranquear as ONGs candidatas** (as 15 mais próximas dentro de 150 km que passam nas regras eliminatórias) pela probabilidade de **aceitar e coletar dentro da validade**. O ranking apoia uma decisão humana: a ONG aceita ou recusa, e o sistema nunca declara um alimento próprio ou impróprio para consumo (`docs/MODEL_REPORT.md` §1, §9; STRIDE P2-11).

## 3. Algoritmo

* **Ranker:** `HistGradientBoostingClassifier` (scikit-learn) com pré-processamento em pipeline; probabilidade por par (lote, ONG) usada como `ML_SCORE`. Comparado a regressão logística e Random Forest (amostra de 12 mil lotes). Escolha pelo maior MRR na **validação** (HGB 0,693; RF 0,680; LR 0,647). Probabilidades **não foram recalibradas**; limiar de decisão 0,248 (F1 na validação).
* **Score final do match:** `FINAL = 0,5·ML + 0,3·REGRAS + 0,2·DISTÂNCIA` — pesos **premissa da equipe, não calibrados com dados reais** (`docs/FASE2_P1_MATCH_ENGINE.md`). Regras eliminatórias (localização, cadastro, categoria aceita, capacidade, refrigeração, horário, prazo de validade) usam atributos **declarados** das ONGs (simulados).
* **Explicação local:** `factors` por oclusão de grupos de fatores (aproximação, não causal) — visível **só ao ADMIN**.
* **Parser semântico:** regex + `dateparser` para validade e quantidade; **TF-IDF de caracteres (2–5) + regressão logística** (C = 10) para categoria, perecibilidade e refrigeração; limiar de confiança **τ = 0,66** escolhido na validação simulada com custo assimétrico (subestimar perecibilidade custa 3× mais que superestimar); abaixo do limiar o campo vai para **confirmação humana** (`ml/artifacts/semantic/metrics.json`; `docs/MODEL_REPORT.md` §8).

## 4. Dados: reais e simulados, e a proporção

| Elemento | Origem | Quantidade | Fonte |
|---|---|---|---|
| ONGs e bancos de alimentos | **REAL** (`PUBLIC`: IPEA/OSC 54.398 + RBBA 192) | 54.590 | `data/gold/organizations.parquet` (execução desta sessão); `docs/data/DATA_SOURCES.md` |
| Localização da ONG | REAL **PROXY**: centroide do município para 54.400; coordenada exata para 190 | 54.590 | idem |
| Município, população, PAA, nº de OSCs | **REAL** | — | `docs/data/` |
| Doadores | **SIMULADO** (tipo, porte e município reais; localização = centroide) | 8.000 | `data/simulated/main/run_params.json` (execução desta sessão) |
| Lotes e textos de descrição | **SIMULADO** | 60.000 | idem; `MODEL_REPORT` §2 |
| Pares (lote, ONG) com desfecho | **SIMULADO** | 895.177 (taxa de `target` 19,7%) | `MODEL_REPORT` §2 |
| Perfil **declarado** das ONGs, frota | **SIMULADO** (com viés/ruído) | 54.590 cada | `DATA_SIMULATION.md` |
| Desfecho (resposta, aceite, coleta) | **SIMULADO**, estocástico | 895.177 pares | idem |

**Proporção:** 100% dos **rótulos**, 100% dos lotes/doadores/textos e todo o perfil declarado das ONGs são simulados; a **identidade e a geografia das ONGs e o contexto territorial** são reais. Na lista de **43 features** (`ml/artifacts/ranker/metadata.json` → `feature_origin`): **28 SIMULADAS**, **8 REAIS** e **7 PROXY/derivadas** (distância e precisão de localização, calculadas de coordenadas públicas/proxy e do doador simulado).

## 5. Features, com origem

(24 numéricas + 12 booleanas + 7 categóricas = 43; `ml/dataset.py`. O `MODEL_REPORT` §2 citava 23 numéricas — corrigido nesta fase para 24, conforme o código.)

| Origem | Features |
|---|---|
| **REAL (PUBLIC)** — 8 | `populacao_2026`, `n_osc_assistencia_municipio`, `paa_kg_historico_municipio`, `ano_fundacao`, `paa_adesao`, `tem_banco_rbba_municipio`, `uf`, `ong_tipo` |
| **PROXY / derivada de coordenadas públicas + doador simulado** — 7 | `dist_km`, `rank_distancia`, `tempo_deslocamento_est_h`, `mesmo_municipio`, `location_precision_doador`, `location_precision_ong`, `geo_quality_ong` |
| **SIMULADO** — 28 | lote (`quantidade_kg`, `horas_ate_validade`, `categoria`, `perecibilidade`, `exige_refrigeracao`, `contem_alergenico`, janelas e `tempo_carga_min`, `hora_cadastro`, `dow_cadastro`), ONG declarada (`capacidade_declarada_max_kg_dia`, `frota_*`, `camara_fria_declarada`, `n_categorias_aceitas_declaradas`, horários e dias declarados, `tem_frota`) e derivadas (`kg_sobre_capacidade`, `kg_sobre_frota`, `horas_validade_menos_viagem`, `razao_deslocamento_validade`, `elegivel_regra`, `categoria_aceita_declarada`, `dia_comum_declarado`, `precisa_frio_sem_frio_declarado`) |

Proibidos como feature (teste `test_features_sem_vazamento`): atributos **latentes** do simulador e colunas de desfecho/tempo (`ml/dataset.py::FORBIDDEN`).

## 6. Target e divisão

* **Target:** `aceitou ∧ coletou ∧ dentro da validade` (`docs/data/DATA_DICTIONARY.md`), gerado de forma **estocástica** (logit com efeitos aleatórios por ONG, por doador e ruído por par). O oráculo do simulador (que conhece os latentes) obtém MRR ≈ 0,75 e Top-1 ≈ 0,61 em amostra de 5.000 lotes, ou seja, o desfecho **não é determinístico**.
* **Rótulos contrafactuais:** todas as candidatas têm desfecho; em produção só se observa o par acionado (viés de seleção a corrigir).
* **Divisão temporal por lote (70/15/15)** por data de cadastro; todos os pares de um lote ficam no mesmo conjunto: lotes 41.967 / 8.993 / 8.994; pares 626.698 / 134.189 / 134.290 (`MODEL_REPORT` §2; `metrics.json`). 24% dos lotes de teste (2.129 de 8.994) não têm nenhuma ONG com `target = 1` e ficam fora das métricas de ranking (6.865 avaliáveis).

## 7. Métricas (teste, **SIMULADO**) com baselines

Fonte: `docs/MODEL_REPORT.md` §3. IC 95% por bootstrap de lotes (200 repetições) para o modelo escolhido.

| Modelo | MRR | Top-1 | Top-3 | NDCG@3 | ROC-AUC | PR-AUC | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aleatório | 0,462 | 0,267 | 0,559 | 0,282 | — | — | — |
| ONG mais próxima | 0,465 | 0,272 | 0,566 | 0,290 | — | — | — |
| Regra (elegível, categoria aceita, distância) | 0,541 | 0,353 | 0,661 | 0,365 | — | — | — |
| Regressão logística | 0,649 | 0,488 | 0,761 | 0,464 | 0,772 | 0,422 | 0,480 |
| Random Forest (12 mil lotes) | 0,681 | 0,532 | 0,787 | 0,498 | 0,790 | 0,447 | 0,497 |
| **HGB (escolhido)** | **0,695** [0,686–0,705] | **0,546** [0,533–0,560] | **0,804** [0,796–0,814] | **0,515** [0,508–0,523] | 0,798 | 0,459 | 0,503 |

O baseline aleatório tem MRR alto porque há cerca de 15 candidatas e ~20% de positivos por par: leia o ganho **contra os baselines**, não em valor absoluto. Classificação (HGB, teste): precisão 0,389, revocação 0,709, Brier 0,131.

**Robustez (SIMULADO):** 5 sementes (12 mil lotes): MRR do HGB 0,649 ± 0,035 contra regra 0,528 ± 0,039, com vitória em todas as sementes; 5 cenários (aceitação baixa/alta, hortifrúti baixo, declarado fiel/otimista): MRR 0,63–0,73, vencendo todos os baselines; treino em A / teste em B: queda de até ≈ 0,03. **Isso não mede robustez a dados reais.** Sem os atributos declarados das ONGs o MRR cai de 0,695 para 0,644 (parte do ganho depende de informação simulada). Segmentos mais difíceis: PANIFICADOS 0,566, REFEIÇÕES_PRONTAS 0,586, LATICÍNIOS/OVOS 0,618, lotes que exigem refrigeração 0,637 — justamente onde o risco sanitário é maior.

**Parser semântico (SIMULADO; `MODEL_REPORT` §8):**

| Conjunto | Categoria / perecibilidade / refrigeração (regressão logística) | Perecibilidade subestimada (baseline → LR) |
|---|---|---|
| Simulado visto (n = 11.467) | 0,961 / 0,984 / 0,917 | 8,6% → 0,8% |
| Simulado reservado, família F4 (n = 12.024) | 0,956 / 0,982 / 0,901 | 7,4% → 0,7% |
| Rascunho provisório escrito por IA (n = 81; **não é rotulagem humana**) | 0,975 / 0,988 / 0,938 | 1,2% → 1,2% |
| **MANUALLY_LABELED** | **ausente** — a equipe ainda precisa criar o conjunto (`data/manual_labeled/`) | — |

Validade informada: extração 98,7%, exatidão 89,9–91,6%, MAE 1,1–1,6 dia (simulado). **Refrigeração é o ponto fraco** (≈ 0,90–0,92): confirmação humana sempre que o lote for de risco.

## 8. Limitações

1. **Todas as métricas são sobre dados simulados**; o desempenho em doações e textos reais é **desconhecido**.
2. **Lote misto:** o ranker foi treinado só com lotes de **uma** categoria; para lote misto o `ML_SCORE` usa a categoria predominante e a elegibilidade exige que a ONG aceite todas as categorias. O desempenho em lote misto é **DESCONHECIDO** (STRIDE P3A-9; aviso só ao ADMIN).
3. **Sem conjunto `MANUALLY_LABELED`:** o parser nunca foi avaliado em texto real de doadores. A família F4 é um estilo de template gerado pela mesma equipe.
4. Atributos declarados das ONGs (capacidade, horários, categorias, câmara fria, frota) são 100% simulados; a ablação mostra a dependência deles.
5. Distância entre pontos do mesmo município é zero (centroide): em cidades grandes o ranking depende dos atributos, não da distância; **não é distância viária**.
6. Sem calibração formal das probabilidades; pesos do score final e premissas logísticas (desvio 1,35, velocidades, margem de segurança) **não verificados**.
7. Conversões de volume para kg (massa por litro e massa unitária) são **premissas da taxonomia v0.2, sem fonte**.
8. Segurança alimentar (cadeia fria) exige validação por especialista antes de qualquer uso real.
9. Simulador: o check R1 (volume por banco) **não passa** e R6 mostra viés **pessimista** (45,5% simulado contra ≈ 4,85% de perda no RBBA): taxas absolutas simuladas **não** são estimativas reais (`docs/data/DATA_SIMULATION.md` §4).
10. Degrau com modelo pré-treinado (Hugging Face) **não foi testado**.

## 9. Circularidade da simulação

Os rótulos nascem de uma função escolhida pela equipe (logit com coeficientes de premissa). Qualquer modelo treinado aqui aprende essa função, não o mundo. As métricas medem **aderência ao simulador**. Mitigações feitas: desfecho com ruído e efeitos não observáveis, 5 sementes, 5 cenários, treino-em-A/teste-em-B e comparação com o oráculo. Mitigação **não feita**: validação com dados reais de doação e coleta.

## 10. Vieses e riscos de equidade (não medidos)

* **Cobertura geográfica:** ONGs sem coordenada utilizável são excluídas pelo motor; hoje as 54.590 têm coordenada, mas 99,65% por centroide de município, o que desfavorece a precisão em áreas rurais e grandes cidades.
* **Tamanho do município:** `populacao_2026` e a densidade de OSCs são features reais; podem favorecer municípios grandes. **Não há análise de equidade por região ou porte de ONG.**
* **Declarado inflado:** ONGs reais poderiam inflar capacidade para ganhar prioridade (STRIDE C2); o simulador modela só um cenário "otimista".
* **Pessoa jurídica apenas:** o modelo não usa atributo de pessoa física, religiosa ou de beneficiário; `area_religiao` do gold **não** é feature.

## 11. Usos recomendados e NÃO recomendados

**Recomendados:** demonstração acadêmica; apoio ao ADMIN para inspecionar o ranking explicado; protótipo cujo resultado passa sempre por **confirmação humana** (doador confirma itens, ONG aceita ou recusa); base para retreino futuro com doações reais.

**NÃO recomendados:**
* apresentar qualquer métrica como desempenho real, "kg salvos" ou "refeições" reais (a plataforma hoje mostra "Nenhuma doação real registrada");
* decidir sozinho o destino de uma doação real ou o despacho sem confirmação humana;
* atestar que um alimento é seguro para consumo;
* usar volumes ou taxas de sucesso simulados como estimativa do mundo real;
* uso comercial enquanto as licenças dos dados estiverem não confirmadas (`docs/COMMERCIAL_READINESS.md`);
* qualquer uso sobre pessoas beneficiadas.

## 12. Manutenção e reprodução

Reprodução: `docs/REPRODUCIBILITY.md` (comandos `simulation.generator`, `ml.semantic.train_eval`, `ml.training.train`). Retreino exige ~6 GB de RAM (README). Mudança de dados, pesos ou premissas ⇒ nova versão do modelo e novo `dataset_version`. Responsável pela revisão deste cartão: equipe do projeto. Última revisão: Fase 4 · Etapa A.
