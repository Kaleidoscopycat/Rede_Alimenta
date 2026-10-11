# DATA_DICTIONARY.md

Dicionário de dados — Fase 0 revisada (DOADOR → ONG). Parte A: fontes **REAIS** em `data/raw/` (inspecionadas). Parte B: esquema **PLANEJADO** das tabelas SIMULADAS e do conjunto MANUALLY_LABELED (**ainda não existem**; nenhum dado simulado foi gerado). Parte C: campos transversais (`data_origin`, `location_precision`, `geo_quality`). Versão v3 (correção de pendências, 2026-10-02); anterior em `archive/DATA_DICTIONARY_v2_pre_correcao.md`. Classes: REAL · PROXY · SIMULADO · PREDITO.

## Parte A — Fontes reais


## PAA — Compra com Doação Simultânea (`paa_execucao_compra_doacao_simultanea.csv`)
| Coluna | Tipo | Descrição |
|---|---|---|
| codigo_ibge | int | Código IBGE do município (6 dígitos) |
| anomes_s | int | Ano-mês de referência (formato AAAAMM) |
| paa_qtd_agricul_familiar_exec_compra_doacao_simul_i | int | Quantidade de agricultores familiares participantes |
| paa_vlr_pago_exec_compra_doacao_simul_d | float | Valor pago (R$) na modalidade |
| paa_qtd_alim_adquiridos_exec_compra_doacao_simul_d | float | Quantidade de alimentos adquiridos (kg) |

## PAA — Incentivo ao Leite (`paa_execucao_leite.csv`)
| Coluna | Tipo | Descrição |
|---|---|---|
| codigo_ibge | int | Código IBGE do município |
| anomes_s | int | Ano-mês de referência |
| paa_qtd_agricul_familiar_exec_incentivo_leite_i | int | Agricultores familiares na modalidade leite |
| paa_vlr_pago_exec_incentivo_leite_d | float | Valor pago (R$) |
| paa_qtd_alim_adquiridos_exec_incentivo_leite_i | int | Quantidade de leite adquirido |

## PAA — Municípios Aderidos (`paa_municipios_aderidos_2026.csv`)
| Coluna | Tipo | Descrição |
|---|---|---|
| codigo_ibge | int | Código IBGE do município |
| anomes_s | int | Ano-mês de referência |
| sigla_uf | str | Sigla da UF |
| municipio | str | Nome do município |
| paa_indicador_adesao_municipio_i | int (0/1) | 1 = município aderiu ao PAA naquele mês |

## PAA — Agricultores por Sexo (`paa_agricultores_por_sexo.csv`)
| Coluna | Tipo | Descrição |
|---|---|---|
| codigo_ibge | int | Código IBGE do município |
| anomes_s | int | Ano-mês de referência |
| paa_qtd_agricul_familiar_sexo_masculino_i | int | Agricultores familiares do sexo masculino |
| paa_qtd_agricul_familiar_sexo_feminino_i | int | Agricultores familiares do sexo feminino |
| paa_qtd_agricul_familiar_sem_info_sexo_i | int | Agricultores sem informação de sexo |

## IBGE — Municípios (`ibge_municipios.json`)
Estrutura: lista de objetos com `id` (código IBGE 7 dígitos), `nome`, `microrregiao`, `mesorregiao` (com `UF.id`, `UF.sigla`, `UF.nome`, `regiao`), `regiao-imediata`, `regiao-intermediaria`.

## IBGE — População (`ibge_populacao_municipios_2026.json`)
Estrutura SIDRA padrão: `resultados[].series[].localidade.id/nome` + `serie.<ano>` (população estimada, string numérica).

## IPEA — Mapa das OSCs (`area_subarea.csv`) — 960.315 linhas, 68 colunas
Colunas 0–10: identificação e município/UF; 12–22: 11 flags de **área** (usar); 24–67: 44 flags de **subárea** (**inconsistentes com a área — não usar**, ver CANDIDATES A1). Principais: `id_osc, cd_identificador_osc (CNPJ), tx_razao_social_osc, tx_nome_fantasia_osc, dt_fundacao_osc, tx_nome_classe_atividade_economica, cd_natureza_juridica_osc, edmu_cd_municipio, edmu_nm_municipio, eduf_cd_uf, eduf_sg_uf` + colunas binárias por área/subárea de atuação (ex.: `Assistência social`, `Saúde`, `Educação e pesquisa`). Ver `Dicionario_Dados.xlsx` (94 variáveis documentadas) para descrição completa de cada coluna.

## RBBA — API resumo (`rbba_resumo.json`)
- `kpis`: objeto com agregados nacionais (bancos, aderidos, municipios, ufs, kg_recebidos, kg_doados, kg_perdidos, pct_perda, pessoas_atendidas, instituicoes, etc.)
- `pontos`: GeoJSON FeatureCollection — cada feature tem `geometry.coordinates [lon, lat]` e `properties` (identificador, nome, cidade, uf, modalidade)
- `graficos`: dados adicionais para os gráficos do painel (distribuição mensal, origem dos alimentos, perfil de processamento, etc.)

## IBGE — Coordenadas de município (`ibge_coords/kelvins_municipios.csv`) — PROXY
| Coluna | Tipo | Descrição |
|---|---|---|
| codigo_ibge | int (7 díg.) | chave; casa 100% com IBGE |
| nome | str | nome do município |
| latitude, longitude | float | ponto único por município (sede/centroide **não especificado**) |
| capital, codigo_uf, siafi_id, ddd, fuso_horario | misc | metadados de terceiros (sem uso) |

## RBBA — conteúdo adicional de `rbba_resumo.json` usado na calibração
`graficos.mensal[{mes,recebido,doado}]` (kg 2025) · `graficos.origens[{categoria,valor,pct}]` · `graficos.classificacao` (NOVA) · `graficos.modalidades` · `graficos.operacionais` · `graficos.perdas_momento`. **Anomalias:** `BA000038` e `BA000307` com coordenada incoerente (usar centroide; `geo_quality=SUSPEITA`). Campos de pessoas atendidas/instituições = **contexto agregado, fora do escopo de modelagem**.

## Parte B — Esquema planejado (Fase 1; ver `DATA_SIMULATION_SPEC.md` v0.2.0)

Campos de rastreabilidade em **todas** as tabelas simuladas: `data_origin` (= `SIMULATED`; `MANUALLY_LABELED` no conjunto manual), `generator_version`, `seed`, `dataset_version`, `source_parameters`.

### `taxonomy_category` / `taxonomy_product` (PREMISSA DO PROJETO, não dado de fonte)
| Campo | Descrição |
|---|---|
| categoria (código) | HORT_FOLHOSAS, HORT_RAIZES, HORT_FRUTOS, FRUTAS, PANIFICADOS, CARNES_PESCADOS, LATICINIOS_OVOS, REFEICOES_PRONTAS, GRAOS_CEREAIS, INDUSTRIALIZADOS, BEBIDAS |
| perecibilidade | `NAO_PERECIVEL` \| `PERECIVEL_BAIXO_RISCO` \| `PERECIVEL_REFRIGERADO_CONGELADO` \| `PRONTO_ALTO_RISCO` |
| temperatura_conservacao | `AMBIENTE` \| `REFRIGERADO` \| `CONGELADO` |
| dias_validade_min/max | **PREMISSA** com intervalo (spec §3.2); âncoras parciais citadas |
| nova_group | premissa de mapeamento (guia NOVA não lido; usado só no check R2) |
| produto | nome do produto |
| **product_name_origin** | `MDS_CATALOGO_2018` \| `CONAB_COMPENDIO_2021` \| `MESA_BRASIL_SESC` \| `SEDUC_GO_2024` \| `PREMISSA_PROJETO` — **nunca** "PAA" nem "TACO" (TACO = NEEDS_REVIEW) |

### `sim_donor`
| Campo | Classe | Descrição |
|---|---|---|
| donor_id | SIMULADO | id interno (nunca CNPJ/nome) |
| donor_type, donor_size | SIMULADO | tipo/porte |
| municipio_ibge, uf | REAL (chave amostrada) | município real |
| donor_geo_basis | — | `POPULACAO_PROXY` \| `CNPJ_ESTABELECIMENTOS` |
| location_precision | — | `MUNICIPALITY_CENTROID` (sempre) |

### `sim_lot`
| Campo | Classe | Descrição |
|---|---|---|
| lot_id, donor_id, created_at | SIMULADO | chaves e data-hora simulada |
| categoria, produto, product_name_origin, perecibilidade, temperatura_conservacao | SIMULADO | taxonomia v0.2 |
| quantidade_kg, quantidade, unidade | SIMULADO | kg e unidade usada no texto |
| dias_ate_validade | SIMULADO | premissa por categoria |
| exige_refrigeracao | SIMULADO | derivado |
| janela_retirada_inicio, janela_retirada_fim, dias_retirada, tempo_carga_min | SIMULADO | **substituem** `janela_coleta_h` (derivada = fim − início) |
| contem_alergenico | SIMULADO | **fora das features do modelo** |
| refeicoes_equiv | SIMULADO (conversão) | `quantidade_kg / 0,4` (`MEAL_KG`, configurável; **mesmo valor do AGENTS.md e da spec**) |

### `sim_lot_text` (novo) — descrições textuais
| Campo | Classe | Descrição |
|---|---|---|
| text_id, lot_id | SIMULADO | chaves |
| texto | SIMULADO | texto livre (sem nome de pessoa, telefone, e-mail, CNPJ, endereço) |
| template_family_id, template_id, noise_ops[], difficulty_flags[], reference_date | SIMULADO | rastreio do gerador |
| y_categoria (+flag multirrótulo), y_produto, y_perecibilidade, y_exige_refrigeracao | SIMULADO | rótulos de verdade |
| y_dias_ate_validade | SIMULADO | nulo se ausente |
| y_validity_source | SIMULADO | `INFORMADA` \| `INFERIDA_PELA_CATEGORIA` \| `AUSENTE` |
| y_quantidade, y_unidade | SIMULADO | — |

### `manual_labeled_text` (novo) — conjunto de teste (**não gerado nesta etapa**)
Mesmos rótulos `y_*` de `sim_lot_text`, **sem** `template_*`; `data_origin = MANUALLY_LABELED`; `annotator_a`, `annotator_b` (pseudônimos), `adjudicado_por`, `frozen_at`, `sha256_conjunto`. **Nunca** entra em treino, validação ou ajuste de limiar.

### `sim_ong_latent` (**oculto** — nunca feature, regra ou exibição)
`ong_id` (pseudônimo) · `capacidade_efetiva_kg_dia` · `camara_fria_efetiva` · `aptidao_alimentar` · `afinidade_categoria[k]` · `efeito_aleatorio_ong` · `disponibilidade_coleta` · `horario_funcionamento_real` — todos **SIMULADO**.

### `sim_ong_declared` (novo) — observável, **SIMULADO**, declarado ≠ real
| Campo | Descrição |
|---|---|
| ong_id | pseudônimo (mesma chave do latente) |
| capacidade_declarada_kg_dia | **faixa**, derivada da capacidade efetiva com viés e ruído (spec §4.3) |
| camara_fria_declarada | pode divergir da efetiva (falso positivo/negativo) |
| categorias_aceitas_declaradas | subconjunto ruidoso das categorias com afinidade |
| horario_funcionamento_declarado, dias_funcionamento_declarados | real ± desvio |
| **rótulo** | exibido sempre com "SIMULADO"; **nunca** junto ao nome/CNPJ da ONG real como característica dela |

### `sim_fleet` (novo)
`fleet_id`, `ong_id`, `tipo_veiculo` (`UTILITARIO` \| `VAN_FURGAO` \| `CAMINHAO_BAU_MEDIO` \| `CAMINHAO_BAU_GRANDE`), `capacidade_kg`, `refrigerado`, `base_municipio_ibge` (REAL), `location_precision` — SIMULADO (premissas sem fonte; spec §3.4).

### `sim_pair_outcome` — unidade de observação: lote × ONG candidata
| Campo | Classe | Descrição |
|---|---|---|
| lot_id, ong_id, ong_tipo | chaves; `ong_tipo` REAL | `OSC_ASSISTENCIA` \| `BANCO_ALIMENTOS_RBBA` |
| dist_km | **PROXY** | haversine (linha reta) entre os dois pontos; **não** é distância viária |
| location_precision_doador, location_precision_ong | ver Parte C | alerta/feature |
| geo_quality_ong | ver Parte C | — |
| tempo_deslocamento_est_h, razao_deslocamento_validade | **SIMULADO** (premissas) | `dist × desvio ÷ velocidade + serviço`; estimativa |
| mesmo_municipio, rank_distancia | REAL/PROXY (derivados) | — |
| campos `*_declarada` da ONG | SIMULADO (observável) | features rotuladas |
| elegivel_regra, motivos_exclusao | derivado | regras eliminatórias explícitas sobre o **declarado** |
| resposta, horas_resposta | **SIMULADO** | `ACEITOU` \| `RECUSOU` \| `SEM_RESPOSTA` (pós-desfecho, não feature) |
| coletou, horas_ate_coleta, coletou_dentro_validade | **SIMULADO** | pós-desfecho |
| **target** | **SIMULADO** | `aceitou ∧ coletou_dentro_validade` |
| lote_registrado_em, proposta_em, resposta_em, coleta_em | SIMULADO | timestamps do ciclo (tempo de match) |
| score_modelo | **PREDITO** | sempre rotulado "simulação" |

### Features REAIS por ONG/território (camada GOLD)
`ong_tipo`, `modalidade_rbba`, `area_atuacao` (flags IPEA), `natureza_juridica`, `n_osc_assistencia_municipio`, `tem_banco_rbba_municipio`, `populacao_2026`, `paa_adesao` (REAL); `paa_kg_historico_municipio` (PROXY).

## Parte C — Campos transversais

### `data_origin` (valores aceitos — AGENTS.md §2)
| Valor | Significado |
|---|---|
| `PUBLIC` | dado de fonte pública real (RAW/BRONZE/SILVER) |
| `SIMULATED` | gerado pelo simulador documentado, versionado e com seed |
| `MANUALLY_LABELED` | texto escrito e rotulado à mão pela equipe, fora do treino/validação |
| `USER_ENTERED` | cadastrado futuramente por usuários reais |
*(O AGENTS.md §7 lista apenas PUBLIC \| SIMULATED \| USER_ENTERED; ver `FASE0_CORRECAO_LOG.md` item de verificação.)*

### `location_precision` (definição e derivação)
| Valor | Quando | Exibição |
|---|---|---|
| `EXACT` | ponto georreferenciado **da própria fonte** (hoje: bancos RBBA) **e** coordenada válida: dentro do retângulo do Brasil (lat −34..6; lon −74..−32) **e** a ≤ 100 km do centroide do município correspondente (`geo_quality ≠ SUSPEITA`) | mostrar normalmente |
| `MUNICIPALITY_CENTROID` | (a) ONG do IPEA (só município); (b) ponto RBBA marcado `SUSPEITA`; (c) doadores e frota simulados (município real) | **alerta ao usuário**: "localização aproximada (centro do município)"; a distância pode errar muito dentro do mesmo município |
| `NONE` | sem município nem coordenada (hoje: **32 OSCs** do IPEA sem município) | **não ranqueável por distância, de forma explícita** (valor adicional à lista do AGENTS.md — ver log de verificação) |

**Notas:** os centroides vêm de compilação de terceiros (MIT), origem primária **não confirmada** → `MUNICIPALITY_CENTROID` é **PROXY**, limitação conhecida (ver `DATA_LICENSES.md`). Distância no mesmo município = 0 km por construção (`mesmo_municipio` obrigatório).

### `geo_quality` (derivação a partir dos dados baixados — testada em `validate_phase0_data.py`)
Aplica-se aos 192 pontos RBBA (distância haversine ponto × centroide do município casado por nome+UF; 192/192 casam):
| Valor | Regra | Contagem atual |
|---|---|---|
| `OK` | ≤ 25 km | **187** |
| `REVISAR` | > 25 e ≤ 100 km (município grande ou coordenada duvidosa; **permanece EXACT**, com alerta de revisão) | **3** (`BA000213` Blumenau 96,1 km; `BA000305` Santa Luzia 48,0 km; `BA000074` Jaíba 40,5 km) |
| `SUSPEITA` | > 100 km — **coordenada incoerente no RAW** | **2** (`BA000038` Imperatriz/MA: lat −54,91, ~5.492 km; `BA000307` Três Corações/MG: lat +21,72, sinal invertido, ~4.827 km) → `location_precision = MUNICIPALITY_CENTROID`, coordenadas originais preservadas em `lat_raw`/`lon_raw`; **RAW não corrigido** |
| `NAO_APLICAVEL` | ONG sem ponto próprio (OSC IPEA; doador/frota simulados) | — |
Os limiares (25 e 100 km) são **escolha metodológica** desta fase, não dado de fonte; revisáveis quando a malha oficial do IBGE for obtida.

### Contagem esperada de `location_precision` (conferida no log de validação)
RBBA `EXACT` = 190 · RBBA `MUNICIPALITY_CENTROID` = 2 · OSC `MUNICIPALITY_CENTROID` = 960.283 · OSC `NONE` = 32.
