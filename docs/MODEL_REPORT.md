# MODEL_REPORT.md — MVP de IA (Fase 1)

> **TODAS as métricas abaixo foram calculadas sobre dados SIMULADOS (`data_origin = SIMULATED`) e NÃO representam desempenho no mundo real.** Os rótulos vêm de um simulador definido pela equipe; os modelos aprendem o simulador (circularidade). Atributos de ONG/município são REAIS; atributos declarados das ONGs, lotes, frota e desfechos são SIMULADOS.

## 1. Problema

Para um lote de alimento de um doador, ranquear as ONGs candidatas (as 15 mais próximas até 150 km) pela probabilidade de **aceitar e coletar dentro da validade** (`target`). Fluxo DOADOR → ONG; ONG → beneficiário está fora de escopo.

## 2. Dados e divisão

* Conjunto `main` (versão `0.2.0+477ed37e+20261003`): 60 000 lotes, 895 177 pares; taxa de `target` 19,7%.
* **Divisão temporal por lote** (70/15/15 por data de cadastro; todos os pares de um lote ficam no mesmo conjunto): treino 41 967 lotes / validação 8 993 / teste 8 994.
* 24% dos lotes de teste não têm nenhuma ONG com `target=1` (2 129 de 8 994); eles são **excluídos das métricas de ranking** (avaliáveis: 6 865) e permanecem nas métricas de classificação por par.
* Features (`ml/dataset.py`): 24 numéricas, 12 booleanas, 7 categóricas (43 no total; corrigido na Fase 4 conforme `ml/dataset.py`, que antes dizia 23); origem de cada coluna em `FEATURE_ORIGIN`. **Atributos latentes e colunas de desfecho/tempo são proibidos** (teste `test_features_sem_vazamento`).

## 3. Baselines e modelos (teste, SIMULADO)

IC95% por bootstrap de lotes (200 repetições) para o modelo escolhido.

| Modelo | MRR | Top-1 | Top-3 | NDCG@3 | ROC-AUC | PR-AUC | F1 (limiar da validação) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aleatório (desempate sorteado) | 0,462 | 0,267 | 0,559 | 0,282 | — | — | — |
| ONG mais próxima | 0,465 | 0,272 | 0,566 | 0,290 | — | — | — |
| Regra (elegível, categoria aceita, distância) | 0,541 | 0,353 | 0,661 | 0,365 | — | — | — |
| Regressão logística | 0,649 | 0,488 | 0,761 | 0,464 | 0,772 | 0,422 | 0,480 |
| Random Forest (amostra de 12 mil lotes) | 0,681 | 0,532 | 0,787 | 0,498 | 0,790 | 0,447 | 0,497 |
| **HistGradientBoosting (escolhido)** | **0,695** [0,686–0,705] | **0,546** [0,533–0,560] | **0,804** [0,796–0,814] | **0,515** [0,508–0,523] | 0,798 | 0,459 | 0,503 |

* Escolha pelo maior MRR na **validação** (HGB 0,693; RF 0,680; LR 0,647).
* O baseline aleatório tem MRR alto (0,46) porque há ~15 candidatas e ~20% de positivos por par; o ganho deve ser lido contra os baselines, não em valor absoluto.
* Classificação (HGB, teste): precisão 0,389, revocação 0,709, Brier 0,131; matriz tn 77 623 / fp 29 847 / fn 7 797 / tp 19 023. Limiar 0,248 escolhido na validação por F1. Probabilidades **não foram recalibradas**.
* Referência de teto: o oráculo do simulador (conhece latentes e coeficientes) obtém MRR ≈ 0,75 e Top-1 ≈ 0,61 em amostra de 5 000 lotes (`realism.json`, métrica não idêntica à acima: amostra e lotes diferentes); portanto o modelo está abaixo do teto teórico e o desfecho não é determinístico.

## 4. Segmentos (HGB, teste, MRR SIMULADO)

Piores: PANIFICADOS 0,566, REFEIÇÕES_PRONTAS 0,586, LATICÍNIOS/OVOS 0,618, perecível refrigerado/congelado 0,624, lotes que exigem refrigeração 0,637. Melhores: INDUSTRIALIZADOS 0,740, HORT_RAÍZES 0,731, GRÃOS 0,721. Perecíveis têm pior ranking: o problema é mais difícil justamente onde o risco sanitário é maior.

## 5. Ablações e robustez (SIMULADO)

* Sem atributos declarados pela ONG (HGB): MRR 0,644 (vs 0,695). Só distância e lote: 0,622. Ou seja, parte do ganho depende de informação declarada, que é simulada.
* **5 seeds** (12 mil lotes): MRR do HGB 0,649 ± 0,035 (dp) vs regra 0,528 ± 0,039; o modelo vence a regra em todas as seeds (ganho mínimo 0,083).
* **5 cenários** (aceitação baixa/alta, hortifrúti baixo, declarado fiel/otimista): HGB vence todos os baselines em todos os cenários (MRR 0,63–0,73).
* **Misspecificação** (treino em `rb_s1`, teste em outras seeds/cenários): MRR cai pouco (até ≈ 0,03 em relação ao modelo treinado no próprio cenário), o que indica sensibilidade moderada a mudanças de parâmetros do gerador. Isso **não** mede robustez a dados reais.
* Importância por permutação (queda de PR-AUC): `quantidade_kg` 0,080, `kg_sobre_capacidade` 0,060, `razao_deslocamento_validade` 0,031, `frota_capacidade_declarada_kg` 0,021, `exige_refrigeracao` 0,020. Reflete o simulador, não causalidade real.

## 6. Explicabilidade

`POST /api/v1/predict` devolve `factors`: efeito, em probabilidade, de neutralizar cada grupo de fatores (distância/tempo, capacidade vs quantidade, frota, refrigeração, categoria aceita, horários, elegibilidade, contexto) para a melhor ONG (oclusão com medianas/modas do treino). É uma explicação local aproximada, não causal.

## 7. Artefato

`ml/artifacts/ranker/`: `model.joblib` (pipeline de pré-processamento + HGB), `metadata.json` (versão `ranker-1.0.0`, SHA-256, versões de dados simulada e real, features, origem por feature, limiar, seed, aviso), `metrics.json`, `robustness.json`. Treinado com scikit-learn 1.7.2 (mesma versão local); o hash é verificado no carregamento da API.

## 8. Análise semântica (seção 12) — `ml/artifacts/semantic/metrics.json`

Componentes: parser de validade (regex + dateparser), extração de quantidade/unidade, baseline de regras e TF-IDF de caracteres (2–5) + regressão logística para categoria, perecibilidade e refrigeração; limiar de confiança τ = 0,66 escolhido na validação simulada com custo assimétrico (subestimar perecibilidade custa 3× mais que superestimar). **Treinado e avaliado somente em texto SIMULADO.**

| Conjunto | Baseline: categoria / perecib. / refrig. | Regressão logística: categoria / perecib. / refrig. | Perecib. subestimada (baseline → LR) |
|---|---|---|---|
| Simulado visto (F1–F3, n=11 467) | 0,861 / 0,896 / 0,903 | 0,961 / 0,984 / 0,917 | 8,6% → 0,8% |
| Simulado reservado F4 (n=12 024) | 0,873 / 0,909 / 0,900 | 0,956 / 0,982 / 0,901 | 7,4% → 0,7% |
| Rascunho IA provisório (n=81; **não é rotulagem humana**) | 0,938 / 0,963 / 0,938 | 0,975 / 0,988 / 0,938 | 1,2% → 1,2% |
| MANUALLY_LABELED | **ausente** (a equipe precisa criar) | — | — |

* Validade informada: taxa de extração 98,7%, exatidão exata 89,9–91,6%, MAE 1,1–1,6 dia (simulado); falso positivo de "validade informada" 0–1,9%; ECE da perecibilidade 0,010–0,014; ~6% dos textos vão para confirmação humana.
* **Refrigeração é o ponto fraco** (acurácia ≈ 0,90–0,92 em simulado): sugerida confirmação humana sempre que o lote for de risco.
* A família F4 é uma mudança de estilo de template **gerada pela mesma equipe**; não substitui texto real. O alvo mais importante da fase seguinte é o conjunto `MANUALLY_LABELED`.
* Degrau de Hugging Face (modelo pré-treinado) **não foi testado** nesta fase.

## 9. Limitações

1. Circularidade simulador → modelo; métricas medem aderência ao simulador.
2. Rótulos contrafactuais (todas as candidatas têm desfecho); em produção só se observa o par acionado, o que exigirá correção de viés de seleção.
3. Declarado da ONG, frota, lotes e textos 100% simulados; R1 não passa e R6 mostra simulador pessimista (docs/data/DATA_SIMULATION.md).
4. Distância entre pontos do mesmo município é zero (centroide), logo, em cidades grandes, o ranking depende de atributos e não de distância; distância real por rota não foi usada.
5. Sem calibração formal das probabilidades do ranker; limiar de decisão otimiza F1 na validação simulada.
6. Segurança alimentar (cadeia fria) exige validação por especialista antes de qualquer uso real.
