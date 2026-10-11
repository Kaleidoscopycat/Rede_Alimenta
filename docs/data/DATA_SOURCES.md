# DATA_SOURCES.md

Fontes **reais** do projeto (fluxo DOADOR → ONG). **v3 (correção de pendências, 2026-10-02)** — anterior em `archive/DATA_SOURCES_v2_pre_correcao.md`. Detalhe em `DATA_SOURCE_CANDIDATES.md`; hashes em `DATA_LINEAGE.md`. Papel: REAL_FEATURE / PARAMETRO_DE_SIMULACAO / REFERENCIA. Classe: REAL / PROXY (SIMULADO e PREDITO não vêm de fontes — ver `DATA_SIMULATION_SPEC.md`).

| ID | Fonte | Órgão | Arquivo local | Registros reais | Papel | Classe | Status |
|---|---|---|---|---|---|---|---|
| ipea_osc_area | Mapa das OSCs — área/subárea | IPEA | data/raw/ipea_osc/area_subarea.csv | 960.315 | REAL_FEATURE | REAL (elegibilidade PROXY) | NEEDS_REVIEW |
| ipea_osc_dict | Mapa das OSCs — dicionário | IPEA | data/raw/ipea_osc/Dicionario_Dados.xlsx | 94 variáveis | REFERENCIA | — | APPROVED |
| rbba_resumo | RBBA — painel/API resumo | MDS | data/raw/rbba/rbba_resumo.json | 192 pontos + KPIs | REAL_FEATURE + PARAMETRO | REAL | NEEDS_REVIEW |
| ibge_municipios | Municípios | IBGE | data/raw/ibge/ibge_municipios.json | 5.571 | REAL_FEATURE | REAL | APPROVED* |
| ibge_populacao | População 2026 | IBGE | data/raw/ibge/ibge_populacao_municipios_2026.json | 5.571 | REAL_FEATURE | REAL | APPROVED* |
| ibge_coords | Coordenadas de município (terceiros, MIT) | kelvins/municipios-brasileiros | data/raw/ibge_coords/kelvins_municipios.csv | 5.571 | REAL_FEATURE (distância) | PROXY | NEEDS_REVIEW |
| paa_compra_doacao | PAA — compra c/ doação simultânea | MDS | data/raw/paa_mds/paa_execucao_compra_doacao_simultanea.csv | 49.627 | PARAMETRO | REAL (ref.) | APPROVED |
| paa_leite | PAA — leite | MDS | data/raw/paa_mds/paa_execucao_leite.csv | 8.367 | REFERENCIA | REAL | APPROVED |
| paa_municipios | PAA — adesão municipal | MDS | data/raw/paa_mds/paa_municipios_aderidos_2026.csv | 19.032 | REAL_FEATURE | REAL | APPROVED |
| paa_sexo | PAA — agricultores por sexo | MDS | data/raw/paa_mds/paa_agricultores_por_sexo.csv | 29.350 | REFERENCIA (sem uso) | — | APPROVED |
| refs_desperdicio | MAPA 2022; Embrapa 2003; Mesa Brasil Sesc | publicações | — (citações em CANDIDATES §E) | — | PARAMETRO/REFERENCIA | REAL (ref.) | APPROVED c/ ressalvas |
| conab_compendio | Compêndio Conab — PAA 2021 (composição das compras 2020) | Conab | — (lido por resumo; PDF **não baixado**) | publicação | PARAMETRO/REFERENCIA | REAL (ref.) | APPROVED (referência) — dataset Conab: REJECTED |
| anvisa_guia_doacao | Anvisa — Guia para Doação de Alimentos com Segurança Sanitária (2022) | Anvisa | — (lido por resumo) | publicação | PARAMETRO (limites de tempo/temperatura) | REAL (ref.) | **RESTRICTED** |
| mds_guia_avaliacao | MDS — Guia de avaliação de alimentos doados (2018) | MDS | — (lido por resumo) | publicação | REFERENCIA (taxonomia) | REAL (ref.) | **RESTRICTED** |
| anvisa_guia26 | Anvisa — Guia nº 26/2019 Bancos de Alimentos | Anvisa | — (lido por resumo) | publicação | REFERENCIA (classes de perecibilidade) | REAL (ref.) | NEEDS_REVIEW |
| anvisa_guia16 | Anvisa — Guia nº 16/2018 v2 (prazos de validade) | Anvisa | — (lido em cópia de terceiro) | publicação | REFERENCIA (conceito) | REAL (ref.) | **RESTRICTED** |
| mds_catalogo_2018 | MDS — Catálogo de Produtos da Agricultura Familiar (2018) | MDS | — (lido por resumo; 17 nomes obtidos) | publicação | REFERENCIA (nomes de produto) | REAL (nomes) | APPROVED (c/ citação) |
| seduc_go_validade | SEDUC-GO — Critérios de validade (alimentação escolar) | SEDUC-GO | — (lido por resumo) | publicação | REFERENCIA qualitativa | — | NEEDS_REVIEW |
| taco_nepa | TACO 4ª ed. (NEPA/UNICAMP) | UNICAMP | — (**não baixada**) | tabela | REFERENCIA (nomes; **após licença**) | — | NEEDS_REVIEW |
| osm_odbl | OpenStreetMap (ODbL), Nominatim e OSRM públicos | OSM Foundation | — (políticas lidas; **nenhum dado/serviço usado**) | — | — | — | NEEDS_REVIEW (dados) · REJECTED (serviços públicos no produto) |
| cnpj_rfb | Dados Públicos do CNPJ (estabelecimentos) | Receita Federal | — (**não acessado**) | — | PARAMETRO (futuro) | PROXY | NEEDS_REVIEW — **PENDENTE** |
| malha_ibge | Malha municipal oficial (substituta dos centroides de terceiros) | IBGE | — (**não acessada**) | — | REAL_FEATURE (futuro) | — | **PENDENTE** |

**Não acessadas / pendentes:** CNPJ (Receita) — NEEDS_REVIEW; malha municipal oficial IBGE — não acessada; equipamentos SAN — não localizado; **tabela de vida útil por categoria — não localizada (premissa)**; Conab dataset — REJECTED. **Nomes de produto:** não vêm do PAA/MDS-SAGI (sem produto) nem da TACO (NEEDS_REVIEW); ver `product_name_origin` no dicionário.
\* APPROVED para pesquisa; licença explícita do IBGE a citar antes de produção.

Acesso: arquivos RAW baixados por API/portal oficial em 2026-09-23 (fase anterior) e `ibge_coords` do GitHub em 2026-10-02. Nenhum dado foi gerado sinteticamente nesta fase.

## Fase 2 · Parte 1 — fontes no PostgreSQL
Tabela `public_data_sources` (+ `public_dataset_versions`): 7 fontes (IPEA/OSC, RBBA, IBGE municípios, IBGE população, coordenadas de terceiros, PAA ×2) com `review_status` e `publication_cleared=false`. Organizações importadas do gold com `source`, `source_record_id`, `source_url`, `last_verified_at` e `data_origin=PUBLIC`. Pendências: `docs/data/PENDING_LICENSE_CONFIRMATIONS.md`.
