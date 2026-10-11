# Confirmações de licença PENDENTES (nenhuma foi resolvida na Fase 2 Parte 1)

Estado no banco: `public_data_sources.review_status` e `publication_cleared=false` (a plataforma **não** libera publicação de bases brutas).

| Fonte (id no banco) | Estado | O que falta confirmar | Ação |
|---|---|---|---|
| Mapa das OSCs / IPEA (`ipea_osc_area`) | NEEDS_REVIEW | Termos de uso comercial/redistribuição; "Other (Attribution)" não é licença padronizada | Leitura manual de `mapaosc.ipea.gov.br/termosuso` e e-mail formal ao IPEA; registrar resposta/data |
| RBBA / MDS (`rbba_resumo`) | NEEDS_REVIEW | Licença não declarada; endpoint não documentado | E-mail a `cgesan@mds.gov.br` (licença, uso comercial, endpoint oficial) |
| IBGE — municípios e população (`ibge_municipios`, `ibge_populacao`) | NEEDS_REVIEW | Termos explícitos de reutilização não localizados | Localizar e citar os termos oficiais do IBGE |
| Coordenadas de município (`ibge_coords`) | NEEDS_REVIEW (PROXY) | MIT é do repositório de terceiros; origem primária não confirmada | Substituir/validar pela malha oficial do IBGE |
| Receita Federal — CNPJ | NEEDS_REVIEW | Licença da base não verificada (CC BY-ND do rodapé cobre o site, não a base) | Obter licença do conjunto; usar só PJ/agregados |
| PAA/MDS (`paa_*`) | APPROVED (a reverificar) | CC-BY vem de metadado da Fase 0; reverificação no portal | Reverificar e atribuir MDS |

Efeitos práticos nesta fase: as 54 590 organizações são **registros de fonte pública para pesquisa/prototipagem acadêmica**; não são clientes da plataforma (`platform_status = PUBLIC_RECORD`) e **não podem receber doações reais** (regra `E_NAO_CADASTRADA`).

## Decisão da equipe — outubro/2026 (Fase 2 Parte 2)
Os e-mails de confirmação de licença **não foram respondidos e não há expectativa de resposta**. Nenhuma entrega fica bloqueada por isso e **não serão enviadas novas confirmações**.
* ONGs (IPEA/OSC, RBBA), municípios, população/indicadores e coordenadas permanecem em **USO ACADÊMICO e educacional**, com licença **NÃO CONFIRMADA (NEEDS_REVIEW)** e `publication_cleared=false` (verificado por `tests/test_p2b_uso_academico.py`). Nenhuma fonte foi marcada como aprovada por causa desta decisão.
* Consequências: `data/raw` e `data/simulated` fora do repositório e das imagens Docker; nenhuma exportação/download de bases brutas na API/interface; atribuição às fontes; aviso visível na interface: "dados públicos usados para fins acadêmicos; licença de reutilização não confirmada"; preferir indicadores agregados na exibição pública.
* Novas fontes reais (ex.: Conab, base CNPJ, malha oficial) **não** foram buscadas — trabalho futuro para escalar o projeto.
* Rotulagem manual **não será feita**: `MANUALLY_LABELED` não existe; o desempenho do parser e do modelo em textos/dados reais é **DESCONHECIDO**; toda métrica é sobre dados simulados.
