# DATA_SIMULATION.md — Simulador de doações (Fase 1, gerador v0.2.0)

> Tudo neste documento descreve dados **SIMULADOS** (`data_origin = SIMULATED`). A especificação-mãe é `DATA_SIMULATION_SPEC.md` (v0.2.0); aqui está o que foi **efetivamente implementado**, as premissas, as incertezas e o que a validação mostrou.

## 1. O que é real e o que é simulado

| Elemento | Origem | Observação |
|---|---|---|
| ONGs/organizações, municípios, população, bancos RBBA, PAA | **REAL** (`PUBLIC`) | Nunca geradas; o simulador só as lê de `data/gold/` |
| Doadores (perfil operacional, localização, janela de retirada) | SIMULADO | Sem pessoas físicas; município sorteado ponderado por população (proxy; base de CNPJ não obtida); coordenada = centroide do município |
| Lotes (categoria, produto, quantidade, validade, refrigeração, alérgenos) | SIMULADO | Taxonomia `simulation/config/taxonomy_v0.2.yaml` (11 categorias, 85 produtos; cada produto traz `origin`) |
| Textos de descrição do lote | SIMULADO | Templates F1–F3 (treino) + F4 reservada (teste fora do treino), com ruído e casos difíceis |
| Perfil LATENTE da ONG (aptidão, afinidade por categoria, capacidade/câmara fria efetivas, disponibilidade) | SIMULADO, **oculto** | Dirige o desfecho; proibido como feature, regra ou exibição |
| Perfil DECLARADO da ONG (capacidade, horários, categorias, câmara fria, frota) | SIMULADO | Observável, com viés e ruído em relação ao latente (cenários fiel/base/otimista) |
| Desfecho (resposta, aceite, coleta, coleta dentro da validade) | SIMULADO | Estocástico; alvo = aceitou ∧ coletou ∧ dentro da validade |

Não há Faker, nomes de pessoas, CPF/CNPJ, e-mails, telefones nem restrição religiosa; não existe `aceita_alergenicos`.

## 2. Como cada parte é derivada

* **Mix de categorias**: calibrado ao alvo agregado NOVA da RBBA 2025 (REAL, agregado: 88,2/1,3/4,5/6,0%) e ao cenário de hortifrúti (alto 60–70% — referência de composição de compras do PAA/Conab, que é compra e não doação; baixo 30–40% — premissa). O mapeamento produto→NOVA é premissa do projeto. Resultado: R2 PASSA.
* **Sazonalidade**: índice mensal de kg da RBBA 2025 (REAL, um único ano). R3 PASSA (Spearman 0,86; erro mensal médio 3,2 pp).
* **Quantidade**: log-normal truncada em [5, 5000] kg, medianas por categoria — **premissa sem fonte** (apenas ordem de grandeza ancorada no agregado RBBA).
* **Validade**: faixas de vida útil por produto, com escala ±30% sorteada por execução — **vida útil sem fonte**; as âncoras só limitam. Textos podem omitir ou deixar ambígua a validade (`frac_validade_ausente` 10–25%, `frac_ambigua` 3–10%).
* **Candidatas**: K=15 ONGs mais próximas até 150 km, por haversine (BallTree); ONGs só entram se tiverem coordenada utilizável (`rankable_by_distance`).
* **Tempo de deslocamento**: `dist × desvio / velocidade + serviço` (desvio 1,2–1,5; 15–30 km/h até 15 km; 40–70 km/h acima; serviço 15–45 min) — **premissas logísticas não verificadas** (L1 PASSA: a fórmula é reproduzida).
* **Desfecho**: logit com β para aptidão, afinidade, capacidade (log), falta de frio, banco de alimentos e distância, mais efeitos aleatórios por ONG e por doador e ruído logístico por par; β0 calibrado à taxa-base do cenário. Resposta: probabilidade de silêncio, mais forte fora do horário; tempo de resposta log-normal que avança só em horário comercial (L2 PASSA: 0 violações). Coleta: capacidade do veículo, falha de cadeia fria, no-show, janela do doador e validade (L3 PASSA).
* **Alvo contrafactual**: todos os pares candidatos recebem desfecho. Em produção só se observa o par acionado — limitação declarada.

## 3. Reprodutibilidade e versionamento

`python -m simulation.generator --seed 20261003 --n-lots 60000 --n-donors 8000 --tag main [--aceitacao baixa|media|alta] [--hortifruti alto|baixo] [--declarado fiel|base|otimista]`. As sementes de cada módulo derivam de `SeedSequence(seed)`; `dataset_version = <generator>+<hash dos parâmetros>+<seed>`. Todas as tabelas carregam `data_origin`, `generator_version`, `seed`, `dataset_version` e `source_parameters`. Testado: mesma seed ⇒ mesmas tabelas; seeds diferentes ⇒ tabelas diferentes (`tests/test_simulator.py`).

## 4. Validação de realismo (`data/simulated/main/realism.json`)

| Check | Resultado | Leitura |
|---|---|---|
| R1 volume por banco RBBA vs 411,7 t/relatório/ano | **NÃO PASSA** (mediana simulada ≈ 4–6 t/ano) | O simulador não calibra o volume por banco; **não usar volumes absolutos**. Registrado, não ocultado |
| R2 mix NOVA | PASSA | Calibrado ao alvo (circular por construção) |
| R3 sazonalidade | PASSA | Idem |
| R4 lotes por UF × população | PASSA (Pearson 0,996) | Coerência interna: população é o proxy da densidade de doadores |
| R5 cobertura de candidatas | REPORTADO | 99,9% dos lotes têm candidata; 94,98% dos doadores estão em município com OSC |
| R6 kg sem destino dentro da validade | REPORTADO: 45,5% vs ~4,85% (perda RBBA) | O simulador é **pessimista** em sucesso; taxas absolutas de sucesso não são estimativas reais |
| T1–T3 textos | PASSA / PASSA / REPORTADO | T3: sobreposição de trigramas com treino 82,5% (visto) vs 43,8% (F4 reservada) |
| L1–L3 logística | PASSA | Coerência interna |
| Oráculo | PASSA | Mesmo conhecendo os latentes, MRR ≈ 0,75 e Top-1 ≈ 0,61: o desfecho **não é determinístico** |
| Monotonicidade | PASSA | P(coleta \| aceitou) varia com a distância |

## 5. Incertezas principais e circularidade

1. Todos os parâmetros marcados `PREMISSA` (quantidades, validades, logística, coeficientes do desfecho, ruído do declarado) vêm de julgamento da equipe, **não de fonte**. A coluna `type/source/why` em `simulation/params/params_v0.2.0.yaml` lista cada um.
2. **Circularidade:** os rótulos nascem de uma função escolhida pela equipe; qualquer modelo treinado aqui aprende o simulador. Para medir a sensibilidade, rodamos 5 seeds, 5 cenários alternativos e treino-em-A/teste-em-B (`ml/artifacts/ranker/robustness.json`).
3. Atributos DECLARADOS das ONGs são simulados porque não há cadastro real; o efeito disso foi isolado numa ablação (queda de MRR de 0,695 para 0,644 ao removê-los).
4. Lacuna crítica: **não há corpus real de textos de doação**; a análise semântica foi treinada e avaliada em texto simulado. Existe apenas um rascunho provisório (83 textos escritos por IA, `data/manual_labeled/PROVISORIO_rascunho_ia.csv`) e um template vazio para o conjunto `MANUALLY_LABELED`, que a equipe precisa preencher.

## 6. Cenários e seeds disponíveis

Principal: `main` (60 000 lotes, seed 20261003). Robustez (12 000 lotes cada): `rb_s1..rb_s5` (seeds 1001–1005), `sc_acc_baixa`, `sc_acc_alta`, `sc_hf_baixo`, `sc_decl_fiel`, `sc_decl_otimista`. Os conjuntos de robustez são descartáveis e reproduzíveis pelos comandos acima.

## 7. Limitações conhecidas que seguem em aberto (Fase 2 Parte 1)

* **R1 (volume por banco) NÃO PASSA** — o simulador não reproduz o volume anual por banco do RBBA. Volumes absolutos simulados **não** devem ser usados como estimativa do mundo real.
* **R6 (kg sem destino) é PESSIMISTA** — 45,5% simulados vs ~4,85% de perda reportada pelo RBBA; taxas de sucesso/perda simuladas **não** são estimativas reais.
* Consequência na Parte 1: a plataforma exibe "**dados simulados com limitações conhecidas**" na UI, no `GET /api/v1/model/info` e nas respostas de match; tempos e taxas observados em execuções com dados `SIMULATED` são de **engenharia**, não desempenho real.
* O simulador **não foi alterado** na Parte 1; os dados são importados para o PostgreSQL apenas com `data_origin = SIMULATED` (+ `generator_version`, `dataset_version`, `seed`, exigidos por restrição CHECK no banco).
