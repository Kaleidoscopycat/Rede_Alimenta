# DATA_DICTIONARY.md

Dicionário de dados — Fase 0 revisada (DOADOR → ONG). Parte A: fontes **REAIS** em `data/raw/` (inspecionadas). Parte B: esquema **PLANEJADO** das tabelas SIMULADAS (**ainda não existem**; nenhum dado simulado foi gerado nesta fase). Classes: REAL · PROXY · SIMULADO · PREDITO.

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

## Parte B — Esquema planejado das tabelas SIMULADAS (Fase 1; ver `DATA_SIMULATION_SPEC.md`)

Campos de rastreabilidade em **todas**: `data_origin` (= `SIMULATED`), `generator_version`, `seed`, `dataset_version`, `source_parameters`.

### `sim_donor`
| Campo | Tipo | Classe | Descrição |
|---|---|---|---|
| donor_id | str | SIMULADO | id interno (nunca CNPJ/nome) |
| donor_type | enum | SIMULADO | supermercado, restaurante, padaria, atacadista/Ceasa, indústria, produtor/hortifrúti |
| donor_size | enum | SIMULADO | pequeno/médio/grande |
| municipio_ibge | int | REAL (chave amostrada) | município real |
| donor_geo_basis | enum | — | `POPULACAO_PROXY` \| `CNPJ_ESTABELECIMENTOS` |

### `sim_lot`
| Campo | Tipo | Classe | Descrição |
|---|---|---|---|
| lot_id, donor_id | str | SIMULADO | chaves |
| created_at | datetime | SIMULADO | data-hora simulada |
| categoria | enum | SIMULADO | taxonomia do projeto |
| quantidade_kg | float | SIMULADO | kg |
| dias_ate_validade | float | SIMULADO | premissa por categoria |
| exige_refrigeracao | bool | SIMULADO | derivado da categoria |
| janela_coleta_h | float | SIMULADO | horas |
| dia_semana, hora | int | SIMULADO | — |
| contem_alergenico | bool | SIMULADO | **fora das features do modelo** |
| refeicoes_equiv | float | SIMULADO (conversão) | kg / 0,4 (configurável) |

### `sim_ong_latent` (oculto; nunca exibido com nome/CNPJ da ONG real)
`ong_id` (pseudônimo) · `capacidade_kg_dia` · `tem_camara_fria` · `aptidao_alimentar` · `afinidade_categoria` · `efeito_aleatorio_ong` · `disponibilidade_coleta` — todos **SIMULADO**.

### `sim_pair_outcome` (unidade de observação: lote × ONG candidata)
| Campo | Classe | Descrição |
|---|---|---|
| lot_id, ong_id, ong_tipo | chaves; ong_tipo REAL | `OSC_ASSISTENCIA` \| `BANCO_ALIMENTOS_RBBA` |
| dist_km | **PROXY** | haversine centroide–centroide (ou centroide–ponto RBBA) |
| dist_precisao, mesmo_municipio, rank_distancia | PROXY/REAL (derivado) | — |
| aceitou, coletou, horas_ate_coleta, coletou_dentro_validade | **SIMULADO** | pós-desfecho (não são features) |
| **target** | **SIMULADO** | aceitou ∧ coletou_dentro_validade |
| score_modelo | **PREDITO** | probabilidade/ranking (sempre rotulado "simulação") |

### Features REAIS por ONG/território (camada GOLD)
`ong_tipo`, `modalidade_rbba`, `area_atuacao` (flags IPEA), `natureza_juridica`, `n_osc_assistencia_municipio`, `tem_banco_rbba_municipio`, `populacao_2026`, `paa_adesao` (REAL); `paa_kg_historico_municipio` (PROXY).
