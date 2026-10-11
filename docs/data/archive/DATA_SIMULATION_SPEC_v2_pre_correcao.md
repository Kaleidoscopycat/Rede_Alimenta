# DATA_SIMULATION_SPEC.md — Especificação da simulação Doador → ONG

**Projeto:** Rede Alimenta IA · **Fase:** 0 (especificação; **nenhum dado simulado foi gerado**) · **Versão da spec:** 0.1.0 · **Data:** 2026-10-02
**Implementação prevista:** `simulation/` (Fase 1). O AGENTS.md pede `docs/data/DATA_SIMULATION.md`; esse arquivo será derivado desta spec na Fase 1 (pendência de nomenclatura registrada).

> **Princípio:** o que existe publicamente é REAL e nunca é inventado (ONGs, municípios, população, bancos de alimentos, referências). O que não existe publicamente — **doadores (perfil operacional), lotes e desfechos de match** — é SIMULADO por gerador documentado, versionado e com seed, parametrizado por fontes reais. **Toda métrica obtida sobre dado simulado é "métrica de simulação", nunca desempenho no mundo real.**

---

## 1. Escopo: o que é e o que não é simulado

| Entidade | Origem | Observação |
|---|---|---|
| Municípios, UF, população, adesão PAA | **REAL** (IBGE, MDS) | nunca simulados |
| Coordenadas de município | **PROXY** (compilação MIT; ver CANDIDATES B3) | não inventadas |
| ONGs candidatas (OSC) | **REAL** (IPEA/Mapa das OSCs, 54.398 com área "Assistência social"; ver §2) | só os atributos observados |
| Bancos de alimentos (RBBA) | **REAL** (192 pontos) | 2 coordenadas suspeitas → centroide |
| Categorias de alimento | **Taxonomia do projeto** (premissa), com mix ancorado na classificação NOVA real da RBBA | PAA não traz categoria |
| **Doadores** (perfil operacional) | **SIMULADO** | id interno, tipo, porte, **município REAL**; sem CNPJ/nome/endereço |
| **Lotes de doação** | **SIMULADO** | categoria, kg, validade, refrigeração, janela de coleta |
| **Perfil operacional latente da ONG** (capacidade, câmara fria, disponibilidade) | **SIMULADO e OCULTO** | ver §4.3; não é atributo real da ONG |
| **Desfechos** (aceite, coleta, tempo) | **SIMULADO** | processo estocástico (§5) |
| Pessoas físicas, beneficiários, "fome", necessidade individual | **NUNCA** | fora de escopo |

Regras duras: sem Faker; sem CNPJ/nome/endereço fictícios de empresas; sem coordenadas inventadas (a posição do doador = centroide de município real); nada de dado de pessoa física, real ou fictício.

**Salvaguarda sobre ONGs reais:** atributos simulados (ex.: capacidade latente) ficam em tabela separada, chaveada por `ong_id` pseudonimizado, **nunca exibidos junto ao nome/CNPJ da ONG real** e nunca descritos como característica dela. Em dashboards/API, qualquer score é rotulado "simulação".

## 2. Universo real de ONGs candidatas e regra de elegibilidade (PROXY)

Não existe, na fonte, flag de "segurança alimentar" nem de "recebe doação de alimentos". Regra v1 (**PROXY, explícita e auditável**):
- `ong_osc`: OSC do IPEA com **área "Assistência social" = 1** (54.398 em 4.421 municípios; as flags de **subárea** não são usadas — inconsistentes com a área, ver CANDIDATES A1). Sensibilidades futuras: + "Desenvolvimento e defesa de direitos" com subárea de centros comunitários (apenas 32 registros) — rejeitado por ser irrisório.
- `ong_rbba`: os 192 bancos RBBA georreferenciados (modalidade: Público Municipal 110, SESC 86, OSC 8, Estadual 2, Federal 1, Distrital 1).
- Interseção OSC × RBBA **não é possível por CNPJ** (RBBA não publica CNPJ) → tratados como universos separados, `ong_tipo ∈ {OSC_ASSISTENCIA, BANCO_ALIMENTOS_RBBA}`. Possível duplicidade é uma limitação.
- **Limite honesto:** uma OSC de assistência social pode não receber alimentos; o simulador reflete isso com um fator latente de "aptidão" (§4.3), mas a fração real é desconhecida.

## 3. Parâmetros: fonte, premissa e incerteza

Convenção: **[REAL]** parâmetro calculado de fonte real · **[PREMISSA]** premissa explícita da equipe/spec, **sem fonte**, com intervalo de incerteza; as premissas são **sorteadas por run dentro do intervalo** (propagação de incerteza, §6) e **todas devem ser revalidadas** quando surgir fonte.

### 3.1 Doadores
| Parâmetro | Valor / regra | Tipo | Fonte / justificativa | Incerteza |
|---|---|---|---|---|
| Tipos de doador | supermercado/hipermercado; restaurante; padaria; atacadista/Ceasa; indústria de alimentos; produtor/hortifrúti | [PREMISSA] (taxonomia por CNAE-alvo) | CANDIDATES D1 | — |
| Distribuição geográfica | proporcional à **população municipal 2026** até obter CNPJ; depois, proporcional à **contagem de estabelecimentos por município × CNAE** | [REAL] população (proxy provisório) | IBGE SIDRA 6579 | **Alta**: população ≠ densidade de estabelecimentos; municípios pequenos sub/sobre-representados. Registrar `donor_geo_basis = POPULACAO_PROXY`. |
| Porte (pequeno/médio/grande) e mix | por tipo; proporções iniciais [PREMISSA] | [PREMISSA] | substituir pelo porte do CNPJ quando aprovado | amplitude ±50% relativa |
| Propensão a doar (fração dos estabelecimentos que efetivamente doam) | 5%–30% | [PREMISSA] | sem fonte; **parâmetro de escala, não afeta o ranking relativo** | ampla |
| Frequência de lotes por doador/semana | por tipo/porte | [PREMISSA] | calibrada para bater a escala do §7.1 | ampla |

### 3.2 Lotes
| Parâmetro | Valor / regra | Tipo | Fonte | Incerteza |
|---|---|---|---|---|
| Categorias | hortifrúti; panificados; laticínios e ovos; carnes/pescados; refeições prontas; mercearia (não perecíveis); bebidas | [PREMISSA] | Mesa Brasil: não perecíveis aceitos; MAPA: 81% do desperdício varejista é perecível | — |
| Mix por categoria | restrito para que **grupo NOVA 1 (in natura/minimamente processados) ≈ 88,2%**, ingredientes ≈ 1,3%, processados ≈ 4,5%, ultraprocessados ≈ 6,0% (em kg) | [REAL] alvo agregado (RBBA 2025) | RBBA `graficos.classificacao` | a RBBA mede o que **bancos receberam**, não o que doadores ofertam → viés de seleção |
| Peso relativo de perecíveis | ≈ 81% dos kg do varejo | [REAL] referência | MAPA 2022 | refere-se a % do desperdício (R$), não kg |
| Tamanho do lote (kg) | log-normal por categoria e porte; truncada em [5 kg; 5.000 kg] | [PREMISSA] | **âncora agregada:** RBBA 2025 = 66.285.063 kg / 161 relatórios ≈ **411,7 t por relatório/ano** (ordem de grandeza) | forma da distribuição **sem fonte**; verificar agregado em §7.1 |
| Sazonalidade mensal da oferta | índice multiplicativo por mês | [REAL] 2 referências | RBBA kg recebidos 2025: jan 0,95 · fev 0,97 · mar 0,94 · abr 0,95 · mai 1,04 · jun 0,94 · jul 1,00 · ago 0,91 · set 1,04 · out 1,11 · nov 1,10 · dez 1,05. PAA (kg 2021–25, hortifrúti/agricultura familiar): 0,53 · 0,54 · 0,69 · 0,94 · 1,26 · 1,15 · 1,24 · 1,30 · 1,07 · 1,21 · 1,28 · 0,79 | RBBA = 1 ano; PAA com cobertura de registros instável. Usar RBBA para o total e PAA **apenas** para a categoria hortifrúti, com mistura sorteada |
| Dia da semana/horário do lote | dias úteis majoritários; picos em fim de expediente de varejo | [PREMISSA] | — | ampla |
| **Dias até a validade** | por categoria: hortifrúti 1–5; panificados 0–3; laticínios 2–15; carnes/pescados 1–5; refeições prontas 0–2; mercearia 30–365; bebidas 30–180 | **[PREMISSA]** | **Nenhuma tabela pública de vida útil foi obtida** (CANDIDATES E6). Valores ilustrativos de ordem de grandeza, **não são dado real** | **Alta**; são os parâmetros mais frágeis. Sorteio de limites ±30% por run |
| Exige refrigeração | determinístico por categoria **como atributo do lote** (carnes, laticínios, refeições prontas = sim; hortifrúti = parcial; resto = não) | [PREMISSA] | boa prática de cadeia fria (não é dado) | média |
| Janela de coleta (horas) | 2–48 h, dependente do tipo de doador | [PREMISSA] | — | ampla |
| Excedente perdido sem destino (referência) | hortaliças 12%–30% (média 21%); varejo 1,8% do faturamento | [REAL] referência | Embrapa 2003; MAPA 2022 | dado antigo/uma rede; usado só para **verossimilhança de ordem de grandeza** |

### 3.3 Premissa de conversão
- **0,4 kg por refeição** (premissa da equipe): `refeicoes = kg / 0,4`. Configurável (`MEAL_KG = 0.4`), exibida na interface e documentação, intervalo de sensibilidade 0,3–0,6. Refeições são **equivalência aritmética**, não "pessoas atendidas".

## 4. Estrutura do dataset simulado (esquema alvo; campos obrigatórios de rastreabilidade em todas as tabelas)

Campos obrigatórios em **toda** linha simulada: `data_origin = "SIMULATED"`, `generator_version`, `seed`, `dataset_version`, `source_parameters` (referência ao arquivo de parâmetros versionado + sha256 e às fontes reais usadas).

### 4.1 `sim_donor` — (doador)
`donor_id` (interno, ex.: `SIMD-000123`; nunca CNPJ) · `donor_type` · `donor_size` · `municipio_ibge` (**REAL**) · `uf` · `donor_geo_basis` · campos de rastreabilidade.

### 4.2 `sim_lot` — (lote)
`lot_id` · `donor_id` · `created_at` (data-hora simulada) · `categoria` · `quantidade_kg` · `dias_ate_validade` · `exige_refrigeracao` · `janela_coleta_h` · `dia_semana` · `hora` · `contem_alergenico` (existe no dataset de doações, **fora das features do modelo**, decisão da equipe) · `refeicoes_equiv` · rastreabilidade.

### 4.3 `sim_ong_latent` — perfil operacional latente (**oculto do modelo e do produto**)
`ong_id` (pseudônimo estável derivado de `id_osc`/`identificador` RBBA) · `capacidade_kg_dia` · `tem_camara_fria` · `aptidao_alimentar` (probabilidade de a ONG, em geral, aceitar alimentos) · `afinidade_categoria[k]` · `efeito_aleatorio_ong` · `disponibilidade_coleta` · rastreabilidade.
- **Não são features v1** (decisão: o modelo não vê o que os dados reais não trazem; assim evitamos "descobrir" o que acabamos de colocar). Experimento opcional rotulado: expor `capacidade_kg_dia`/`tem_camara_fria` como features **SIMULADAS** e medir o ganho — o ganho mede a lógica do simulador.
- Parâmetros: [PREMISSA]; quando possível, centrados em valores da RBBA (ex.: tamanho de operação) com variação por tipo de ONG (RBBA: 62% operação convencional, 28% colheita urbana).

### 4.4 `sim_pair_outcome` — (par lote × ONG candidata) — **unidade de observação**
`lot_id` · `ong_id` · `ong_tipo` · `dist_km` (haversine entre centroide do município do doador e centroide do município da ONG; **ou** ponto real RBBA quando válido) · `dist_precisao ∈ {CENTROIDE_CENTROIDE, CENTROIDE_PONTO}` · `mesmo_municipio` · `rank_distancia` · `aceitou` · `coletou` · `horas_ate_coleta` · `coletou_dentro_validade` · **`target = aceitou ∧ coletou_dentro_validade`** · rastreabilidade.

**Geração de candidatas por lote:** as `K = 15` ONGs elegíveis (§2) mais próximas por distância de centroide, restritas a no máximo 150 km, garantindo ≥1 `BANCO_ALIMENTOS_RBBA` quando houver um dentro do raio. Lotes sem nenhuma candidata são registrados como `sem_candidata` (reflete municípios sem rede) e não entram no treino.

## 5. Como o desfecho é gerado (processo estocástico — nunca regra determinística)

Para cada par (lote *i*, ONG *j*), em duas etapas, com **ruído e fatores latentes**:

1. **Aceite:** `logit P(aceita) = β0 + β_apt·aptidao_j + β_cat·afinidade_j[cat_i] + β_cap·f(kg_i / capacidade_j) + β_frio·1[exige_frio_i ∧ ¬camara_j] + β_tipo·tipo_j + u_j + v_i + ε_ij`, onde `u_j ~ N(0,σ_u²)` (efeito aleatório da ONG, não observável), `v_i ~ N(0,σ_v²)` (efeito do doador/lote, não observável) e `ε_ij ~ Logistic(0,1)` (ruído do par). `aceita ~ Bernoulli(P)`.
2. **Coleta:** tempo até coleta `T_ij ~ LogNormal(μ_ij, σ_T²)` com `μ_ij = γ0 + γ_dist·log(1+dist_km) + γ_disp·disponibilidade_j + γ_dia·fim_de_semana + γ_hr·hora`; `coletou_dentro_validade = 1[T_ij ≤ min(janela_coleta_i, dias_ate_validade_i·24)]`.
3. **Não determinismo:** as funções acima são aplicadas com **coeficientes sorteados por run** de intervalos `[PREMISSA]` (priors em `simulation/params/*.yaml`), com ruído de par e dois efeitos aleatórios. Nenhum atributo observável determina sozinho o desfecho; a **taxa máxima atingível** é limitada (ver §7.3: o simulador deve produzir AUC-teto < 1 por construção — o *oráculo* que conhece os latentes e os coeficientes **não** pode chegar a 100%).
4. **Contrafactual:** os rótulos são gerados para **todos** os pares candidatos (informação completa). Em produção real só se observa o desfecho da ONG efetivamente acionada (viés de seleção/censura). Isso é limitação **declarada**.
5. **Sem vazamento:** `aptidao`, `capacidade`, `camara_fria`, `u_j`, `v_i`, `ε_ij`, `T_ij`, `aceitou`, `coletou` **não** entram em features; `horas_ate_coleta` e `aceitou` são pós-desfecho.

Coeficientes: sinais esperados por premissa (distância ↓ P; ONG com câmara fria ↑ P para perecíveis; kg/capacidade alto ↓ P). **A magnitude é premissa sem fonte** → resultado do modelo = reflexo do que o simulador codifica.

## 6. Seed, versionamento e reprodutibilidade
- `generator_version` (SemVer; começa em `0.1.0`), `dataset_version = <generator_version>+<hash curto dos parâmetros>+<seed>`.
- `seed` mestre inteiro; sub-seeds derivadas por entidade com `numpy.random.SeedSequence.spawn` (doadores, lotes, latentes ONG, desfechos) → reprodução bit a bit com mesma versão de numpy/Python (versões registradas em `data/metadata/`).
- Arquivo de parâmetros versionado: `simulation/params/params_v{generator_version}.yaml`; cada parâmetro com campos `valor | intervalo`, `tipo (REAL|PREMISSA)`, `fonte`, `justificativa`. O hash (sha256) vai em `source_parameters`.
- Execução de **múltiplas seeds** (≥5) e **cenários** (aceitação baixa/média/alta; mix de perecíveis alto/baixo) para reportar variação — nunca uma única realização.
- Testes de determinismo: mesma seed ⇒ mesmo hash do dataset; seeds distintas ⇒ hashes distintos.

## 7. Critérios de realismo (como o simulado é comparado com as referências reais)

### 7.1 Agregados com âncora real (devem passar; reprovação = ajustar premissa ou documentar)
| # | Verificação | Referência real | Critério |
|---|---|---|---|
| R1 | kg doados/ano por banco RBBA-equivalente (soma dos lotes recebidos num banco simulado) | ≈ 411,7 t/relatório/ano (RBBA 2025) | mediana simulada entre 0,5× e 2× — **só ordem de grandeza** |
| R2 | mix NOVA em kg | 88,2 / 1,3 / 4,5 / 6,0 % | desvio ≤ 2 p.p. por grupo |
| R3 | sazonalidade mensal de kg ofertados | índice RBBA 2025 | correlação de Spearman ≥ 0,6 e erro relativo mensal ≤ 15% |
| R4 | distribuição geográfica de doadores | população IBGE (provisório) / contagem CNPJ (futuro) | correlação por UF ≥ 0,9 |
| R5 | cobertura de candidatas | municípios com OSC "Assistência social" (4.421 de 5.571) e 161 municípios com ponto RBBA | proporção de lotes com ≥1 candidata coerente com a cobertura (reportar) |
| R6 | perda sem destino | 4,85% de perda nos bancos (RBBA); 1,8% do faturamento no varejo (MAPA) | fração de kg "não coletado dentro da validade" reportada ao lado dessas referências; **não é meta de calibração** (medidas diferentes) |

### 7.2 Aceitação/coleta
**Não há referência real** de taxa de aceite ou de coleta doador→ONG em fonte pública localizada. Portanto a taxa é **premissa**; reportar resultados por cenário (aceitação baixa/média/alta) e **nunca** apresentar uma taxa simulada como "taxa real".

### 7.3 Sanidade do simulador
- **Oráculo:** classificador que conhece latentes+coeficientes deve ter desempenho **bem abaixo de perfeito** (teto de ruído documentado); se ≈100%, o simulador é determinístico demais → reprovado.
- Monotonicidade esperada (dist ↑ ⇒ P(coleta) ↓) verificada empiricamente.
- Distribuições marginais plotadas e arquivadas; checagens de faixa (kg, validade, janela).

## 8. Circularidade — risco e como será reportado
O modelo supervisionado aprenderá **a lógica do simulador** (o que a spec e as premissas codificam), não o mundo real. Mitigações **e** obrigações de relato:
1. **Baselines obrigatórios:** aleatório; "ONG mais próxima"; regra simples (distância + câmara fria **não observável → só distância + tipo + categoria**); popularidade (frequência de aceite por tipo de ONG no treino); regressão logística; árvore/gradient boosting.
2. **Comparação com regra simples:** o ganho do modelo sobre a melhor regra simples é a métrica principal; se for pequeno, o modelo não agrega.
3. **Teste de misspecificação:** treinar em cenário A (coeficientes/priors A) e avaliar em cenário B (coeficientes deslocados, outra seed, outro mix) — a queda mede dependência da lógica do simulador.
4. **Particionamento:** por **lote/doador** e por **região/tempo** (nunca por par aleatório, que vaza efeitos aleatórios).
5. **Rótulo em tudo:** métricas (AUC-PR, NDCG@k, Recall@k, Brier/calibração) sempre acompanhadas de "**simulação — não representa desempenho no mundo real**" em relatórios, API, dashboard, README e pitch. Proibido: "acurácia de X%" sem esse rótulo.
6. **Honestidade de produto:** o ranking é "ONGs com maior probabilidade **simulada** de aceitar/coletar", não impacto real, fome ou necessidade.
7. **Caminho para o real:** a coleta de feedback real (USER_ENTERED) numa versão futura permite reajustar/validar; até lá, nenhuma afirmação de generalização.

## 9. O que esta spec NÃO resolve (pendências reais)
1. Fonte de **vida útil por categoria** (CANDIDATES E6) e de **taxa de aceite** — premissas.
2. **Estabelecimentos por CNAE/município** (CNPJ) — bloqueio de rede e licença; provisório = população.
3. Licenças de IPEA/OSC, RBBA, coordenadas e IBGE — confirmação formal pendente.
4. Distância intramunicipal (mesmo município = 0 km); trocar por malha oficial IBGE e, na Fase 1, avaliar distância viária (fora do escopo de dado público disponível agora).
5. Capacidade/refrigeração **reais** das ONGs — inexistentes em fonte pública; permanece latente simulado.
