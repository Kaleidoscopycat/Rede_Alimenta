# DATA_SIMULATION_SPEC.md — Especificação da simulação Doador → ONG

**Projeto:** Rede Alimenta IA · **Fase:** 0 (especificação; **nenhum dado simulado foi gerado**)
**Versão da spec:** **0.2.0** (2026-10-02) · **Versão dos parâmetros registrada:** **params v0.2.0** (o arquivo `simulation/params/params_v0.2.0.yaml` será criado na Fase 1 a partir das tabelas deste documento; hoje não existe)
**Versão anterior:** 0.1.0, arquivada em `archive/DATA_SIMULATION_SPEC_v2_pre_correcao.md`.
**Nomenclatura:** o AGENTS.md pede `docs/data/DATA_SIMULATION.md`; esse arquivo será derivado desta spec na Fase 1.

> **Princípio:** o que existe publicamente é REAL e nunca é inventado (ONGs, municípios, população, bancos de alimentos, referências). O que não existe publicamente — **doadores (perfil operacional), lotes, descrições textuais dos lotes, desfechos de match e premissas logísticas** — é SIMULADO por gerador documentado, versionado e com seed, parametrizado por fontes reais **ou por premissa explícita**. **Toda métrica obtida sobre dado simulado é "métrica de simulação", nunca desempenho no mundo real.**

## 0. Registro de mudanças 0.1.0 → 0.2.0 (params v0.1.0 → v0.2.0)
| # | Mudança | Motivo |
|---|---|---|
| 1 | Novo **gerador de descrições textuais** dos lotes (§6) | decisão da equipe: análise semântica entra na Fase 1 (seção 12) e na Fase 2 Parte 1 (3.2) |
| 2 | Novo **conjunto MANUALLY_LABELED** fora do treino (§7) | medir generalização além dos modelos de frase do gerador |
| 3 | **Capacidade/refrigeração da ONG em dois níveis**: LATENTE (oculto) e DECLARADO (observável, SIMULADO) (§4.3) | o motor de match precisa de regra de elegibilidade; atributo oculto não pode ser regra |
| 4 | **Premissas logísticas** (janela de retirada, resposta da ONG, frota, desvio, velocidade) (§3.4, §4.4) | Logística Inteligente (Fase 1 seção 13; Fase 2) |
| 5 | **Taxonomia e nomes de produto** com origem registrada; **vida útil** com âncoras parciais (§3.2) | pendência 3: nomes **não vêm do PAA** nem da TACO |
| 6 | `location_precision`/`geo_quality` (§4.7) | pendência 4 |
| 7 | Correção de premissa: **panificados** passam de 0–3 dias para **0–1 dia** (âncora Anvisa 24 h) | fonte G1 |
| 8 | **Quatro classes de perecibilidade** (§3.2) | Anvisa Guia 26/2019 + Guia de Doação 2022 |

## 1. Escopo: o que é e o que não é simulado
| Entidade | Origem | Observação |
|---|---|---|
| Municípios, UF, população, adesão PAA | **REAL** (IBGE, MDS) | nunca simulados |
| Coordenadas de município | **PROXY** (compilação MIT; origem primária não confirmada) | não inventadas |
| ONGs candidatas (OSC) e bancos RBBA | **REAL** (IPEA; RBBA) | só os atributos observados |
| Taxonomia de categorias e lista de nomes de produto | **PREMISSA DO PROJETO** (inspirada em fontes públicas, §3.2) | **não** é dado de fonte |
| Doadores (perfil operacional) | **SIMULADO** | id interno, tipo, porte, **município REAL** |
| Lotes de doação | **SIMULADO** | categoria, produto, kg, validade, refrigeração, janela |
| **Descrições textuais dos lotes** | **SIMULADO** | texto livre + rótulos de verdade gerados juntos (§6) |
| **Perfil operacional da ONG — LATENTE** | **SIMULADO e OCULTO** | determina o desfecho; nunca é feature (§4.3) |
| **Perfil operacional da ONG — DECLARADO** | **SIMULADO e OBSERVÁVEL** | gerado do latente **com ruído**; usado em regras e, rotulado, como feature (§4.3) |
| Frota de coleta, janelas, tempos de resposta | **SIMULADO** | premissas (§3.4) |
| Desfechos (aceite, coleta, tempos) | **SIMULADO** | processo estocástico (§5) |
| Conjunto de teste textual | **MANUALLY_LABELED** (escrito pela equipe) | **não é simulado** (§7) |
| Pessoas físicas, beneficiários, "fome", necessidade individual | **NUNCA** | fora de escopo |

Regras duras: sem Faker; sem CNPJ/nome/endereço/telefone fictícios de empresas ou pessoas **inclusive dentro dos textos**; sem coordenadas inventadas (posição do doador = centroide de município real); nenhum dado de pessoa física, real ou fictício.

**Salvaguarda sobre ONGs reais:** atributos simulados — latentes **e declarados** — ficam em tabelas separadas, chaveadas por `ong_id` pseudonimizado, e **nunca são exibidos junto ao nome/CNPJ da ONG real como se fossem característica dela**. Em dashboards/API, todo campo declarado simulado carrega o rótulo "SIMULADO".

## 2. Universo real de ONGs candidatas e regra de elegibilidade (PROXY)
- `OSC_ASSISTENCIA`: OSC do IPEA com **área "Assistência social" = 1** (54.398 em 4.421 municípios; flags de **subárea** não usadas — inconsistentes com a área).
- `BANCO_ALIMENTOS_RBBA`: os 192 bancos RBBA georreferenciados (Público Municipal 110, SESC 86, OSC 8, Estadual 2, Federal 1, Distrital 1).
- Sem chave comum (RBBA não publica CNPJ) → universos separados; possível duplicidade é limitação.
- Elegibilidade "receptora de alimentos" é **PROXY** (não há flag de segurança alimentar). A fração real é desconhecida.

## 3. Parâmetros: fonte, premissa e incerteza
Convenção: **[REAL]** calculado de fonte real · **[REF]** referência publicada citada (com restrição de licença, ver CANDIDATES §G) · **[PREMISSA]** sem fonte, com intervalo de incerteza. Premissas são **sorteadas por run dentro do intervalo** (§8) e **revalidadas quando surgir fonte**.

### 3.1 Doadores
| Parâmetro | Valor / regra | Tipo | Fonte / justificativa | Incerteza |
|---|---|---|---|---|
| Tipos | supermercado/hipermercado; restaurante; padaria; atacadista/Ceasa; indústria de alimentos; produtor/hortifrúti | [PREMISSA] (por CNAE-alvo) | CANDIDATES D1 | — |
| Distribuição geográfica | ∝ **população 2026** (provisório) → depois ∝ estabelecimentos por município × CNAE (CNPJ, **pendente**) | [REAL] população como proxy | IBGE SIDRA 6579 | **Alta** (população ≠ densidade de estabelecimentos). Registrar `donor_geo_basis`. |
| Porte e mix | por tipo | [PREMISSA] | trocar pelo porte do CNPJ | ±50% relativo |
| Propensão a doar | 5%–30% | [PREMISSA] | parâmetro de escala; não altera o ranking relativo | ampla |
| Frequência de lotes/semana | por tipo/porte | [PREMISSA] | calibrada p/ §9 R1 | ampla |
| **Janela de retirada** (novo) | dias da semana permitidos (subconjunto de seg–dom), `hora_inicio`/`hora_fim` (início 6–12 h; duração 2–10 h), `tempo_carga_min` 10–45 | [PREMISSA] | **cobre horário e dias** (a v0.1.0 só tinha duração `janela_coleta_h`, insuficiente: ver §4.2) | ampla |

### 3.2 Lotes — taxonomia, nomes, perecibilidade e vida útil
**Origem da taxonomia (decisão da correção, item 2 da pendência 3): PREMISSA DO PROJETO v0.2**, *inspirada* em: grupos do MDS para hortifrúti (A folhosas/talos/inflorescências; B raízes/bulbos/rizomas/tubérculos; C frutos; D frutas) [G2, RESTRICTED]; classes de perecibilidade da Anvisa [G3, NEEDS_REVIEW] e do Guia de Doação [G1, RESTRICTED]; composição do PAA 2020 (Hortifrúti 69%, Carnes 8%, Grãos/oleaginosas 7%, Processados 16%) [C5, referência de **oferta agrícola**, não de doações]. **Nada disso é "dado de fonte" da simulação.**

**Classes de perecibilidade (v0.2):** `NAO_PERECIVEL` · `PERECIVEL_BAIXO_RISCO` (hortaliças e frutas inteiras, panificados) · `PERECIVEL_REFRIGERADO_CONGELADO` · `PRONTO_ALTO_RISCO` (refeições prontas). As três primeiras ecoam G3; a quarta vem dos limites de tempo/temperatura de G1.

| Código | Categoria (premissa) | Perecibilidade | Refrigeração (premissa) | Dias até a validade (premissa; sorteio ±30% por run) | Âncora citada |
|---|---|---|---|---|---|
| HORT_FOLHOSAS | folhosas, talos, inflorescências (MDS-A) | baixo risco | recomendada | 1–4 | G6: folhas desinfetadas 12 h (contexto de cozinha escolar → só qualitativo) |
| HORT_RAIZES | raízes, bulbos, tubérculos (MDS-B) | baixo risco | não | 5–30 | — |
| HORT_FRUTOS | hortaliças-fruto (MDS-C) | baixo risco | parcial | 2–8 | — |
| FRUTAS | frutas (MDS-D) | baixo risco | parcial | 2–10 | — |
| PANIFICADOS | pães e similares | baixo risco | não | **0–1** | **G1: máximo 24 h após a fabricação** |
| CARNES_PESCADOS | cárneos | refrigerado/congelado | sim | 1–5 (refrigerado); 30–180 (congelado) | G6: carne moída 24 h a ≤ 4 °C (contexto diferente); G1: congelado −18 °C (ou −12 °C — **divergência na leitura**) |
| LATICINIOS_OVOS | leite fluido, queijos, iogurtes, ovos | refrigerado/congelado | sim | 2–15 | G1: refrigerado 4–10 °C |
| REFEICOES_PRONTAS | refeições preparadas | pronto/alto risco | sim | **0–2** | **G1: refrigeradas máx. 5 dias a 4 °C; quentes máx. 6 h acima de 60 °C** (premissa 0–2 dentro do limite) |
| GRAOS_CEREAIS | arroz, feijão, fubá, farinhas, macarrão | não perecível | não | 60–365 | validade é do fabricante (G4) |
| INDUSTRIALIZADOS | óleo, molho de tomate, sardinha em lata, leite em pó, doces | não perecível | não | 30–365 | idem |
| BEBIDAS | sucos, bebidas não alcoólicas | não perecível | não | 30–180 | idem |

**Vida útil:** continua **PREMISSA com intervalo de incerteza** (sem tabela de fonte; G4 confirma que o prazo é do fabricante). As âncoras acima **limitam** alguns intervalos mas não os determinam. **Parâmetros mais frágeis do simulador.**

**Nomes de produto:** lista = **premissa do projeto**, cada nome com `product_name_origin ∈ {MDS_CATALOGO_2018, CONAB_COMPENDIO_2021, MESA_BRASIL_SESC, SEDUC_GO_2024, PREMISSA_PROJETO}`. Nomes com origem pública **já obtidos literalmente**: abóbora, acelga, açúcar, alho, amendoim, arroz, café, carne bovina, carne de ave, doces de frutas, feijão, frutas, leite fluido, mel, queijo, suco de fruta (G5); arroz, feijão, leite em pó, óleo, fubá, sardinha em lata, macarrão, molho de tomate, farinha de milho, farinha de mandioca (Mesa Brasil/SESC, E3); mandioca, banana, melancia (Conab 2021); pão francês, creme de leite, salsicha, goiabada, carne moída (SEDUC-GO). **O PAA/MDS-SAGI não traz produto; a TACO (NEEDS_REVIEW) não é usada como lista de nomes até a licença ser revisada; nenhum nome é atribuído ao "PAA" ou a "dados reais" sem esta rastreabilidade.**

| Parâmetro | Valor / regra | Tipo | Fonte | Incerteza |
|---|---|---|---|---|
| Mix por categoria | grupo NOVA 1 ≈ **88,2%**, ingredientes ≈ 1,3%, processados ≈ 4,5%, ultraprocessados ≈ 6,0% (em kg) via mapeamento categoria→NOVA | [REAL] alvo agregado RBBA 2025 | A3 | RBBA mede o que bancos **receberam** (viés de seleção); mapeamento NOVA por produto é premissa (G8 não lido) |
| Cenário "hortifrúti alto" | peso de HORT_* e FRUTAS ≈ 60–70% | [REF] composição de compras PAA (63% em 2018 secundário; 69% em 2020) | C5 | refere-se a compras agrícolas, não a doações |
| Peso de perecíveis | ≈ 81% do desperdício varejista | [REF] | MAPA 2022 | é % de R$ |
| Tamanho do lote (kg) | log-normal por categoria/porte, truncada em [5; 5.000] kg | [PREMISSA] | âncora agregada: RBBA ≈ **411,7 t por relatório/ano** | forma sem fonte; verificar R1 |
| Sazonalidade mensal | índice multiplicativo | [REAL] | RBBA 2025: 0,95·0,97·0,94·0,95·1,04·0,94·1,00·0,91·1,04·1,11·1,10·1,05; PAA 2021–25 só p/ hortifrúti | RBBA = 1 ano; PAA com cobertura instável |
| Quantidade e unidade no texto | unidades (kg, g, caixa, pacote, unidade, dúzia, bandeja, litro) com **massa unitária** por produto | [PREMISSA] | — | ampla; a massa unitária liga o texto ao `quantidade_kg` |
| Exige refrigeração | atributo da **categoria/estado** (refrigerado/congelado/ambiente), com subcategoria `temperatura_conservacao` | [PREMISSA] ancorada em G1 | — | média |

### 3.3 Premissa de conversão (consistência verificada)
**0,4 kg por refeição** (premissa da equipe): `refeicoes_equiv = quantidade_kg / 0,4`, configurável (`MEAL_KG = 0.4`), sensibilidade 0,3–0,6. É o **mesmo valor** do AGENTS.md e das tabelas deste documento e do dicionário. Refeições = equivalência aritmética, **não** "pessoas atendidas".

### 3.4 Premissas logísticas (novas, todas SIMULATED)
| Parâmetro | Valor / regra | Tipo | Justificativa | Intervalo de incerteza |
|---|---|---|---|---|
| Janela de retirada do doador | ver §3.1 | [PREMISSA] | cobre dias e horário | ver §3.1 |
| Horário de funcionamento da ONG (real, latente) | dias úteis ± sábado; abertura 7–10 h, fechamento 15–19 h | [PREMISSA] | não há fonte pública | ampla |
| **Tempo de resposta da ONG a uma proposta** | log-normal por `ong_tipo`; mediana: banco RBBA 15–90 min; OSC 60–360 min; resposta só dentro do horário de funcionamento; `P(sem_resposta)` 5%–25% (tratada como não aceite) | [PREMISSA] | sem fonte; **parte do processo estocástico** (§5), não regra | muito ampla |
| **Probabilidade de aceite por tipo de ONG** | efeito `β_tipo` (§5) com taxa-base por cenário: baixa 0,15–0,25 · média 0,30–0,45 · alta 0,50–0,65 | [PREMISSA] | **escala de cenário, não estimativa** (não há taxa real em fonte pública) | muito ampla |
| **Frota — tipos** | `UTILITARIO` 200–500 kg · `VAN_FURGAO` 600–1.200 kg · `CAMINHAO_BAU_MEDIO` 2.000–4.000 kg · `CAMINHAO_BAU_GRANDE` 6.000–12.000 kg | [PREMISSA] | ordens de grandeza de veículos de carga; **sem fonte lida — validar com operadores (ex.: bancos de alimentos)** | ±30% |
| Frota — refrigeração | `P(refrigerado \| tipo)`: utilitário 0,02–0,10; van 0,10–0,35; caminhão médio 0,20–0,50; grande 0,30–0,60 | [PREMISSA] | — | ampla |
| Frota — posse | banco RBBA: 0,5–0,9 com ≥ 1 veículo; OSC: 0,05–0,30 | [PREMISSA] | apoio **qualitativo**: nos relatórios RBBA aparece a função "motorista" (99 registros; 10,4% das funções declaradas) — não permite inferir frota | ampla |
| **Base de saída** | município/ponto da ONG dona do veículo (herda `location_precision`) | derivado de dado REAL | — | herda a incerteza de localização |
| **Fator de desvio** (reta → via) | 1,2–1,5 (central 1,3) | [PREMISSA] configurável | faixa usual para redes viárias, **não verificada com fonte nesta sessão** | ampla |
| **Velocidade média** | ≤ 15 km: 15–30 km/h; > 15 km: 40–70 km/h | [PREMISSA] configurável | — | ampla |
| Tempo de serviço (carga/descarga) | 15–45 min | [PREMISSA] | — | ampla |
| Tempo de deslocamento estimado | `dist_reta × desvio / velocidade + serviço` | derivado | sempre apresentado como **estimativa**, nunca distância viária real | — |

## 4. Estrutura do dataset simulado (esquema alvo)
Campos obrigatórios em **toda** linha simulada: `data_origin = "SIMULATED"` (ou `MANUALLY_LABELED` no §7), `generator_version`, `seed`, `dataset_version`, `source_parameters` (arquivo de parâmetros + sha256 + fontes reais).

### 4.1 `sim_donor`
`donor_id` (interno, nunca CNPJ) · `donor_type` · `donor_size` · `municipio_ibge` (**REAL**) · `uf` · `donor_geo_basis` · `location_precision = MUNICIPALITY_CENTROID` · rastreabilidade.

### 4.2 `sim_lot`
`lot_id` · `donor_id` · `created_at` · `categoria` (§3.2) · `produto` · `product_name_origin` · `perecibilidade` · `temperatura_conservacao` · `quantidade_kg` · `quantidade_unidade`/`unidade` · `dias_ate_validade` · `exige_refrigeracao` · **`janela_retirada_inicio`, `janela_retirada_fim`, `dias_retirada`, `tempo_carga_min`** (substituem `janela_coleta_h`, que passa a ser derivada: fim − início) · `contem_alergenico` (**fora das features**) · `refeicoes_equiv` · rastreabilidade.

### 4.3 Capacidade e refrigeração da ONG: **declarada × latente** (decisão registrada)
**Decisão (2026-10-02):** o motor de match (Fase 2 Parte 1) precisa de capacidade/refrigeração como **regra de elegibilidade**; atributo oculto não pode ser regra. Logo, dois níveis:

| Nível | Tabela | Visibilidade | Conteúdo | Uso |
|---|---|---|---|---|
| **LATENTE** | `sim_ong_latent` | **oculto** do modelo, das regras e do produto | `capacidade_efetiva_kg_dia`, `camara_fria_efetiva`, `aptidao_alimentar`, `afinidade_categoria[k]`, `efeito_aleatorio_ong` (`u_j`), `disponibilidade_coleta`, horário de funcionamento real | **apenas** o gerador de desfecho (§5) |
| **DECLARADO** | `sim_ong_declared` | **observável**, rotulado `SIMULATED` | `capacidade_declarada_kg_dia`, `camara_fria_declarada`, `categorias_aceitas_declaradas`, `horario_funcionamento_declarado`, `dias_funcionamento_declarados` | regras de elegibilidade; **e**, rotulado, feature do modelo |

**Como o declarado é gerado (declarado ≠ real, por construção):**
- `capacidade_declarada = arredondar_para_faixa( capacidade_efetiva × exp(δ) )`, `δ ~ N(viés, σ_d²)` com viés **positivo** (ONGs tendem a declarar mais do que operam): `viés` 0,0–0,4, `σ_d` 0,2–0,6; declaração em **faixas** (como em um cadastro), não valor exato. **[PREMISSA]**
- `camara_fria_declarada`: `P(declara sim | não tem)` 5%–25% (câmara fria inoperante/compartilhada); `P(declara não | tem)` 0%–10%. **[PREMISSA]**
- `categorias_aceitas_declaradas`: subconjunto das categorias com `afinidade` alta, **mais** categorias adicionais com probabilidade 10%–30% (otimismo) e **menos** algumas com 5%–15% (omissão). **[PREMISSA]** *(extensão em relação ao texto da pendência: a Fase 2 Parte 1 usa "categoria aceita" e "horário de funcionamento" como regras de elegibilidade e, sem fonte real, também precisam do nível declarado.)*
- `horario_funcionamento_declarado`: real ± deslocamento de até 1 h e, com 5%–20%, janelas que a ONG não cumpre. **[PREMISSA]**

**Regra de "sem vazamento" (atualizada):**
1. **Proibidos como feature/regra:** todos os campos LATENTES, `u_j`, `v_i`, `ε_ij`, `T_ij`, `aceitou`, `coletou`, `horas_ate_coleta`.
2. **Permitidos:** campos DECLARADOS, **sempre rotulados SIMULATED**, em regras e como feature.
3. Como o declarado é gerado **a partir** do latente (que dirige o desfecho), a correlação declarado→desfecho **é construída pelo simulador**. **Experimento opcional obrigatório de relato:** medir o ganho do modelo com e sem os campos declarados; **esse ganho mede a lógica do simulador, não o mundo real** e deve ser reportado como tal.
4. Salvaguarda da §1: campos declarados **nunca** são exibidos junto ao nome/CNPJ da ONG real como característica dela; o rótulo "SIMULADO" acompanha o campo.

### 4.4 `sim_fleet`
`fleet_id` · `ong_id` · `tipo_veiculo` · `capacidade_kg` · `refrigerado` · `base_municipio_ibge` (REAL) · `location_precision` · rastreabilidade. Todos SIMULADOS (§3.4). Capacidade e refrigeração da frota são **declaradas** à plataforma (observáveis) e podem divergir da capacidade efetiva em uso (parâmetro `fator_uso_efetivo` 0,7–1,0).

### 4.5 `sim_lot_text` — descrições textuais (novo; §6)
`text_id` · `lot_id` · `texto` · `template_family_id` · `template_id` · `noise_ops[]` · `difficulty_flags[]` · `reference_date` · **rótulos de verdade:** `y_categoria` (1 ou 2 com flag) · `y_produto` · `y_perecibilidade` · `y_exige_refrigeracao` · `y_dias_ate_validade` (nulo se ausente) · `y_validity_source ∈ {INFORMADA, INFERIDA_PELA_CATEGORIA, AUSENTE}` · `y_quantidade` · `y_unidade` · rastreabilidade (`data_origin = SIMULATED`).

### 4.6 `manual_labeled_text` — conjunto de teste (novo; §7)
Mesmo esquema de rótulos de §4.5, **sem** `template_*`; `data_origin = MANUALLY_LABELED`; campos: `annotator_a`, `annotator_b` (pseudônimos), `adjudicado_por`, `frozen_at`, `sha256_conjunto`.

### 4.7 `sim_pair_outcome` — (par lote × ONG candidata) — **unidade de observação**
`lot_id` · `ong_id` · `ong_tipo` · `dist_km` (haversine) · **`location_precision_doador`, `location_precision_ong ∈ {EXACT, MUNICIPALITY_CENTROID, NONE}`** · `geo_quality_ong ∈ {OK, SUSPEITA, NAO_APLICAVEL}` · `mesmo_municipio` · `rank_distancia` · `tempo_deslocamento_est_h` · `razao_deslocamento_validade` · features DECLARADAS · `elegivel_regra` + `motivos_exclusao` (regras explícitas) · **desfecho:** `resposta ∈ {ACEITOU, RECUSOU, SEM_RESPOSTA}`, `horas_resposta`, `coletou`, `horas_ate_coleta`, `coletou_dentro_validade`, **`target = aceitou ∧ coletou_dentro_validade`** · timestamps simulados (`lote_registrado_em`, `proposta_em`, `resposta_em`, `coleta_em`) · rastreabilidade.
**Geração de candidatas:** as `K = 15` ONGs elegíveis (§2) mais próximas, até 150 km; ≥ 1 `BANCO_ALIMENTOS_RBBA` quando houver dentro do raio. Lotes sem candidata → `sem_candidata`. **Distância:** haversine (linha reta). Definição e derivação de `location_precision` em `DATA_DICTIONARY.md`.

## 5. Como o desfecho é gerado (processo estocástico — nunca regra determinística)
Para cada par (lote *i*, ONG *j*), depois do filtro de elegibilidade por regras explícitas sobre o **declarado**:
1. **Resposta e aceite:** `T_resp ~ LogNormal(·)` (§3.4), só dentro do horário **real**; `logit P(aceita) = β0 + β_apt·aptidao_j + β_cat·afinidade_j[cat_i] + β_cap·f(kg_i / capacidade_efetiva_j) + β_frio·1[exige_frio_i ∧ ¬camara_efetiva_j] + β_tipo·tipo_j + u_j + v_i + ε_ij`, onde `u_j ~ N(0,σ_u²)`, `v_i ~ N(0,σ_v²)` (não observáveis) e `ε_ij ~ Logistic(0,1)`. Resultado `ACEITOU`/`RECUSOU`; `SEM_RESPOSTA` com probabilidade `P(sem_resposta)`.
2. **Coleta:** frota disponível (capacidade/refrigeração **efetivas**); `T_ij ~ LogNormal(μ_ij, σ_T²)`, `μ_ij = γ0 + γ_dist·log(1 + dist_km·desvio) + γ_disp·disponibilidade_j + γ_dia·fim_de_semana + γ_hr·hora`; `coletou_dentro_validade = 1[T_ij ≤ min(janela de retirada, dias_ate_validade·24)]`.
3. **Não determinismo:** coeficientes sorteados por run de intervalos `[PREMISSA]`, mais efeitos aleatórios e ruído de par. O **oráculo** (conhece latentes e coeficientes) deve ficar **bem abaixo de 100%**; se não, o simulador é determinístico demais → reprovado (§9).
4. **Declarado ≠ efetivo:** uma ONG pode passar no filtro (declarado) e ainda **recusar ou não coletar** por capacidade/refrigeração efetivas — fonte realista de erro, **sem** tornar o desfecho uma regra sobre variáveis observáveis.
5. **Contrafactual:** rótulos gerados para **todos** os pares candidatos; em produção só se observa o par acionado (viés de seleção/censura) — limitação declarada.
Coeficientes: sinais esperados por premissa; **magnitudes sem fonte** → resultado do modelo = reflexo do que o simulador codifica.

## 6. Gerador de descrições textuais dos lotes (novo — pendência 2.1)
**Objetivo:** produzir o texto livre que o doador escreveria, **junto** com os rótulos de verdade, para treinar/avaliar a análise semântica (tipo, perecibilidade, refrigeração, validade, quantidade, unidade). **Lacuna conhecida:** não há fonte pública conhecida de descrições de doação rotuladas → textos **SIMULADOS** (`data_origin = SIMULATED`).

**Entradas:** o lote simulado (§4.2): produto, categoria, quantidade+unidade, dias até a validade, temperatura de conservação, `reference_date`.
**Procedimento:**
1. **Famílias de modelos de frase** (`template_family_id`): F1 telegráfica ("10cx iogurte nat 4C vence 3d"); F2 frase completa; F3 mensagem informal; F4 campos/lista. Cada família tem N modelos; **famílias reservadas** (held-out) não entram no treino.
2. **Operadores de variação:** abreviações (cx, un, pct, dz, kg, L); erros de digitação (troca/omissão de letra, acentos, caixa); formatos de data ("vence em 3 dias", "vence amanhã", "val. 15/10", "val 15/10/26", "validade 15/10/2026"); unidade e quantidade ("10 caixas", "2 bandejas", "5kg", "uma dúzia"); temperatura **mencionada** ("mantido a 4 °C", "refrigerado", "congelado") **ou ausente**; textos **curtos e longos**.
3. **Casos difíceis (de propósito; frações são [PREMISSA] com intervalo):** validade **ausente** (10%–25%); **ambígua** ("vence semana que vem"; "03/10" dia/mês ambíguo) (3%–10%); **inconsistente com a categoria** (ex.: folhosas com validade de 200 dias) (2%–5%); texto **vago** ("sobras de padaria", "alimentos diversos") (3%–8%); **duas categorias** ("cesta com frutas e iogurte"; rótulo multirrótulo + flag) (3%–8%). `difficulty_flags` registra cada um.
4. **Rótulo de verdade:** gerado **junto** com o texto (§4.5). `y_validity_source = INFORMADA` quando a data/prazo está no texto; `INFERIDA_PELA_CATEGORIA` quando a validade só pode vir de premissa da categoria; `AUSENTE` quando nem isso é justificável. **Nunca preencher a validade em silêncio.**
5. **Privacidade:** nenhum nome de pessoa, telefone, e-mail, CNPJ, marca fictícia que simule empresa real ou endereço aparece no texto.
6. **Rastreabilidade:** `data_origin = SIMULATED`, `generator_version`, `seed`, `dataset_version`, `template_family_id`, `template_id`, `noise_ops`.
7. **Origem dos nomes de produto:** conforme §3.2 (`product_name_origin`); **não** do PAA.

**Observação metodológica:** no texto simulado o mapeamento produto→categoria é **determinístico por construção** (o léxico define o rótulo), ao contrário do mundo real, onde há ruído de rotulagem. Isso favorece qualquer baseline de palavras-chave.

**Circularidade específica do texto:** o modelo pode aprender **os modelos de frase e o léxico do gerador**, não a linguagem real do doador. Como será relatado:
1. métricas em **três conjuntos separados e rotulados**: (a) simulado, famílias vistas; (b) simulado, **famílias reservadas**; (c) **MANUALLY_LABELED**;
2. comparação sempre com o **baseline de regras/dicionário** (que explora o mesmo léxico);
3. a diferença (a)−(c) é reportada como **estimativa do otimismo da simulação**;
4. rótulo "**simulação**" em toda métrica de (a) e (b); só (c) é "rotulado manualmente".

## 7. Conjunto de teste MANUALLY_LABELED (novo — pendência 2.2)
**Protocolo (a confirmar com a equipe):**
1. **Quem escreve:** membros da equipe, **sem acesso** aos modelos de frase e à lista de nomes do gerador até o conjunto ser congelado; instrução: escrever como um doador real escreveria, com variedade de estilo, incluindo os casos difíceis do §6.3.
2. **Quem rotula:** idealmente **duas pessoas** independentes por texto, mesmo esquema de rótulos do §4.5; divergências resolvidas por adjudicação registrada; **concordância medida** (kappa de Cohen por campo categórico; erro absoluto em dias para validade).
3. **Dados pessoais:** textos reais de grupos de mensagem **só** se anonimizados e com autorização; senão, escritos do zero (a origem real seria `USER_ENTERED`, não `MANUALLY_LABELED`).
4. **Isolamento:** `data_origin = MANUALLY_LABELED`; **fora do treino e da validação**, nem para escolher hiperparâmetros ou limiares; limiares de confiança são escolhidos no conjunto **simulado de validação**. Se a equipe quiser calibrar com dados manuais, deve criar **um segundo conjunto** (`MANUALLY_LABELED_DEV`) — decisão pendente.
5. **Diversidade medida:** reportar a sobreposição de n-gramas entre o conjunto manual e os modelos do gerador (evidência de que a linguagem é diferente); congelar com hash e data.
6. **Métricas:** reportadas **separadamente** das do texto simulado.

**Tamanho mínimo por classe — critério proposto (decisão da equipe PENDENTE; não é um número definido):** o tamanho deve permitir estimar o **recall por classe** com intervalo de confiança de largura aceitável. Para uma proporção `p` com semi-largura `d` e 95% de confiança: `n ≈ 1,96²·p(1−p)/d²`.
| p assumido | d = 0,10 | d = 0,15 |
|---|---|---|
| 0,5 (pior caso) | 96 | 43 |
| 0,8 | 62 | 28 |
**Trade-off:** com ~11 categorias, 62 textos/classe já são ≈ 680 textos (esforço de escrita e dupla rotulagem); com d = 0,15 e p = 0,8 são ≈ 310. Classes raras (casos difíceis) podem usar amostra menor com a limitação **declarada**. A equipe escolhe `d`, `p` e o orçamento de rotulagem; este documento **não** fixa o valor. Convenção usual de leitura de kappa (≥ 0,6 "substancial") é referência, não exigência desta spec.

## 8. Seed, versionamento e reprodutibilidade
- `generator_version` (SemVer; planejado `0.2.0`), `dataset_version = <generator_version>+<hash dos parâmetros>+<seed>`.
- Seed mestre; sub-seeds por entidade com `numpy.random.SeedSequence.spawn` (doadores, lotes, **textos**, latentes, declarados, frota, desfechos); versões de Python/numpy registradas.
- **params v0.2.0** = tabelas das §3 e §4 deste documento (`simulation/params/params_v0.2.0.yaml`, a criar na Fase 1): cada parâmetro com `valor|intervalo`, `tipo (REAL|REF|PREMISSA)`, `fonte`, `justificativa`; hash em `source_parameters`.
- ≥ 5 seeds e cenários (aceitação baixa/média/alta; hortifrúti alto/baixo; declarado fiel/otimista); nunca uma única realização. Testes de determinismo (mesma seed ⇒ mesmo hash).

## 9. Critérios de realismo
### 9.1 Agregados com âncora real (devem passar; reprovação = ajustar premissa ou documentar)
| # | Verificação | Referência real | Critério |
|---|---|---|---|
| R1 | kg/ano por banco RBBA-equivalente | ≈ 411,7 t/relatório/ano (RBBA 2025) | mediana entre 0,5× e 2× (ordem de grandeza) |
| R2 | mix NOVA em kg | 88,2/1,3/4,5/6,0 % | desvio ≤ 2 p.p. por grupo |
| R3 | sazonalidade mensal | índice RBBA 2025 | Spearman ≥ 0,6; erro mensal ≤ 15% |
| R4 | distribuição geográfica de doadores | população (provisório) / CNPJ (futuro) | correlação por UF ≥ 0,9 |
| R5 | cobertura de candidatas | 4.421 municípios com OSC "Assistência social"; 161 com ponto RBBA | proporção de lotes com candidata coerente (reportar) |
| R6 | perda sem destino | 4,85% (RBBA); 1,8% do faturamento (MAPA) | reportar ao lado das referências; **não é meta** |
### 9.2 Texto e logística
| # | Verificação | Critério |
|---|---|---|
| T1 | frações de casos difíceis geradas = parâmetros sorteados | desvio ≤ 1 p.p. |
| T2 | privacidade dos textos | zero ocorrências de padrões de CPF/CNPJ/telefone/e-mail (teste automático) |
| T3 | sobreposição de n-gramas entre famílias de treino e reservadas / manual | **reportada** |
| L1 | tempo de deslocamento estimado | coerente com `dist × desvio / velocidade + serviço`; sem valores negativos |
| L2 | respostas fora do horário real da ONG | zero (respeita §5.1) |
| L3 | capacidade da frota | `kg_lote` ≤ capacidade efetiva nos lotes coletados |
### 9.3 Aceitação/coleta e sanidade
Não há referência real de taxa de aceite/coleta doador→ONG: a taxa é **premissa**; reportar por cenário e **nunca** como "taxa real". O **oráculo** deve ter desempenho bem abaixo de perfeito; monotonicidade (dist ↑ ⇒ P(coleta) ↓) verificada; distribuições marginais arquivadas.

## 10. Circularidade — risco e como será reportado (match)
O modelo supervisionado aprende **a lógica do simulador**, não o mundo real. Obrigações de relato:
1. **Baselines:** aleatório; ONG mais próxima; regra simples sobre **observáveis** (distância, tipo, categoria, declarado); popularidade; regressão logística; gradient boosting.
2. **Ganho sobre a melhor regra simples** como métrica principal.
3. **Teste de misspecificação:** treinar no cenário A e avaliar em B (coeficientes, mix, viés de declaração deslocados).
4. **Partição** por lote/doador e por região/tempo (nunca por par aleatório).
5. **Rótulo em tudo:** "**simulação — não representa desempenho no mundo real**" em relatórios, API, dashboard, README e pitch. Resultados de **rota, tempo de match e comparação entre estratégias** obtidos com premissas simuladas também são "simulação".
6. **Ablação do declarado** (§4.3-3).
7. **Honestidade de produto:** ranking = "ONGs com maior probabilidade **simulada** de aceitar/coletar"; distância em linha reta e tempo estimado **não** são distância viária real.
8. **Caminho para o real:** feedback real (`USER_ENTERED`) em versão futura.

## 11. Pendências (o que esta spec NÃO resolve)
1. **Vida útil por categoria** e **taxa de aceite** — premissas (âncoras parciais em CANDIDATES §G); reconferir os PDFs originais (leitura foi por resumo).
2. **CNPJ** (estabelecimentos por CNAE/município) — bloqueio de acesso e licença; provisório = população.
3. **Licenças** de IPEA/OSC, RBBA, coordenadas, IBGE e TACO — confirmação formal pendente.
4. **Malha oficial do IBGE** (substituir centroides de terceiros) — pendente.
5. **Capacidade/refrigeração/horário reais** das ONGs — inexistentes em fonte pública; permanecem latentes + declarados simulados.
6. **Tamanho do conjunto MANUALLY_LABELED** e escolha de anotadores — **decisão da equipe**.
7. **Análise jurídica da ODbL** para rotas próprias (se a extensão OSRM for aprovada) — pendente.
8. **Parâmetros de frota, resposta da ONG e desvio/velocidade** — premissas sem fonte; validar com operadores (bancos de alimentos, Mesa Brasil).
