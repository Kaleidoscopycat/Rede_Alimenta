# DATA_SOURCE_CANDIDATES.md

**Projeto:** Rede Alimenta IA — **Fase 0 (revisada): Data Discovery, Simulação Fundamentada e Viabilidade**
**Enquadramento:** fluxo **DOADOR → ONG** (match, recomendação e coleta). Fora de escopo: ONG → beneficiário final.
**Revisão:** 2026-10-02 (substitui a versão de 2026-09-23, arquivada em `docs/data/archive/`, cujo enquadramento era "índice de gap de cobertura municipal"). **Correção de pendências (v3, 2026-10-02):** nova seção **G** (taxonomia, nomes de produto, cadeia fria e vida útil), nova seção **H** (geografia e roteamento: OSM/ODbL) e reclassificação da CONAB (C5) e da TACO (E5). A versão anterior está em `archive/DATA_SOURCE_CANDIDATES_v2_pre_correcao.md`.
**Metodologia:** "acessado" = arquivo baixado e inspecionado por código (`scripts/validate_phase0_data.py`); "NÃO ACESSADO" = fonte identificada mas não baixada/lida nesta sessão. Nada foi simulado, inventado ou gerado por IA. Checksums sha256 em `data/metadata/raw_checksums.json`.

> **Restrição de ambiente desta revisão:** a política de saída da sessão bloqueou `ibge.gov.br`, `servicodados.ibge.gov.br`, `geoftp.ibge.gov.br`, `dadosabertos.rfb.gov.br`, `dados.gov.br`, `gov.br/mds` e `aplicacoes.mds.gov.br` para download. Os arquivos RAW das fontes 1–9 são os baixados em 2026-09-23 (fase anterior); a revisão re-validou todos eles. Fontes novas que dependiam desses domínios ficaram **NÃO ACESSADAS** e estão registradas como pendência — não foram substituídas por dados inventados.

Classificação: `APPROVED` · `RESTRICTED` · `REJECTED` · `NEEDS_REVIEW`. **Dados NEEDS_REVIEW não entram em produção.**
Papel: `REAL_FEATURE` · `PARAMETRO_DE_SIMULACAO` · `REFERENCIA`.
Classe de variável (ver spec): `REAL` · `PROXY` · `SIMULADO` · `PREDITO`.

---

## A. Lado ONG / receptor

### A1. IPEA — Mapa das OSCs (área/subárea de atuação) — `ipea_osc_area`
- **Órgão:** IPEA. **URL de descoberta:** `https://dados.gov.br/dados/conjuntos-dados/mapaosc` (página exige JavaScript/retornou HTTP 401 a leitores automáticos nesta sessão). **Termos de uso publicados pelo IPEA:** `https://mapaosc.ipea.gov.br/termosuso` (existe; **leitura automática bloqueada por robots.txt** — leitura manual pendente).
- **Formato / acesso:** CSV (`;`), download direto. **Atualização:** não declarada de forma verificável.
- **Granularidade:** 1 linha por OSC. **Registros (leitura de 100% do arquivo):** **960.315** (id_osc e CNPJ únicos; 32 sem município).
- **Colunas (68):** identificação (id, CNPJ, razão social, fantasia, data de fundação, classe CNAE, natureza jurídica), município/UF (códigos IBGE), 11 flags de **área** e 44 flags de **subárea**.
- **Cobertura:** 5.570 dos 5.571 municípios têm ≥1 OSC. 54.398 OSCs com área "Assistência social" (4.421 municípios).
- **NÃO há:** coordenadas, endereço/CEP, capacidade de armazenamento, refrigeração, horário, tipos de alimento aceitos, nem subárea de segurança alimentar. As colunas de subárea são **inconsistentes com as de área** (ex.: `Ass Social sub Outros`=1 em 296.136 linhas contra 54.398 da área) → usar **somente flags de área**.
- **Licença:** metadado do portal: "Other (Attribution)" (não padronizada). **Uso comercial:** NÃO CONFIRMADO. **Atribuição:** sim (IPEA/Mapa das OSCs).
- **Dados pessoais:** CNPJ, razão social e nome fantasia (pessoa jurídica). Nenhuma coluna de CPF/sócio (verificado por teste). Algumas razões sociais podem conter nome de pessoa física (ex.: associações nomeadas); **não são usadas como feature nem exibidas sem necessidade**.
- **Papel:** `REAL_FEATURE` (universo de ONGs candidatas, município/UF, área). **Classe:** REAL (cadastro declarado); elegibilidade como "receptora de doação de alimentos" = **PROXY** (regra por área, não existe flag de segurança alimentar).
- **Classificação:** **NEEDS_REVIEW** (mantida). **Plano de confirmação:** (1) ler manualmente os Termos de uso em `mapaosc.ipea.gov.br/termosuso`; (2) e-mail formal ao IPEA (canal indicado no site do Mapa das OSC) perguntando uso comercial, redistribuição de derivados e uso de CNPJ/razão social em produto; (3) registrar resposta e data em `DATA_LICENSES.md`. Até lá: uso restrito a pesquisa/prototipagem acadêmica, sem publicar a base bruta.

### A2. IPEA — Dicionário de dados do Mapa das OSCs — `ipea_osc_dict`
- XLSX/TXT, 94 variáveis documentadas. Mesma licença de A1 (metadado de documentação). **Papel:** REFERENCIA. **Classificação:** **APPROVED** (apenas como documentação).

### A3. MDS — Rede Brasileira de Bancos de Alimentos (RBBA) — `rbba_resumo`
- **Órgão:** MDS/CGESAN; painel "RBBA em números" na plataforma Alimenta Cidades Digital. **Página oficial:** `https://www.gov.br/mds/pt-br/acoes-e-programas/acesso-a-alimentos-e-a-agua/rede-brasileira-de-bancos-de-alimentos` (lida: rede restabelecida pelo Decreto nº 12.512/2025; 208 bancos aderidos; membros = bancos públicos, rede Sesc Mesa Brasil, OSCs e operações em Ceasas; contato `cgesan@mds.gov.br`).
- **Endpoint usado (fase anterior):** `https://alimentacidades.digital/rbba/api/resumo` (JSON público, sem autenticação; descoberto pelo painel).
- **Conteúdo (acessado):** 192 bancos georreferenciados (lat/lon, nome, cidade, UF, modalidade) em 161 municípios; KPIs nacionais 2025: 362 bancos, 208 aderidos, 161 relatórios, **66.285.063,38 kg recebidos, 62.483.403,16 kg doados, 3.215.754,25 kg perdidos (4,85%)**; gráficos: modalidade, perfil operacional, **origem dos alimentos** (54,8% "Perdas e Desperdícios"), **classificação NOVA** (88,2% in natura/minimamente processados, 1,3% ingredientes, 4,5% processados, 6,0% ultraprocessados), **série mensal de kg recebidos/doados**, momento da perda, tipos de instituição atendida.
- **Qualidade (achado desta revisão):** 2 pontos com coordenada incoerente no RAW — `BA000038` (Imperatriz/MA, lat −54,91; ~5.492 km do município) e `BA000307` (Três Corações/MG, lat +21,72; sinal invertido; ~4.827 km). **Não corrigidos no RAW.** Regra: na camada BRONZE marcar `geo_quality = "SUSPEITA"` e usar o centroide do município. Nos demais 190, mediana de 1,7 km e p90 de 6,2 km em relação ao centroide do município.
- **Limites:** só 192 de 362 bancos têm ponto; só agregados nacionais (sem kg por banco, exceto top-10); apenas 2024–2025; **KPIs de "pessoas atendidas" e "instituições" são contexto agregado** — não usados como target/feature (fora de escopo).
- **Licença:** NÃO DECLARADA. **Uso comercial:** NÃO CONFIRMADO. **Atribuição:** recomendada (MDS/RBBA). **Dados pessoais:** não (instituições). **Aviso:** o endpoint foi descoberto por inspeção do painel — **não é API documentada**; pode mudar sem aviso.
- **Papel:** `REAL_FEATURE` (localização/modalidade dos bancos — a ponta receptora real) e `PARAMETRO_DE_SIMULACAO` (kg/ano por relatório, sazonalidade mensal, origem, classe NOVA, taxa de perda).
- **Classificação:** **NEEDS_REVIEW** (mantida). **Plano:** e-mail a `cgesan@mds.gov.br` pedindo (a) termos de uso/licença do painel e do endpoint, (b) autorização de uso comercial futuro, (c) endpoint/conjunto oficial documentado e base completa dos 362 bancos com coordenadas. Registrar protocolo e resposta.

### A4. Equipamentos de segurança alimentar (cozinhas comunitárias, restaurantes populares) — **NÃO ENCONTRADO**
- Busca por base georreferenciada aberta retornou apenas publicações em PDF do MDS e conjuntos municipais isolados (ex.: portal de dados de Belo Horizonte). Nenhum conjunto nacional estruturado foi localizado/baixado. **Classificação:** **REJECTED** (não localizado nesta revisão; **pendência** de nova busca com acesso a `dados.gov.br`/`aplicacoes.mds.gov.br`).

---

## B. Território

### B1. IBGE — Municípios (`ibge_municipios`) — **APPROVED***
- API `https://servicodados.ibge.gov.br/api/v1/localidades/municipios`; JSON; 5.571 municípios (códigos únicos). Sem coordenadas. Papel: chave territorial (`REAL`).
- **Licença:** o IBGE publica como dado aberto (Decreto nº 8.777/2016 — política de dados abertos), mas **não foi possível confirmar a licença explícita** (o Plano de Dados Abertos 2024–2025 consultado não a especifica; a página de política de dados abertos retornou 404). *Rebaixamento de rigor em relação à versão anterior ("uso livre")*: manter **APPROVED para pesquisa**, com **pendência** de citar a licença/termos oficiais do IBGE antes de produção comercial.

### B2. IBGE — População residente estimada 2026 (SIDRA 6579/9324) (`ibge_populacao`) — **APPROVED***
- 5.571 municípios; soma 214.211.951 (teste passa). Papel: `REAL_FEATURE`. Mesma ressalva de licença de B1.

### B3. Coordenadas de município — `ibge_coords` (kelvins/municipios-brasileiros) — **NEEDS_REVIEW**
- **Fonte:** `https://github.com/kelvins/municipios-brasileiros` (arquivo `csv/municipios.csv`, commit mais recente observado 2025-12-10). **Licença do repositório: MIT** (confirmada no arquivo `LICENSE`). **A origem primária das coordenadas NÃO é declarada** no README — é compilação de terceiros (provavelmente derivada de dados do IBGE, **não confirmado**).
- **Conteúdo:** 5.571 linhas, código IBGE (7 dígitos), nome, lat, lon, capital, UF, SIAFI, DDD, fuso. **Casa 100% com os 5.571 códigos IBGE** (teste). Todas as coordenadas dentro do Brasil.
- **Validação independente:** contra os 192 pontos reais da RBBA (coordenadas de outra origem) — mediana **1,7 km**, p90 **6,2 km** (exceto as 2 anomalias do RBBA). Isso sustenta o uso como **centroide/sede aproximada**.
- **Limitação registrada:** é **PROXY** de localização (ponto único por município; sem polígono; não sabemos se é sede ou centroide geométrico). Distância ONG–doador no mesmo município = 0 por construção → incluir `mesmo_municipio` e declarar a incerteza intramunicipal.
- **Fonte oficial a obter (substituição):** Malha Municipal Digital do IBGE (página `https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html`; edição 2025 citada na página de áreas territoriais; também API de malhas `servicodados.ibge.gov.br/api/v3/malhas` e o conjunto "Malha geométrica dos municípios brasileiros" em dados.gov.br) — **NÃO ACESSADA** (bloqueio de rede). A licença do IBGE para a malha também precisa ser confirmada (B1). Plano: baixar a malha, calcular centroides com `shapely`/`geopandas` (ambos ausentes no ambiente local; instalar via PyPI, que é acessível) e comparar com B3.
- **Papel:** `REAL_FEATURE`/cálculo de distância. **Classe:** PROXY.

---

## C. Referências de alimentos / oferta

### C1–C4. PAA — MDS/SAGI (`paa_compra_doacao`, `paa_leite`, `paa_municipios`, `paa_sexo`) — **APPROVED**
- API SAGI/MDS (CC-BY, conforme metadado em dados.gov.br na fase anterior; **não reverificável nesta sessão** — bloqueio). Município × mês. Registros: 49.627 / 8.367 / 19.032 / 29.350.
- **O que realmente trazem (corrige expectativa do prompt):** totais por município-mês (kg, R$, nº de agricultores). **Não há produto nem categoria.** Portanto o PAA serve como **referência de volume e sazonalidade**, não de categorias.
- **Sazonalidade calculada (kg/mês ÷ média, 2021–2025):** jan 0,53 · fev 0,54 · mar 0,69 · abr 0,94 · mai 1,26 · jun 1,15 · jul 1,24 · ago 1,30 · set 1,07 · out 1,21 · nov 1,28 · dez 0,79. **Ressalva:** o nº de registros por ano varia muito (4.752 em 2022 a 13.270 em 2021), então o índice mistura mudança de cobertura com sazonalidade → incerteza alta.
- A modalidade "compra com doação simultânea" tem execução em apenas **3.781 municípios** distintos.
- **Papel:** `PARAMETRO_DE_SIMULACAO` (sazonalidade da oferta agrícola) e `REAL_FEATURE` (adesão do município — contexto territorial). `paa_sexo`: **REFERENCIA** sem uso (irrelevante ao problema). **Atribuição:** MDS. **Dados pessoais:** não.

### C5. CONAB — dataset estruturado **REJECTED**; publicações **APPROVED como referência** (reclassificado na correção v3)
- **Dataset estruturado próprio:** nenhum localizado/baixado (dados.gov.br sem registro; portal de informações sem downloads funcionais na fase anterior). Execução do PAA vem do MDS (C1–C4). **REJECTED** como fonte de dados.
- **Publicação localizada (lida via resumo, não baixada):** Conab, *Compêndio de Estudos Conab — Agricultura Familiar, PAA 2021* (`gov.br/conab/.../compendio-v30-paa-2021.pdf`; ISSN 2448-3710). Traz, para **2020**, participação por grupo de produto nas compras do PAA: **Hortifrúti 69% · Carnes 8% · Grãos e oleaginosas 7% · Processados 16%** (Gráfico 3, p. 13), e produtos por região em toneladas (ex.: mandioca no NE, banana no SE/S, melancia no N). **Termo de reprodução:** "Qualquer parte desta publicação pode ser reproduzida, desde que citada a fonte."
- **Fonte secundária (não usada como parâmetro):** notícia Agrolink citando o compêndio Conab de 2018 (hortifrúti ≈ 63% das compras do PAA em 2018).
- **Atenção:** são compras de **agricultura familiar** (oferta agrícola), **não doações de doadores urbanos**; servem de **referência de composição agrícola e de nomes de produto**, nunca como "doações da Rede Alimenta".
- **Papel:** `REFERENCIA` / `PARAMETRO_DE_SIMULACAO` (cenário de mix com peso alto de hortifrúti; nomes de produtos). **Classe:** REAL (referência). **Classificação:** **APPROVED** (referência com citação). Tabela por produto/ano **não obtida** (PDF não baixado) → pendência: baixar o compêndio quando houver acesso.

---

## D. Universo de doadores

### D1. Receita Federal — Dados Públicos do CNPJ (estabelecimentos, por CNAE) — **NEEDS_REVIEW (NÃO ACESSADO)**
- **URL de referência:** `https://dadosabertos.rfb.gov.br/CNPJ/` (diretório de arquivos mensais) — **bloqueado nesta sessão; nenhum byte foi baixado.**
- **Licença:** **NÃO verificada.** O único texto de licença lido foi o rodapé geral do site da Receita ("Creative Commons Atribuição-SemDerivações 3.0 Não Adaptada"), que se refere ao *conteúdo do site*, **não** ao conjunto de dados — não pode ser assumido para o CNPJ. **Uso comercial: NÃO CONFIRMADO.**
- **Uso previsto (se aprovado):** apenas arquivos de **Estabelecimentos** (município, CNAE principal, situação cadastral, data de início, porte via arquivo de Empresas), **somente PJ**, agregando **contagem por município × grupo CNAE × porte** para dar distribuição geográfica e peso relativo dos tipos de doador. **Excluir integralmente o arquivo de Sócios** e qualquer campo que identifique pessoa física (inclusive MEI/empresário individual cujo nome da firma seja o nome da pessoa — ao agregar, não carregar razão social/nome fantasia/CNPJ para o dataset; manter só contagens). Os CNPJs individuais **não** entram em nenhum dataset do projeto (doadores simulados usam id interno, conforme AGENTS.md §2).
- **CNAEs-alvo propostos (a validar na tabela CNAE 2.0 do IBGE):** comércio varejista de mercadorias em geral com predominância de alimentos (supermercados/hipermercados), restaurantes e similares, padarias, comércio atacadista de alimentos, indústria de produtos alimentícios, hortifrúti (varejo e atacado), Ceasas/centrais de abastecimento.
- **Papel:** `PARAMETRO_DE_SIMULACAO` (distribuição geográfica/porte de doadores). **Classe:** PROXY (estabelecimento existente ≠ doador efetivo; a propensão a doar é SIMULADA).
- **Até obter:** a distribuição geográfica dos doadores simulados usa **população IBGE (REAL) como proxy provisório**, declarado como tal no spec. **Pendência real:** baixar manualmente (usuário) ou liberar o domínio, e confirmar a licença (e-mail à Receita/consulta ao catálogo dados.gov.br).

---

## E. Desperdício, perecibilidade e critérios de doação (referências publicadas)

> São publicações, não conjuntos de dados reutilizáveis: servem de **referência/parâmetro com citação**. A licença de reprodução de cada publicação não foi analisada — citar números com fonte e **não copiar tabelas/textos**.

| ID | Referência | O que foi lido (literal/aproximado) | Papel | Classe | Classificação |
|---|---|---|---|---|---|
| E1 | MAPA/CDSA, *Relatório final — Enfrentamento a perdas e desperdício de alimentos* (27/09/2022). `gov.br/agricultura/.../relatorio-final-perdas-e-desperdicio` | Varejo supermercadista: **1,8% do faturamento bruto** perdido (R$ 7,6 bi/ano); **81%** do desperdício é perecível; FLV ≈ R$ 1,3 bi/ano; feiras livres de SP descartam 18.400 t/ano | PARAMETRO_DE_SIMULACAO (taxa de excedente do varejo, peso de perecíveis) | REAL (referência) | **APPROVED** (como referência, com citação) |
| E2 | Vilela, Lana, Nascimento, Makishima — *Perdas na comercialização de hortaliças em uma rede varejista do DF* (Embrapa, 2003; observações em 4 supermercados de uma rede, 1999) | Perda média **21%**; tomate **30%**, pimentão **20%**, cenoura **12%** | PARAMETRO_DE_SIMULACAO (excedente de hortifrúti) — **dado antigo e de uma única rede → incerteza alta** | REAL (referência) | **APPROVED** (com ressalva de representatividade) |
| E3 | Sesc Mesa Brasil (SP), "Tire suas dúvidas" (`sescmesabrasil.sescsp.org.br`) | Aceita **não perecíveis** em unidades; coleta direta em empresas do setor de alimentos; aceita produtos que "perderam valor comercial, mas continuam adequados para consumo"; ~1.150 instituições cadastradas em SP. **Não especifica validade mínima nem refrigeração** | REFERENCIA qualitativa (existência de critérios e de coleta ativa) | REAL (referência) | **APPROVED** (qualitativa) |
| E4 | Embrapa × ABRAS, notícia de 12/08/2019 (perdas no varejo de frutas e hortaliças) | Apenas metadados lidos; corpo do texto não obtido | — | — | **NEEDS_REVIEW** (nada extraído) |
| E5 | TACO — Tabela Brasileira de Composição de Alimentos, 4ª ed. (NEPA/UNICAMP) — página `nepa.unicamp.br/categoria/taco/` | Lida a página: edição vigente 4ª (ampliada e revisada), download em Excel e PDF; **a página não traz licença, termos de reprodução nem citação recomendada**; contatos `nepa@unicamp.br` e (19) 3521-4022. Tabela **não baixada**. Composição nutricional ≠ vida útil. Cópias em GitHub são de terceiros (não usar) | REFERENCIA de nomes de alimentos (**somente após licença**) | — | **NEEDS_REVIEW** (não entra em produção; plano: e-mail ao NEPA pedindo termos de uso e permissão de uso comercial) |
| E6 | FAO/ONU, Embrapa (vida útil por produto) | **Nenhuma tabela de vida útil restante-na-doação por categoria obtida** (ver G: o que foi achado são limites operacionais de cadeia fria, não vida útil de embalagem; a Anvisa afirma que o prazo de validade é do fabricante). | (lacuna) | — | **NÃO LOCALIZADO** — vida útil por categoria permanece **PREMISSA** com intervalo de incerteza (spec §3), agora com âncoras parciais (seção G) |
| E7 | Open Food Facts | Não analisado; licença ODbL (obrigações de compartilhamento) exige análise jurídica antes de qualquer integração | — | — | **REJECTED** (por ora, por regra do AGENTS.md) |

---

## F. dados.gov.br
- Portal é SPA em JavaScript; `/dataset/mapaosc` retornou **HTTP 401** a leitor automático; sem API CKAN pública (confirmado na fase anterior). Usado só como índice de descoberta (Mapa das OSCs, PAA, malha municipal). Não é fonte de dados.
- Links mortos da fase anterior (2 recursos SharePoint do MDS) permanecem **REJECTED**.

---

## Resumo de classificação

| # | Fonte | Papel | Classe | Classificação |
|---|---|---|---|---|
| A1 | IPEA Mapa das OSCs (960.315) | REAL_FEATURE | REAL / elegibilidade PROXY | **NEEDS_REVIEW** |
| A2 | IPEA dicionário | REFERENCIA | — | APPROVED |
| A3 | RBBA (192 pontos + KPIs) | REAL_FEATURE + PARAMETRO | REAL | **NEEDS_REVIEW** |
| A4 | Equipamentos SAN | — | — | REJECTED (não localizado) |
| B1 | IBGE municípios (5.571) | REAL_FEATURE | REAL | APPROVED* |
| B2 | IBGE população 2026 | REAL_FEATURE | REAL | APPROVED* |
| B3 | Coordenadas (kelvins, MIT) | REAL_FEATURE | PROXY | **NEEDS_REVIEW** |
| C1 | PAA compra c/ doação simultânea | PARAMETRO | REAL (ref.) | APPROVED |
| C2 | PAA leite | REFERENCIA | REAL | APPROVED |
| C3 | PAA adesão municipal | REAL_FEATURE | REAL | APPROVED |
| C4 | PAA agricultores por sexo | REFERENCIA | — | APPROVED (sem uso) |
| C5 | CONAB (dataset) / compêndio PAA 2021 (publicação) | REFERENCIA | REAL (ref.) | REJECTED (dataset) · **APPROVED** (publicação, referência) |
| D1 | CNPJ/Receita (estabelecimentos) | PARAMETRO | PROXY | **NEEDS_REVIEW (não acessado)** |
| E1 | MAPA perdas e desperdício | PARAMETRO | REAL (ref.) | APPROVED |
| E2 | Embrapa hortaliças (2003) | PARAMETRO | REAL (ref.) | APPROVED c/ ressalva |
| E3 | Mesa Brasil Sesc | REFERENCIA | REAL (ref.) | APPROVED |
| E4 | Embrapa/ABRAS 2019 | — | — | NEEDS_REVIEW |
| E5 | TACO 4ª ed. | REFERENCIA (nomes) | — | NEEDS_REVIEW (licença não declarada na página) |
| E6 | Vida útil por categoria (tabela) | — | — | NÃO LOCALIZADO (premissa) |
| G1 | Anvisa — Guia para Doação de Alimentos com Segurança Sanitária (2022) | PARAMETRO/REFERENCIA | REAL (ref.) | **RESTRICTED** |
| G2 | MDS — Guia de avaliação de alimentos doados aos Bancos de Alimentos (2018) | REFERENCIA (taxonomia) | REAL (ref.) | **RESTRICTED** |
| G3 | Anvisa — Guia nº 26/2019 Bancos de Alimentos | REFERENCIA (3 classes de perecibilidade) | REAL (ref.) | NEEDS_REVIEW |
| G4 | Anvisa — Guia nº 16/2018 v2 (prazos de validade) | REFERENCIA (conceito) | REAL (ref.) | **RESTRICTED** |
| G5 | MDS — Catálogo de Produtos da Agricultura Familiar (2018) | REFERENCIA (nomes de produto) | REAL (nomes) | **APPROVED** (c/ citação; lista completa não obtida) |
| G6 | SEDUC-GO — Critérios de validade dos alimentos (alimentação escolar) | REFERENCIA qualitativa | — | NEEDS_REVIEW |
| G7 | MDS — Minuta/Documento RBBA (2015) | REFERENCIA | — | APPROVED (sem critérios por categoria) |
| G8 | Guia Alimentar (MS) / classificação NOVA | REFERENCIA | — | NEEDS_REVIEW (não lido) |
| H1 | OpenStreetMap (dados, ODbL) | — | — | **NEEDS_REVIEW** (não integrado; análise em H) |
| H2 | Nominatim público / OSRM demo | — | — | **REJECTED** para uso no produto (política de uso) |
| E7 | Open Food Facts | — | — | REJECTED |

\* APPROVED para pesquisa; licença explícita do IBGE a citar antes de produção comercial.

---

## G. Taxonomia de categorias, nomes de produto, cadeia fria e vida útil (pendência 3 da correção)

**Método:** busca em português (WebSearch) + leitura de cada documento por resumo (WebFetch); nenhum PDF foi baixado ao RAW nesta etapa. As leituras vieram de resumos automáticos — **números citados abaixo foram devolvidos literalmente pela leitura, mas devem ser reconferidos no PDF original antes de entrarem em parâmetro final**. Domínios bloqueados: nenhum bloqueio novo; `mapaosc.ipea.gov.br` e `repositorio.ipea.gov.br` seguem inacessíveis (robots.txt) — **não contornados**. As páginas de política do OpenStreetMap exigiram aprovação de acesso (permitidas na segunda tentativa).

**Conclusão geral:** (1) **não existe**, nas fontes encontradas, tabela pública de **vida útil restante por categoria no momento da doação** — a Anvisa afirma que "não estipula prazo de validade para os alimentos, uma vez que o fabricante é o responsável" (G4); (2) existem **limites operacionais de cadeia fria e de tempo** (G1, G6) e **taxonomias de aceitação** (G1–G3) que ancoram **parcialmente** categorias e perecibilidade; (3) a **lista de nomes de produto** da simulação **não vem do PAA** (o PAA/MDS não traz produto) **nem da TACO** (NEEDS_REVIEW): vem de **fontes públicas citadas por nome** (G5, C5, E3, G6) e de **premissa do projeto** para o restante, com a origem registrada por nome (`product_name_origin`).

### G1. Anvisa — *Guia para Doação de Alimentos com Segurança Sanitária* (2022) — **RESTRICTED**
- Cópia lida: `fcna.abras.com.br/downloads/arq/Guia_para_Doacao_de_Alimentos_ANVISA.pdf` (hospedada pela ABRAS; **o original oficial está no portal da Anvisa — a conferir**).
- **Conteúdo relevante (resumo da leitura):** hortaliças/frutas in natura — avaliação de integridade (sem podridão, mofo, danos); grãos/cereais/farináceos — ausência de mofo/insetos; **panificados — prazo máximo de 24 h após a fabricação**, rejeitar com mofo; cárneos/laticínios/ovos — sem alteração de cor/textura/mofo, ovos sem casca trincada; **refeições prontas refrigeradas — máximo 5 dias a 4 °C**; alimentos quentes — **máximo 6 h acima de 60 °C**; congelados a **−18 °C**; "Quadro 4": congelados **−12 °C ou menos**, refrigerados **4 a 10 °C** (**os dois valores de congelado divergem na própria leitura — não resolver em silêncio; registrar a divergência e verificar no PDF**).
- **Licença/reprodução (literal):** "A reprodução parcial ou total deste documento por qualquer meio é totalmente livre, desde que citada adequadamente a fonte. **A reprodução para qualquer finalidade comercial está proibida.**" → **RESTRICTED**: citar e parafrasear, **não reproduzir texto/quadros** no produto; parâmetros (ex.: 24 h, 5 dias, 4 °C) são usados como **âncora citada** em premissas, com revisão jurídica antes de uso comercial.
- **Papel:** `PARAMETRO_DE_SIMULACAO` (limites de tempo/temperatura) e `REFERENCIA` (categorias).

### G2. MDS — *Guia de avaliação de alimentos doados aos Bancos de Alimentos* (2018) — **RESTRICTED**
- `mds.gov.br/webarquivos/publicacao/seguranca_alimentar/livro 'Guia avaliação alimentos'-mod13.pdf`. Objetivo: critérios mínimos para aceitar doações (aceitabilidade sensorial/visual).
- **Grupos (resumo da leitura):** hortaliças (A) folhosas, talos e inflorescências; (B) raízes, bulbos, rizomas e tubérculos; (C) frutos; (D) frutas; além de pães de padaria, alimentos de origem animal e processados/ultraprocessados. Validade "obrigatoriamente dentro do prazo"; embalagem íntegra; temperatura de armazenamento/transporte "na mesma temperatura presente na sua origem".
- **Reprodução (literal):** "É permitida a reprodução parcial ou total desta obra, desde que citada a fonte e que **não seja para venda ou qualquer fim comercial**." → **RESTRICTED**.
- **Papel:** `REFERENCIA` — base da **taxonomia de hortifrúti** (A–D) da simulação.

### G3. Anvisa — *Guia nº 26/2019, versão 1 — Bancos de Alimentos* — **NEEDS_REVIEW**
- `pesquisa.anvisa.gov.br/upload/surveys/15455/files/GUIA BANCO ALIMENTOS.pdf` (arquivo hospedado em portal de pesquisa da Anvisa). Sem tabela de critérios por categoria; remete ao guia do MDS (G2). Menciona **3 classes**: (1) industrializados **não perecíveis** (arroz, feijão, massas, leite em pó); (2) **perecíveis de baixo risco** (hortaliças e frutas inteiras); (3) **perecíveis refrigerados/congelados** (leite fluido, carnes, verduras minimamente processadas). **Sem trecho de licença** na leitura → NEEDS_REVIEW.
- **Papel:** `REFERENCIA` — origem das **classes de perecibilidade** (§ spec 2.1).

### G4. Anvisa — *Guia nº 16/2018, versão 2 (03/07/2024) — determinação de prazos de validade* — **RESTRICTED**
- Lida em cópia de terceiro (`regoola.io`) — **conferir no portal da Anvisa**. **Só metodologia** (estudos de estabilidade); não traz prazos por alimento. Literal: "A Anvisa não estipula prazo de validade para os alimentos, uma vez que o fabricante é o responsável." Reprodução comercial proibida. → confirma que vida útil por categoria **não é dado de fonte**.

### G5. MDS — *Catálogo de Produtos da Agricultura Familiar* (2018) — **APPROVED** (nomes, com citação)
- Publicação do MDS/SESAN (empreendimentos do Portal de Compras da Agricultura Familiar; organizada por região/UF). **Reprodução (literal):** "Qualquer parte desta publicação pode ser reproduzida, desde que citada a fonte."
- **Nomes de produto obtidos literalmente na leitura (17):** abóbora; acelga; açúcar (demerara, cristal e mascavo); alho; amendoim; arroz (branco e integral); café; carne bovina; carne de ave; doces de frutas; feijão; frutas; leite fluido; mel de abelha; queijo; suco de fruta. **A lista completa do catálogo não foi obtida** (download bloqueado; só resumo).
- **Papel:** `REFERENCIA` (nomes). **Atenção:** é catálogo de **ofertantes da agricultura familiar**, não de doações.

### G6. SEDUC-GO — *Critérios de validade dos alimentos* (alimentação escolar; arquivo "2024") — **NEEDS_REVIEW**
- Gerência de Alimentação Escolar (GO). Tabela de prazos por condição (ambiente/refrigeração/congelamento) para **alimentos manipulados/abertos em cozinhas escolares**; data não especificada no documento; **sem licença/termos**. Exemplos literais: pão francês 24 h (ambiente); creme de leite 3 dias e salsicha (embalagem aberta) 3 dias (refrigeração); carne moída 24 h e salgados crus 24 h (≤ 4 °C); folhas desinfetadas 12 h (≤ 4 °C); pão congelado 7 dias (< −12 °C).
- **Contexto diferente** (pós-abertura/preparo em cozinha) → **não** é vida útil de embalagem nem de doação. Uso: **apenas qualitativo** (ordem de grandeza e coerência), nunca como parâmetro direto.

### G7. MDS — *Rede Brasileira de Bancos de Alimentos* (documento de 2015) — **APPROVED** (sem critérios)
- Documento finalizado (não minuta), 2015. **Sem critérios por categoria/validade/temperatura**. Só a definição: alimentos "fora dos padrões de comercialização, mas [que] mantêm inalteradas suas propriedades nutricionais, não apresentando nenhuma restrição de caráter sanitário" (literal).

### G8. Guia Alimentar para a População Brasileira (MS) / classificação NOVA — **NEEDS_REVIEW**
- Identificado em busca (`bvsms.saude.gov.br/bvs/publicacoes/guia_alimentar_populacao_brasileira_2ed.pdf`); a página de glossário do gov.br **não** trouxe a classificação na leitura. **Não lido.** A RBBA já usa NOVA (A3), o que basta para o mix agregado; usar o guia como referência de classificação só após leitura.

### Outras referências localizadas e **não lidas**
- *Lei Federal nº 14.016/2020* (doação de alimentos) — aparece no título de uma cartilha do CRN-2; **não lida** (pendência para a análise jurídica de produto).
- *Portaria CVS nº 5/2013* (SP): resultados de busca (blogs) indicam substituição pela "CVS 3/2026" — **informação de fonte secundária não verificada**; norma estadual; **não lida**.
- *Boas Práticas de Manipulação em Bancos de Alimentos* e *Guia Operacional e de Gestão para Bancos de Alimentos* (MDS); *Manual operacional de doações* (Portaria MDS nº 708/2021): **não lidos**; candidatos a conter critérios por categoria.

### Decisão (item 2 e 4 da pendência 3)
1. **Taxonomia de categorias:** declarada como **PREMISSA DO PROJETO v0.2**, **inspirada** em G1–G3 (grupos do MDS e classes da Anvisa) e na composição do PAA (C5) — **não é "dado de fonte"**.
2. **Lista de nomes de produto:** **premissa do projeto**; nomes com origem pública identificada recebem `product_name_origin` = `MDS_CATALOGO_2018` | `CONAB_COMPENDIO_2021` | `MESA_BRASIL_SESC` | `SEDUC_GO_2024` e os demais `PREMISSA_PROJETO`. Nada vem do PAA/MDS-SAGI (que não tem produto) nem da TACO (NEEDS_REVIEW).
3. **Vida útil por categoria:** **PREMISSA com intervalo de incerteza**, com **âncoras parciais citadas** (panificados ≤ 24 h; refeições prontas refrigeradas ≤ 5 dias a 4 °C; quente ≤ 6 h acima de 60 °C), todas de G1 (RESTRICTED).

---

## H. Geografia e roteamento: OpenStreetMap (ODbL) e serviços públicos gratuitos (pendência 4)

Leitura de: `openstreetmap.org/copyright`; política do Nominatim (`operations.osmfoundation.org/policies/nominatim/`); wiki do servidor demo do OSRM (GitHub); FAQ de licença da OSM Foundation (`osmfoundation.org/wiki/Licence/Licence_and_Legal_FAQ`). As políticas estão **em inglês** (não há versão oficial em português; a página da wiki em português é introdutória). **Não é parecer jurídico.**

- **ODbL (dados OSM):** permite copiar, distribuir e adaptar com **atribuição** (crédito ao OpenStreetMap e colaboradores, indicando a licença ODbL, com link para `openstreetmap.org/copyright`) e **share-alike** (base de dados derivada distribuída deve permanecer ODbL). Distinção da FAQ: *produced work* (mapa, imagem, tiles — pode ter outra licença; receptores podem pedir os dados subjacentes) × *derivative database* (adaptar/enriquecer/corrigir os dados — permanece ODbL ao distribuir). **A leitura não esclareceu** o enquadramento de rotas calculadas por um motor próprio sobre dados OSM → **dúvida jurídica registrada, em aberto**. Uso comercial é permitido pela FAQ ("você pode cobrar qualquer valor"), mas o conteúdo derivado segue aberto.
- **Nominatim público:** máximo **1 requisição/s**; **User-Agent/Referer identificando a aplicação**; **cache obrigatório**; atribuição visível; **proibido** autocompletar, consultas sistemáticas/em massa, raspagem e **revenda de resultados**; aplicações cujo foco é geocodificação devem operar **instância própria**.
- **OSRM demo público:** "uso restrito a casos **razoáveis e não comerciais**"; ≤ 1 requisição/s; **sem garantias** de disponibilidade/latência/atualização; perfis carro/pedestre/bicicleta.
- **Alternativa:** instância própria (OSRM/Nominatim) com extrato OSM do Brasil — exige infraestrutura e conformidade ODbL; não avaliada tecnicamente.

**Decisão registrada:**
1. **Fase 1 e Fase 2 Parte 1: distância em linha reta (haversine)**, com fator de desvio e velocidade média como **premissas configuráveis** (nunca apresentadas como distância viária real). **Nenhum dado ou serviço OSM é usado; nenhuma chamada a Nominatim/OSRM.**
2. **Rota por malha viária real (OSRM): extensão opcional** da Fase 2 Parte 2, **somente se aprovada**, apenas com **instância própria**, após **análise jurídica da ODbL** (atribuição visível; share-alike sobre qualquer base derivada) e confirmação do tratamento de rotas como *produced work*. **Não é obrigatória** e **não usar os servidores públicos** (demo OSRM é não comercial; Nominatim não admite uso intensivo).
3. **Geocodificação de endereços:** desnecessária no escopo atual (não há endereço de ONG nas fontes; localização por município/ponto RBBA).
