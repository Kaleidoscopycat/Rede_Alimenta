# DATA_SOURCE_CANDIDATES.md

**Projeto:** Rede Alimenta IA
**Fase:** 0 — Data Discovery e Viabilidade Comercial
**Data de geração:** 2026-09-23
**Metodologia:** Todas as fontes abaixo foram acessadas de fato (download real via API oficial ou portal de dados abertos), com amostra inspecionada programaticamente (pandas) e validação de schema. Nenhum dado foi simulado, inventado ou gerado por IA. Ver `docs/data/VALIDATION_LOG.txt` para o log completo da validação programática.

---

## 1. PAA — Execução: Compra com Doação Simultânea

- **Nome:** Execução do PAA — modalidade Compra com Doação Simultânea (histórico mensal por município)
- **Órgão:** Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome (MDS)
- **URL (API real utilizada):** `https://aplicacoes.mds.gov.br/sagi/servicos/misocial/?fq=anomes_s:20*&q=*:*&rows=1000000&sort=anomes_s desc, codigo_ibge asc&wt=csv&fl=codigo_ibge,anomes_s,paa_qtd_agricul_familiar_exec_compra_doacao_simul_i,paa_vlr_pago_exec_compra_doacao_simul_d,paa_qtd_alim_adquiridos_exec_compra_doacao_simul_d&fq=paa_qtd_alim_adquiridos_exec_compra_doacao_simul_d:*`
- **URL de descoberta (catálogo):** `https://dados.gov.br/dados/conjuntos-dados/programa-de-aquisicao-de-alimentos-paa`
- **Formato:** CSV (API SAGI/MDS, Solr-based, também retorna JSON)
- **Acesso:** API pública (sem autenticação)
- **Atualização:** Mensal (dado mais recente observado: 2026-06 / anomes_s=202606)
- **Granularidade:** Município × mês
- **Colunas disponíveis:** `codigo_ibge, anomes_s, paa_qtd_agricul_familiar_exec_compra_doacao_simul_i, paa_vlr_pago_exec_compra_doacao_simul_d, paa_qtd_alim_adquiridos_exec_compra_doacao_simul_d`
- **Cobertura geográfica:** Nacional (todos os municípios com execução registrada)
- **Período histórico:** 2021-01 a 2026-06 (confirmado programaticamente)
- **Quantidade REAL de registros:** 49.627 linhas (verificado via pandas, arquivo `paa_execucao_compra_doacao_simultanea.csv`, 2.079.436 bytes)
- **Licença:** Creative Commons Attribution (CC-BY), conforme metadado do conjunto de dados em dados.gov.br
- **Uso comercial permitido?** Sim (CC-BY permite uso comercial com atribuição)
- **Atribuição necessária?** Sim — atribuir ao Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome (MDS)
- **Presença de dados pessoais?** Não. Dados agregados por município; não há identificação de indivíduos.
- **Utilidade para o projeto:** Alta. Fornece histórico real de execução financeira e volume de alimentos adquiridos por município, base para feature de "histórico PAA" e "quantidade histórica distribuída (proxy de oferta)".
- **Classificação:** **APPROVED**

---

## 2. PAA — Execução: Incentivo ao Leite

- **Nome:** Execução do PAA — modalidade Incentivo à Produção e Consumo de Leite
- **Órgão:** MDS
- **URL (API real):** `https://aplicacoes.mds.gov.br/sagi/servicos/misocial/?fq=anomes_s:20*&q=*:*&rows=1000000&sort=anomes_s desc, codigo_ibge desc&wt=csv&fl=codigo_ibge,anomes_s,paa_qtd_agricul_familiar_exec_incentivo_leite_i,paa_vlr_pago_exec_incentivo_leite_d,paa_qtd_alim_adquiridos_exec_incentivo_leite_i&fq=paa_vlr_pago_exec_incentivo_leite_d:*`
- **Formato:** CSV (API SAGI/MDS)
- **Acesso:** API pública
- **Atualização:** Mensal
- **Granularidade:** Município × mês
- **Colunas:** `codigo_ibge, anomes_s, paa_qtd_agricul_familiar_exec_incentivo_leite_i, paa_vlr_pago_exec_incentivo_leite_d, paa_qtd_alim_adquiridos_exec_incentivo_leite_i`
- **Cobertura geográfica:** Nacional
- **Período histórico:** 2021-01 a 2026-06 (confirmado)
- **Quantidade REAL de registros:** 8.367 linhas (verificado via pandas)
- **Licença:** CC-BY (mesmo conjunto de dados PAA)
- **Uso comercial permitido?** Sim
- **Atribuição necessária?** Sim (MDS)
- **Presença de dados pessoais?** Não
- **Utilidade para o projeto:** Média — complementa histórico de execução PAA, modalidade específica (leite), útil como feature adicional de cobertura do programa.
- **Classificação:** **APPROVED**

---

## 3. PAA — Municípios Aderidos (indicador de adesão)

- **Nome:** Indicador de adesão municipal ao PAA
- **Órgão:** MDS
- **URL (API real):** `https://aplicacoes.mds.gov.br/sagi/servicos/misocial/?fl=codigo_ibge,anomes_s,sigla_uf,municipio,paa_indicador_adesao_municipio_i&fq=paa_indicador_adesao_municipio_i:*&q=*:*&rows=1000000&sort=anomes_s desc, codigo_ibge asc&wt=csv&fq=anomes_s:2026*`
- **Formato:** CSV (API SAGI/MDS)
- **Acesso:** API pública
- **Atualização:** Mensal
- **Granularidade:** Município × mês
- **Colunas:** `codigo_ibge, anomes_s, sigla_uf, municipio, paa_indicador_adesao_municipio_i` (indicador binário 0/1)
- **Cobertura geográfica:** Nacional — 5.570 municípios únicos (verificado)
- **Período histórico:** 2026-01 a 2026-06
- **Quantidade REAL de registros:** 19.032 linhas (verificado via pandas)
- **Licença:** CC-BY
- **Uso comercial permitido?** Sim
- **Atribuição necessária?** Sim (MDS)
- **Presença de dados pessoais?** Não
- **Utilidade para o projeto:** Alta — feature binária direta "município aderiu ao PAA", e cobre nomenclatura oficial de município/UF por código IBGE, útil para join com outras fontes.
- **Classificação:** **APPROVED**

---

## 4. PAA — Agricultores Familiares por Sexo

- **Nome:** Quantidade de agricultores familiares fornecedores do PAA, por sexo
- **Órgão:** MDS
- **URL (API real):** `https://aplicacoes.mds.gov.br/sagi/servicos/misocial/?fq=anomes_s:[201412 TO *]&q=*:*&rows=1000000&sort=anomes_s desc, codigo_ibge asc&wt=csv&fl=codigo_ibge,anomes_s,paa_qtd_agricul_familiar_sexo_masculino_i,paa_qtd_agricul_familiar_sexo_feminino_i,paa_qtd_agricul_familiar_sem_info_sexo_i&fq=paa_qtd_agricul_familiar_sexo_masculino_i:*`
- **Formato:** CSV (API SAGI/MDS)
- **Acesso:** API pública
- **Atualização:** Mensal
- **Granularidade:** Município × mês
- **Colunas:** `codigo_ibge, anomes_s, paa_qtd_agricul_familiar_sexo_masculino_i, paa_qtd_agricul_familiar_sexo_feminino_i, paa_qtd_agricul_familiar_sem_info_sexo_i`
- **Cobertura geográfica:** Nacional
- **Período histórico:** 2014-12 a 2026-06 (maior profundidade histórica entre as fontes PAA)
- **Quantidade REAL de registros:** 29.350 linhas (verificado)
- **Licença:** CC-BY
- **Uso comercial permitido?** Sim
- **Atribuição necessária?** Sim (MDS)
- **Presença de dados pessoais?** Não (dado agregado, sem identificação individual)
- **Utilidade para o projeto:** Baixa/Média para o problema de priorização geográfica (mais relevante para análises de equidade de gênero na agricultura familiar do que para priorização de distribuição).
- **Classificação:** **APPROVED**

---

## 5. IBGE — Municípios do Brasil (metadados territoriais)

- **Nome:** Lista oficial de municípios, com hierarquia territorial (UF, mesorregião, microrregião, região)
- **Órgão:** Instituto Brasileiro de Geografia e Estatística (IBGE)
- **URL:** `https://servicodados.ibge.gov.br/api/v1/localidades/municipios`
- **Formato:** JSON
- **Acesso:** API pública (sem autenticação)
- **Atualização:** Conforme atualizações territoriais do IBGE (baixa frequência de mudança)
- **Granularidade:** Município
- **Colunas/campos:** `id (código IBGE 7 dígitos), nome, microrregiao, mesorregiao, UF (id, sigla, nome), regiao, regiao-imediata, regiao-intermediaria`
- **Cobertura geográfica:** Nacional — 5.571 municípios (verificado, número oficial correto)
- **Período histórico:** N/A (dado corrente, não é série temporal)
- **Quantidade REAL de registros:** 5.571 (verificado via pandas/json)
- **Licença:** Dados abertos do IBGE — uso livre com atribuição recomendada (Lei de Acesso à Informação / política de dados abertos do IBGE; IBGE não impõe licença restritiva sobre dados estatísticos oficiais)
- **Uso comercial permitido?** Sim
- **Atribuição necessária?** Recomendada (IBGE)
- **Presença de dados pessoais?** Não
- **Utilidade para o projeto:** Alta — fonte de verdade para código IBGE, nome de município e UF, essencial para join entre todas as demais fontes.
- **Classificação:** **APPROVED**

---

## 6. IBGE — População Residente Estimada por Município (2026)

- **Nome:** População residente estimada — Tabela SIDRA 6579, variável 9324
- **Órgão:** IBGE
- **URL:** `https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/variaveis/9324?localidades=N6[all]`
- **Formato:** JSON
- **Acesso:** API pública (SIDRA)
- **Atualização:** Anual
- **Granularidade:** Município
- **Colunas/campos:** `localidade.id (código IBGE), localidade.nome, serie.2026 (população estimada)`
- **Cobertura geográfica:** Nacional — 5.571 municípios (verificado)
- **Período histórico:** Ano corrente da estimativa (2026); a API permite consultar períodos anteriores trocando o parâmetro `periodos`
- **Quantidade REAL de registros:** 5.571 (verificado); soma da população nacional = 214.211.951 (verificado, valor plausível para o Brasil)
- **Licença:** Dados abertos do IBGE, uso livre
- **Uso comercial permitido?** Sim
- **Atribuição necessária?** Recomendada (IBGE)
- **Presença de dados pessoais?** Não (dado agregado populacional)
- **Utilidade para o projeto:** Alta — feature "população" direta, necessária para normalizar (per capita) outras métricas e para dimensionar prioridade operacional.
- **Classificação:** **APPROVED**

---

## 7. IPEA / Mapa das OSCs — Área e Subárea de Atuação

- **Nome:** Organizações da Sociedade Civil (OSC) — área e subárea de atuação
- **Órgão:** IPEA (dado publicado via Portal Brasileiro de Dados Abertos)
- **URL de descoberta:** `https://dados.gov.br/dados/conjuntos-dados/mapaosc`
- **Formato:** CSV (delimitador `;`)
- **Acesso:** Download direto via portal (recurso "Áreas de atuação")
- **Atualização:** Não explicitamente declarada no portal (dataset consolidado, atualização não verificável)
- **Granularidade:** Organização (1 linha por OSC)
- **Colunas disponíveis (68 no total, amostra):** `id_osc, cd_identificador_osc (CNPJ), tx_razao_social_osc, tx_nome_fantasia_osc, dt_fundacao_osc, tx_nome_classe_atividade_economica, cd_natureza_juridica_osc, edmu_cd_municipio, edmu_nm_municipio, eduf_cd_uf, eduf_sg_uf` + colunas binárias de área/subárea de atuação (Habitação, Saúde, Cultura e recreação, Educação e pesquisa, Assistência social, Religião, Meio ambiente e proteção animal, Desenvolvimento e defesa de direitos, entre outras)
- **Cobertura geográfica:** Nacional — 4.644 municípios distintos identificados em amostra de 50.000 registros
- **Período histórico:** Data de fundação de cada OSC desde décadas anteriores; dataset é um cadastro corrente, não série temporal
- **Quantidade REAL de registros:** 960.315 linhas de dados (960.316 incluindo cabeçalho) — verificado via `wc -l` e pandas; arquivo de 266.910.744 bytes (~267 MB)
- **Licença:** "Other (Attribution)" — licença não-padrão declarada no portal dados.gov.br. Não é uma licença Creative Commons reconhecida; interpretação: uso permitido mediante atribuição à fonte (IPEA/Mapa das OSCs), mas sem termos jurídicos padronizados publicamente disponíveis.
- **Uso comercial permitido?** NÃO CONFIRMADO — a licença "Other (Attribution)" não especifica explicitamente uso comercial. Recomenda-se tratamento conservador.
- **Atribuição necessária?** Sim — atribuir a IPEA / Mapa das Organizações da Sociedade Civil
- **Presença de dados pessoais?** O dataset contém CNPJ (pessoa jurídica, não pessoa física — fora do escopo de dados pessoais da LGPD, que protege "pessoa natural"). Razão social e nome fantasia são também de pessoa jurídica. Não foram identificados CPFs ou dados de pessoas físicas nas colunas inspecionadas.
- **Utilidade para o projeto:** Alta — permite contar organizações por município e por área de atuação (ex: "Assistência social"), feature real para "organizações na região".
- **Classificação:** **NEEDS_REVIEW** (uso liberado para fins de pesquisa/acadêmicos nesta fase; uso comercial em produção requer confirmação formal dos termos de licença junto ao IPEA antes de prosseguir para a Fase 1 com fins comerciais)

---

## 8. IPEA / Mapa das OSCs — Dicionário de Dados

- **Nome:** Dicionário de dados das bases do Mapa das OSCs
- **Órgão:** IPEA
- **URL de descoberta:** `https://dados.gov.br/dados/conjuntos-dados/mapaosc` (recurso "Dicionário de dados", formato XLSX)
- **Formato:** XLSX
- **Acesso:** Download direto
- **Atualização:** Não verificável
- **Granularidade:** Metadado (1 linha por variável/coluna)
- **Colunas:** `Variável, Descrição, Fonte`
- **Cobertura geográfica:** N/A (metadado)
- **Período histórico:** N/A
- **Quantidade REAL de registros:** 95 linhas (94 variáveis documentadas + cabeçalho), verificado via openpyxl
- **Licença:** Mesma do dataset principal — "Other (Attribution)"
- **Uso comercial permitido?** Mesma ressalva do item 7
- **Atribuição necessária?** Sim (IPEA)
- **Presença de dados pessoais?** Não (é um dicionário de metadados)
- **Utilidade para o projeto:** Alta — essencial para interpretar corretamente as colunas do dataset de área/subárea (item 7).
- **Classificação:** **APPROVED** (uso como metadado/documentação, sem restrição adicional)

---

## 9. RBBA — Rede Brasileira de Bancos de Alimentos (API "resumo")

- **Nome:** Painel "RBBA em números" — bancos de alimentos aderidos, georreferenciados, e indicadores nacionais agregados
- **Órgão:** MDS (Coordenação-Geral de Equipamentos de Segurança Alimentar e Nutricional — CGESAN), publicado via plataforma "Alimenta Cidades Digital"
- **URL oficial de referência:** `https://www.gov.br/mds/pt-br/acoes-e-programas/acesso-a-alimentos-e-a-agua/rede-brasileira-de-bancos-de-alimentos`
- **URL da API real utilizada:** `https://alimentacidades.digital/rbba/api/resumo`
- **Formato:** JSON (GeoJSON para os pontos georreferenciados)
- **Acesso:** API pública, descoberta via inspeção de requisições de rede do painel público (sem autenticação necessária)
- **Atualização:** Dados de 2025 (ano mais recente com relatório consolidado) e 2024; painel indica "anos: [2025, 2024]"
- **Granularidade:** Banco de alimentos individual (georreferenciado) + agregados nacionais
- **Colunas/campos:** `kpis` (bancos, aderidos, municípios, ufs, kg_recebidos, kg_doados, kg_perdidos, pessoas_atendidas, instituicoes, etc.); `pontos.features[].properties` (identificador, nome, cidade, uf, modalidade) + geometria (lat/long)
- **Cobertura geográfica:** Nacional — 27 UFs, 192 bancos georreferenciados de um total de 362 bancos cadastrados (208 com adesão vigente à RBBA)
- **Período histórico:** Dados anuais 2024–2025 (sem série histórica mais longa disponível nesta API)
- **Quantidade REAL de registros:** 192 bancos georreferenciados (feature collection); KPIs nacionais agregados (não são registros individuais, são somatórios): 5.167.799 pessoas atendidas em 2025, 66.285.063,38 kg recebidos, 62.483.403,16 kg doados — verificado via inspeção do JSON real
- **Licença:** NÃO DECLARADA EXPLICITAMENTE na página ou na API. É um painel público de um órgão federal (MDS), mas sem termos de uso/licença publicados no momento da coleta.
- **Uso comercial permitido?** NÃO CONFIRMADO — requer contato com CGESAN/MDS (e-mail institucional: cgesan@mds.gov.br, conforme página oficial) para confirmação formal antes de uso comercial/produção.
- **Atribuição necessária?** Recomendada (MDS / RBBA)
- **Presença de dados pessoais?** Não. Dados são de instituições (bancos de alimentos), com nome da instituição, cidade, UF, modalidade de gestão — não há identificação de pessoas físicas.
- **Utilidade para o projeto:** Alta — única fonte real encontrada que indica presença/localização geográfica de bancos de alimentos por município, feature diretamente solicitada ("presença de banco de alimentos").
- **Classificação:** **NEEDS_REVIEW** (dado real e tecnicamente utilizável na Fase 0/pesquisa; uso em produção comercial NÃO deve ocorrer até confirmação formal de licença junto ao MDS/CGESAN)

---

## 10. CONAB — Investigação de fontes próprias (resultado: não encontrado)

- **Nome:** N/A — busca por conjunto de dados próprio da CONAB
- **Órgão investigado:** Companhia Nacional de Abastecimento (CONAB)
- **URLs investigadas:**
  - `https://dados.gov.br/dados/conjuntos-dados?q=CONAB` → **"Nenhum registro encontrado!"** (busca real realizada, sem resultados sob esse termo/organização)
  - `https://www.conab.gov.br/dados-abertos-m` → redireciona para a home institucional (página não encontrada)
  - `https://portaldeinformacoes.conab.gov.br/paa-entregas.html` e `/home` → portal de painéis (Power BI-like) carregou, mas retornou **"Erro ao carregar downloads"** e **"Nenhum painel encontrado"** — portal aparentemente sem dados públicos acessíveis no momento da coleta, ou exige navegação/filtros adicionais não localizados
- **Formato:** N/A
- **Acesso:** Não disponível como dataset estruturado no momento da coleta
- **Conclusão real e verificada:** A CONAB é a executora operacional do PAA (compras da agricultura familiar), mas os dados de execução do programa são consolidados e publicados oficialmente pelo **MDS** (via API SAGI — ver itens 1 a 4), não pela CONAB diretamente em um portal de dados abertos próprio. O "Portal de Informações Agropecuárias" da CONAB existe mas, no momento da coleta, não expôs painéis/downloads funcionais para os temas de doação/PAA.
- **Utilidade para o projeto:** Nenhuma fonte estruturada própria da CONAB pôde ser confirmada e baixada nesta fase.
- **Classificação:** **REJECTED** (fonte não disponibilizou dados estruturados acessíveis; necessidade coberta pelas fontes MDS/PAA já aprovadas)

---

## 11. Links quebrados identificados (documentados, não utilizados)

- **"PAA - Execução Geral"** (CSV, catalogado 27/10/2021 em dados.gov.br) → aponta para link SharePoint da MDS (`mdsgov.sharepoint.com/...`) que retorna **"Sorry, the link has expired"**. **REJECTED** (link morto).
- **"2025 - Execução financeira da modalidade Compra com Doação Simultânea"** (XLSX) → mesmo problema, link SharePoint expirado. **REJECTED** (link morto). Dado equivalente já coberto pela API SAGI (item 1).

---

## 12. dados.gov.br — usado como índice de descoberta

O Portal Brasileiro de Dados Abertos (dados.gov.br) foi utilizado como ferramenta de busca/descoberta para localizar os datasets acima (PAA, Mapa das OSCs), não como fonte de dados em si. É uma aplicação Vue.js (SPA); buscas foram realizadas via interface real (não há API CKAN pública aberta neste domínio — tentativa de acesso a `/api/3/action/package_search` retornou HTTP 401).

---

## Resumo de classificação

| # | Fonte | Órgão | Classificação |
|---|-------|-------|----------------|
| 1 | PAA — Compra c/ Doação Simultânea | MDS | APPROVED |
| 2 | PAA — Incentivo ao Leite | MDS | APPROVED |
| 3 | PAA — Municípios Aderidos | MDS | APPROVED |
| 4 | PAA — Agricultores por Sexo | MDS | APPROVED |
| 5 | IBGE — Municípios | IBGE | APPROVED |
| 6 | IBGE — População 2026 | IBGE | APPROVED |
| 7 | IPEA — Mapa das OSCs (área/subárea) | IPEA | NEEDS_REVIEW (licença não-padrão) |
| 8 | IPEA — Dicionário de dados | IPEA | APPROVED |
| 9 | RBBA — API resumo | MDS/Alimenta Cidades | NEEDS_REVIEW (licença não declarada) |
| 10 | CONAB — fonte própria | CONAB | REJECTED (não encontrada) |
| 11 | Links SharePoint MDS (2x) | MDS | REJECTED (links mortos) |

**Nota de conformidade:** Conforme instrução do projeto, fontes classificadas como NEEDS_REVIEW (itens 7 e 9) não devem ser utilizadas em produção/comercialização até confirmação formal da licença junto ao órgão responsável (IPEA e MDS/CGESAN, respectivamente). Podem ser utilizadas nesta fase de pesquisa e prototipagem acadêmica.
