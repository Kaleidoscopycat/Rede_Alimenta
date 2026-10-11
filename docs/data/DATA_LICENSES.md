# DATA_LICENSES.md

**v3 (correção de pendências, 2026-10-02)** — anterior em `archive/DATA_LICENSES_v2_pre_correcao.md`.

> **Regra:** "dado público" **não** significa livre para uso comercial. Fonte NEEDS_REVIEW **não entra em produção**. Esta tabela registra o que foi **realmente verificado** e o que ainda é pendência.

| Fonte | Licença/termo verificado | Verificado como | Uso comercial | Atribuição | Ação antes de produção |
|---|---|---|---|---|---|
| PAA (MDS, 4 conjuntos) | Creative Commons Attribution (CC-BY) | metadado do dados.gov.br (fase anterior; **reverificação bloqueada** nesta sessão) | Permitido | Sim — MDS | Reverificar no portal |
| IBGE (municípios, população) | Dado aberto (política de dados abertos, Decreto 8.777/2016); **licença explícita NÃO localizada** (Plano de Dados Abertos 2024–2025 não a especifica; página de política retornou 404) | leitura de documento | **Não confirmado explicitamente** | Recomendada — IBGE | Localizar e citar os termos oficiais de reutilização do IBGE |
| IPEA / Mapa das OSCs | "Other (Attribution)" (não padronizada) | metadado do portal (fase anterior) | **Não confirmado** | Sim — IPEA | (1) leitura manual de `mapaosc.ipea.gov.br/termosuso` (bloqueio por robots); (2) e-mail formal ao IPEA; (3) registrar resposta/data aqui |
| MDS / RBBA | **Não declarada** (página oficial lida não traz termos de uso dos dados) | leitura da página do MDS | **Não confirmado** | Recomendada — MDS/RBBA | E-mail a `cgesan@mds.gov.br`: licença, uso comercial, endpoint oficial, base completa |
| Coordenadas de município (kelvins/municipios-brasileiros) | **MIT** (repositório); origem primária **não declarada** | arquivo `LICENSE` | MIT permite; **mas a licença MIT do repositório não resolve a licença da origem dos dados** | Manter aviso de copyright MIT (Kelvin S. do Prado) | Substituir/validar pela malha oficial IBGE e citar a licença do IBGE |
| Receita Federal — CNPJ (estabelecimentos) | **Não verificada.** Rodapé geral do site da Receita cita CC BY-ND 3.0 para *conteúdo do site*, **não** para a base | trecho do site | **Não confirmado** | A definir | Obter licença do conjunto; usar só PJ/agregados; excluir Sócios |
| Referências publicadas (MAPA 2022, Embrapa 2003, Mesa Brasil) | Direitos autorais das publicações; **licença de reprodução não analisada** | — | Citar números com fonte; **não copiar tabelas/textos** | Sim (citação) | — |
| **Coordenadas de município — confirmação (pendência 4.3)** | MIT é do repositório; **origem primária das coordenadas NÃO confirmada** | — | — | — | **Permanecem PROXY**, com origem primária não confirmada: **limitação conhecida**. Substituição/validação pela malha oficial do IBGE continua **PENDENTE** (não resolvida) |
| TACO 4ª ed. (NEPA/UNICAMP) | **Página não declara licença nem termos de reprodução** (só formatos Excel/PDF e contatos) | página `nepa.unicamp.br/categoria/taco/` | **Não confirmado** | A definir | E-mail a `nepa@unicamp.br`; **NEEDS_REVIEW — não entra em produção; não usar como lista de nomes até revisar** |
| Anvisa — Guia para Doação de Alimentos com Segurança Sanitária (2022) | "A reprodução parcial ou total ... é totalmente livre, desde que citada adequadamente a fonte. **A reprodução para qualquer finalidade comercial está proibida.**" | leitura por resumo (cópia hospedada na ABRAS) | **Proibido reproduzir** | Sim (citação) | **RESTRICTED**: citar/parafrasear; **revisão jurídica** antes de usar parâmetros em produto comercial; conferir o original no portal da Anvisa |
| Anvisa — Guia nº 16/2018 v2 | mesma cláusula (reprodução comercial proibida) | cópia de terceiro (regoola.io) | **Proibido reproduzir** | Sim | **RESTRICTED**; conferir no portal da Anvisa |
| MDS — Guia de avaliação de alimentos doados (2018) | "reprodução ... desde que citada a fonte e que **não seja para venda ou qualquer fim comercial**" | leitura por resumo | **Proibido reproduzir** | Sim | **RESTRICTED** |
| Anvisa — Guia nº 26/2019 Bancos de Alimentos | **sem trecho de licença** na leitura | leitura por resumo | Não confirmado | Sim (citação) | **NEEDS_REVIEW** |
| MDS — Catálogo de Produtos da Agricultura Familiar (2018) | "Qualquer parte desta publicação pode ser reproduzida, desde que citada a fonte." | leitura por resumo | Permitido com citação | Sim | APPROVED (nomes) |
| Conab — Compêndio PAA 2021 | "Qualquer parte desta publicação pode ser reproduzida, desde que citada a fonte." | leitura por resumo | Permitido com citação | Sim | APPROVED (referência) |
| SEDUC-GO — Critérios de validade | **sem licença/termos** no documento | leitura por resumo | Não confirmado | — | NEEDS_REVIEW (uso só qualitativo) |
| OpenStreetMap — dados (ODbL) | ODbL: **atribuição** ("© OpenStreetMap contributors", com link `openstreetmap.org/copyright`) e **share-alike** para base derivada; *produced work* pode ter outra licença; uso comercial permitido | página de copyright e FAQ da OSM Foundation (em inglês) | Permitido, **com share-alike sobre derivados** | **Sim** | **NEEDS_REVIEW — não integrado**; enquadramento de rotas próprias sobre dados OSM **em aberto (análise jurídica)** |
| Nominatim público | política de uso: ≤ 1 req/s, User-Agent identificado, **cache obrigatório**, sem uso intensivo/lote/revenda; foco em geocodificação exige instância própria | política oficial (inglês) | Restrito | Sim | **REJECTED** para o produto; instância própria só se aprovada |
| OSRM demo público | "uso restrito a casos razoáveis e **não comerciais**"; ≤ 1 req/s; sem garantias | wiki do projeto (inglês) | **Não** | — | **REJECTED** para o produto; **decisão:** haversine nas Fases 1 e 2-P1; OSRM só como extensão opcional, instância própria, após análise ODbL |
| Open Food Facts | Não analisada (ODbL) | — | — | — | Fora do escopo desta fase |

**Regra de conformidade aplicada:** NEEDS_REVIEW = IPEA/OSC, RBBA, coordenadas, CNPJ, TACO, Anvisa Guia 26, SEDUC-GO, dados OSM (e IBGE até citação da licença); RESTRICTED = guias Anvisa 2022/16-2018 e MDS 2018 (reprodução comercial proibida). Uso restrito a pesquisa/prototipagem acadêmica; não publicar bases brutas; nenhum dado desses entra em produção/comercialização antes da confirmação formal registrada neste arquivo.

**Pendências de terceiros mantidas como PENDENTES (nenhuma marcada como resolvida):** confirmação formal de licença do **IPEA** (Mapa das OSCs), do **MDS/RBBA** e do **IBGE**; obtenção da base de **CNPJ** (Receita) e da **malha oficial do IBGE**; contato com o **NEPA** (TACO).

## Nota — Fase 2 Parte 2 (outubro/2026)
Sem resposta aos pedidos de confirmação de licença, as bases públicas já processadas (ONGs, municípios, indicadores) seguem em **uso acadêmico** com licença **NEEDS_REVIEW** e `publication_cleared=false`; nada foi declarado como licenciado. Ver `docs/data/PENDING_LICENSE_CONFIRMATIONS.md`. Licenças de **software** adicionadas nesta parte: `docs/data/SOFTWARE_LICENSES.md`.
