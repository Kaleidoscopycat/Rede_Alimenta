# DATA_SOURCES.md

Fontes **reais** do projeto (fluxo DOADOR → ONG). Detalhe em `DATA_SOURCE_CANDIDATES.md`; hashes em `DATA_LINEAGE.md`. Papel: REAL_FEATURE / PARAMETRO_DE_SIMULACAO / REFERENCIA. Classe: REAL / PROXY (SIMULADO e PREDITO não vêm de fontes — ver `DATA_SIMULATION_SPEC.md`).

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

**Não acessadas / pendentes:** CNPJ (Receita) — NEEDS_REVIEW; malha municipal oficial IBGE — não acessada; equipamentos SAN — não localizado; vida útil por categoria — não localizado; CONAB — REJECTED.
\* APPROVED para pesquisa; licença explícita do IBGE a citar antes de produção.

Acesso: arquivos RAW baixados por API/portal oficial em 2026-09-23 (fase anterior) e `ibge_coords` do GitHub em 2026-10-02. Nenhum dado foi gerado sinteticamente nesta fase.
