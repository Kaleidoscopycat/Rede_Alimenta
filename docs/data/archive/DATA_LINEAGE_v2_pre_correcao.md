# DATA_LINEAGE.md

Linhagem das fontes na camada **RAW** (cópia original; **nunca modificada**). Campos exigidos pelo AGENTS.md §7: `source_id, source_name, source_url, source_dataset, source_updated_at, ingested_at, pipeline_version`, mais `sha256` e tamanho (checksums gerados por `scripts/validate_phase0_data.py` → `data/metadata/raw_checksums.json`, 14 arquivos).

`data_origin = PUBLIC` para tudo abaixo. **Nenhum dado SIMULADO existe nesta fase.**

| source_id | source_name | source_url | source_dataset | source_updated_at | ingested_at | pipeline_version | sha256 | bytes |
|---|---|---|---|---|---|---|---|---|
| paa_compra_doacao | MDS/SAGI | aplicacoes.mds.gov.br/sagi/servicos/misocial | PAA Compra c/ Doação Simultânea | 2026-06 (anomes_s máx.) | 2026-09-23 | v0-fase0-raw | `164543861c927a9a1188676cdd333895b677bdbc499fea8be6b5e36e163b70fe` | 2.079.436 |
| paa_leite | MDS/SAGI | aplicacoes.mds.gov.br/sagi/servicos/misocial | PAA Incentivo ao Leite | 2026-06 | 2026-09-23 | v0-fase0-raw | `e0ce63da5a9ac1e439cd19fd0983bf9274ce5ed0f141c33762c6df1c58890eb9` | 289.415 |
| paa_municipios | MDS/SAGI | aplicacoes.mds.gov.br/sagi/servicos/misocial | PAA Municípios Aderidos | 2026-06 | 2026-09-23 | v0-fase0-raw | `a2ad9de34eb1f4038a2f209d512deb63b7f5cf0ea4f8fc2bd4324a0e88210954` | 609.785 |
| paa_sexo | MDS/SAGI | aplicacoes.mds.gov.br/sagi/servicos/misocial | PAA Agricultores por Sexo (sem uso) | 2026-06 | 2026-09-23 | v0-fase0-raw | `206fd19479e6351ccce2e28707f5a0b3941c7eff8fa99d889a6e721099c80013` | 582.679 |
| ibge_municipios | IBGE | servicodados.ibge.gov.br/api/v1/localidades/municipios | Municípios | não verificável | 2026-09-23 | v0-fase0-raw | `86ecdccdf97d72e7e5e46f0854cfcea8bacc28154cc1bc4ed0e6110e3a6c9c02` | 2.470.036 |
| ibge_populacao | IBGE/SIDRA | servicodados.ibge.gov.br/api/v3/agregados/6579 | População estimada 2026 | 2026 | 2026-09-23 | v0-fase0-raw | `36b8bd4c9ec1c74f0b1e76cbb108fec91571c351b9423e508bf0f4350e6d27b0` | 689.494 |
| ibge_coords | kelvins/municipios-brasileiros (terceiros) | github.com/kelvins/municipios-brasileiros (csv/municipios.csv) | Coordenadas de municípios | commit 2025-12-10 | 2026-10-02 | v0-fase0-raw | `22bd03d004361329f69ddfa3f6c99cd53012aa53972a172e10b141288ad0b1fe` | 390.201 |
| ipea_osc_area | IPEA | dados.gov.br/dados/conjuntos-dados/mapaosc | Mapa das OSCs: área/subárea | não verificável | 2026-09-23 | v0-fase0-raw | `c2e07a328ac5beb8f8cdd03abd2da58029115ec6949a6cf6b598550d019925e8` | 266.910.744 |
| ipea_osc_dict | IPEA | dados.gov.br/dados/conjuntos-dados/mapaosc | Dicionário (XLSX) | não verificável | 2026-09-23 | v0-fase0-raw | `6b4b4484785b8534644e8751ed9243c1a4f048b73e596c7b1ac5028a11be4f30` | 9.245 |
| rbba_resumo | MDS/Alimenta Cidades | alimentacidades.digital/rbba/api/resumo | RBBA resumo 2025 | 2025 (anos 2025. 2024) | 2026-09-23 | v0-fase0-raw | `682df159a74da024fc89d928bae39ff3453c5f5585ce6a69e37b20d6935ad1cf` | 122.567 |

## Fluxo previsto (Fase 1)
`RAW` (esta fase) → `BRONZE` (padronização; RBBA ganha `geo_quality`: `OK` | `SUSPEITA` p/ BA000038 e BA000307; OSC normalizada com municípios IBGE) → `SILVER` (limpeza; elegibilidade de ONG; centroides) → `GOLD` (par lote × ONG; **único** ponto onde dados reais e simulados se encontram, com `data_origin` preservado por coluna/tabela de origem).

## Registro de operações desta revisão (2026-10-02)
- Re-validação integral do RAW (`validate_phase0_data.py`): leitura de 100% das 960.315 linhas IPEA/OSC (antes: amostra de 50.000).
- Inclusão de `data/raw/ibge_coords/` (4 arquivos de terceiros; MIT) — origem GitHub, baixados em 2026-10-02.
- Fontes **NÃO acessadas por bloqueio de rede**: malha municipal oficial IBGE, CNPJ/Receita, termos do Mapa das OSC (robots), dados.gov.br.
- RAW das demais fontes **inalterado** desde 2026-09-23 (checksums registrados nesta data; não há checksum anterior para comparação — limitação).
