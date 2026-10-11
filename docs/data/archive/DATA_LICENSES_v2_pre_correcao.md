# DATA_LICENSES.md

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
| TACO / Open Food Facts | Não analisadas (OFF = ODbL, exige análise antes de integrar) | — | — | — | Fora do escopo desta fase |

**Regra de conformidade aplicada:** NEEDS_REVIEW = IPEA/OSC, RBBA, coordenadas, CNPJ (e IBGE até citação da licença). Uso restrito a pesquisa/prototipagem acadêmica; não publicar bases brutas; nenhum dado desses entra em produção/comercialização antes da confirmação formal registrada neste arquivo.
