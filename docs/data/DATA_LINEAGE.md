# DATA_LINEAGE.md

**v3 (correção de pendências, 2026-10-02)** — anterior em `archive/DATA_LINEAGE_v2_pre_correcao.md`.

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

## Correção de pendências (2026-10-02, v3)
**RAW:** revalidado por `scripts/validate_phase0_data.py`; checksums idênticos aos da execução anterior (cópia em `archive/raw_checksums_v2_pre_correcao.json`). **Nenhum dado novo baixado; nada baixado novamente.**

### Fontes consultadas por leitura (NÃO armazenadas no RAW; sem hash)
`data_origin = PUBLIC` (publicações). Acesso em **2026-10-02** por leitura/resumo automático (WebFetch); `ingested_at` = N/A (não ingeridas). `pipeline_version` = N/A.
| source_id | source_name | source_url | source_dataset | source_updated_at |
|---|---|---|---|---|
| conab_compendio | Conab | gov.br/conab/.../compendio-v30-paa-2021.pdf | Compêndio de Estudos — PAA 2021 | 2021 |
| anvisa_guia_doacao | Anvisa | fcna.abras.com.br/downloads/arq/Guia_para_Doacao_de_Alimentos_ANVISA.pdf (cópia) | Guia para Doação de Alimentos com Segurança Sanitária | 2022 |
| mds_guia_avaliacao | MDS/SESAN | mds.gov.br/webarquivos/publicacao/seguranca_alimentar/ (livro 'Guia avaliação alimentos') | Guia de avaliação de alimentos doados | 2018 |
| anvisa_guia26 | Anvisa | pesquisa.anvisa.gov.br/upload/surveys/15455/files/GUIA BANCO ALIMENTOS.pdf | Guia nº 26/2019 v1 | 21/06/2019 |
| anvisa_guia16 | Anvisa | regoola.io/.../1Guia-no-16_2018_Versao-2.pdf (cópia de terceiro) | Guia nº 16/2018 v2 | 03/07/2024 |
| mds_catalogo_2018 | MDS/SESAN | mds.gov.br/.../Catalogo_Produtos_Agricultura_Familiar.pdf | Catálogo de Produtos da Agricultura Familiar | 2018 |
| seduc_go_validade | SEDUC-GO | goias.gov.br/educacao/.../Criterios_de_validade_2024-aa6.pdf | Critérios de validade dos alimentos | não especificada |
| mds_rbba_2015 | MDS | mds.gov.br/.../caisan/RBBA/MINUTA_Documento_RBBA.pdf | Documento RBBA | 2015 |
| nepa_taco | NEPA/UNICAMP | nepa.unicamp.br/categoria/taco/ | TACO 4ª ed. (página; tabela não baixada) | não verificável |
| osm_politicas | OSM Foundation / OSRM | openstreetmap.org/copyright; operations.osmfoundation.org/policies/nominatim/; github.com/Project-OSRM/osrm-backend/wiki/Demo-server; osmfoundation.org/wiki/Licence/Licence_and_Legal_FAQ | políticas e licença | não verificável |
**Inacessíveis (não contornados):** `mapaosc.ipea.gov.br` (robots.txt), `repositorio.ipea.gov.br` (robots.txt), `dados.gov.br/dataset/mapaosc` (HTTP 401); no download de dados: `ibge.gov.br`, `servicodados.ibge.gov.br`, `geoftp.ibge.gov.br`, `dadosabertos.rfb.gov.br`, `aplicacoes.mds.gov.br`, `gov.br/mds`.

### Registro de transformações lógicas (sem alteração do RAW)
`geo_quality` e `location_precision` serão derivados na camada BRONZE conforme `DATA_DICTIONARY.md` (Parte C); o script desta etapa **calcula e testa** a derivação sem escrever dados derivados. **Dados SIMULADOS: nenhum gerado.**

## Fase 1 — Registro de execução (2026-10-03)

Camadas geradas por `python -m pipelines.run_all` (versão de pipeline 1.0.0), sem alteração do RAW (checksums verificados contra `data/metadata/raw_checksums.json`; teste `tests/test_ingestion.py`):

| Camada | Artefatos |
|---|---|
| bronze | `ibge_municipios`, `ibge_populacao`, `ibge_coords`, `ipea_osc`, `rbba_pontos` (+`rbba_referencia.json`), `paa_compra_doacao`, `paa_leite`, `paa_municipios` |
| silver | `municipios`, `osc` (960.315 linhas), `rbba` (192), `paa_*` |
| gold | `territory` (5.571 municípios), `organizations` (54.590 = 54.398 OSC de assistência social + 192 bancos RBBA) |

Dados SIMULADOS (`data/simulated/<tag>/`) são gerados por `simulation/generator.py` e nunca se misturam às camadas acima; a junção ocorre apenas em `ml/dataset.py`, que preserva a origem por coluna (`FEATURE_ORIGIN`). Artefatos do modelo: `ml/artifacts/ranker/` e `ml/artifacts/semantic/`. O manifesto `data/metadata/ingestion_manifest.json` guarda URL, timestamp, checksum, versão, tamanho e número de registros por fonte/camada.

Fontes NÃO obtidas nesta fase: base de CNPJ/estabelecimentos doadores (`pipelines/donors_universe` vazio), Conab (`pipelines/conab` vazio), malha geográfica IBGE (uso só de centroides de terceiros, `PROXY`).

## Fase 2 · Parte 1 — banco
gold (parquet) → `database/importers.py` → PostgreSQL: 54 590 `organizations` (+ `organization_locations`; 190 EXACT, 54 400 `MUNICIPALITY_CENTROID`), 5 571 `municipalities`, 27 855 `public_indicators`, 11 `food_categories`. Simulador (`data/simulated/main`, `dataset_version 0.2.0+477ed37e+20261003`) → 54 590 `organization_profiles`, 8 000 `donors`, 60 000 `donations`/`donation_items`, todos `data_origin=SIMULATED` (lotes históricos com status `HISTORICAL`). Não importados: os 895 mil pares contrafactuais `sim_pair_outcome` (permanecem em parquet). Relatório: `docs/data/IMPORT_REPORT_FASE2P1.json`. A importação é idempotente.
