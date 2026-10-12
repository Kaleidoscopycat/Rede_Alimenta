# Doação com itens (Fase 3 · Parte 1 · Etapa A)

A doação passa a ser um **cabeçalho** com **itens**. Peso, validade e refrigeração do lote são **agregados** dos itens
(`api/aggregation.py`). Doações históricas do simulador (`SIMULATOR_IMPORT`) **não foram alteradas**: não têm itens detalhados
(colunas novas nulas) e continuam com `is_mixed_batch = false`. O fluxo de texto único da Fase 2 (`POST /api/v1/donations`) segue disponível.

> **Dados reais × simulados.** Nada aqui cria doador, ONG, produto ou doação reais. Os exemplos abaixo são de **formato**.
> Em demonstração, o fluxo roda apenas com registros do simulador (`SIMULATED`) por contas `--demo`; entrada real é `USER_ENTERED`.
> O `data_origin` do item é sempre o da doação (garantido no banco por FK composta).

## 1. Modelo de dados (migration `0003`, reversível)
| Onde | Campos novos |
|---|---|
| `donations` | `categories` (da de maior peso à de menor), `is_mixed_batch`, `aggregated_at`, `updated_at`; status `DRAFT` |
| `donation_items` | `description`, `perecibilidade` (derivada da categoria), `exige_refrigeracao`, `validity_days`, `expires_at`, `validity_source`, `validity_precision` (`DAY`/`MONTH`), `unit_weight` + `unit_weight_unit` (`kg`/`g`/`l`/`ml`), `weight_basis`, `entry_source` (`MANUAL`/`TEXTO_SUGERIDO`), `pending_fields`, `parser_suggestion`, `created_at`, `updated_at` |
| integridade | `UNIQUE (id, data_origin)` em `donations` + FK composta `(donation_id, data_origin)` em `donation_items`; CHECKs de unidade, par valor/unidade e bases de peso |

`alembic upgrade head` ⇄ `alembic downgrade 0002` testado com dados (`tests/test_p3a_xx_migracao_reversivel.py`). No downgrade, `DRAFT` volta a `PENDING_CONFIRMATION`.

## 2. Conversão para kg
`quantity_kg do item = número de unidades × peso (ou volume) de cada unidade × fator`.

| Entrada | Conversão | `weight_basis` | Estimado? |
|---|---|---|---|
| `kg`, `g` | × 1 ou × 0,001 | `MASSA_INFORMADA` | não |
| `l`, `ml` | volume em litros × **massa por litro da categoria** (`unit_mass_kg.litro` da taxonomia v0.2) ou, se a categoria não tiver, `DONATION_DEFAULT_DENSITY_KG_L` (1,0) | `VOLUME_CONVERTIDO` | **sim** (alerta e nota em toda resposta) |
| massa unitária por embalagem da taxonomia (caixa, pacote…) | **só como sugestão** do parser, nunca aplicada em silêncio | `MASSA_UNITARIA_CATEGORIA` | sim |

**Premissas e fontes.** As massas por litro e por embalagem vêm de `simulation/config/taxonomy_v0.2.yaml`
(**premissa do projeto, sem fonte externa**). O padrão de 1,0 kg/L também é premissa sem fonte. O peso mostrado ao doador, à ONG e ao ADMIN
carrega essa informação. Limite por item e por lote: `DONATION_MAX_TOTAL_KG` (padrão 100 000 kg).

## 3. Validade
* Data exata: vale até **23:59:59 (America/Sao_Paulo)** do dia informado (mesma convenção da Fase 2).
* **Mês/ano** (`MM/AAAA` ou `AAAA-MM`): usamos o **último dia do mês**, conforme definido pela equipe.
  Essa é a leitura **menos restritiva** (o produto pode vencer antes); por isso a resposta traz `validity_precision = MONTH` e uma nota, e no texto livre o campo fica **pendente** de confirmação.
* Validade vencida em qualquer item → `BLOCKED_EXPIRED` (cita o item); item sem validade → `BLOCKED_NO_VALIDITY`.

## 4. Agregação do lote (conservadora)
| Cabeçalho | Regra |
|---|---|
| `quantity_kg` | soma dos kg dos itens (`incomplete_weight` indica item sem peso) |
| `expires_at` / `validity_days` | **a mais próxima** entre os itens (o lote inteiro só pode ser entregue antes dela) |
| `exige_refrigeracao` | verdadeiro se **qualquer** item exigir; desconhecido se algum item não informou e nenhum exige |
| `perecibilidade` | a **mais restritiva** |
| `categoria` | a de **maior peso** (empate: a mais perecível; depois ordem alfabética); `categories` lista todas |
| `is_mixed_batch` | mais de uma categoria (nenhuma categoria nova foi criada) |
| aviso de validades | se a diferença entre a mais próxima e a mais distante passar de `DONATION_VALIDITY_SPREAD_WARN_DAYS` (60), a resposta sugere separar os itens de validade curta |

**Lote misto — limitação.** O ranker foi treinado e avaliado **somente com lotes simulados de uma única categoria**; o desempenho em lote misto é **desconhecido**.
O `ML_SCORE` usa a categoria predominante; a elegibilidade exige que a ONG aceite **todas** as categorias (`E_CATEGORIA_NAO_ACEITA`); o alerta vai ao ADMIN e à ONG.

## 5. API (somente DONOR/ADMIN; o doador só enxerga as próprias doações)
| Método e rota | Função |
|---|---|
| `POST /api/v1/donations/items/parse-preview` | divide um texto em itens **sem gravar nada** |
| `POST /api/v1/donations/drafts` | cria o rascunho (`texto` opcional → itens **sugeridos**) |
| `PATCH /api/v1/donations/{id}/draft` | janela de retirada, tempo de carga, alergênicos |
| `POST /api/v1/donations/{id}/items` · `…/items/from-text` | item manual · itens sugeridos de um texto |
| `PATCH /api/v1/donations/{id}/items/{item_id}` | corrige campos, `accept_fields` (aceita o sugerido), `confirm_item` |
| `DELETE /api/v1/donations/{id}/items/{item_id}` · `GET …/items` | remove · lista |
| `POST /api/v1/donations/{id}/finalize` | valida; `READY` só com todos os itens completos e confirmados |

Qualquer edição volta a doação a `DRAFT` (precisa finalizar de novo); com match em andamento a edição é recusada (409). Limite: `DONATION_MAX_ITEMS` (30).
`PATCH /donations/{id}/confirm` (fluxo antigo) é recusado em doações com itens.

## 6. Parser de texto livre em itens (`api/item_parser.py`)
Regras (regex) extraem produto, embalagem, número de unidades, peso/volume por embalagem e validade; o parser semântico da Fase 1 sugere categoria,
perecibilidade e refrigeração (treinado em texto **simulado**; desempenho em texto real **desconhecido**). Todo item do texto é **sugestão**:
`entry_source = TEXTO_SUGERIDO`, com `pending_fields` (`revisao_do_item`, `exige_refrigeracao` e o que faltar). Nada é inventado: sem peso, validade ou
número de unidades, o campo fica ausente e pendente (única exceção documentada: massa total sem embalagem assume 1 unidade e marca `quantidade` pendente).

Texto de regressão do parser (**usado só no teste do parser; não é doação**):
`arroz agulhinha tipo 1 (pacote de 5 kg, 3 unidades, validade 12/2027), feijão carioca (pacote de 1 kg, 5 unidades, validade 08/2027), macarrão espaguete (pacote de 500 g, 6 unidades, validade 05/2028) e óleo de soja (garrafa de 900 ml, 4 unidades, validade 10/2027)`
→ 4 itens: 15 kg + 5 kg + 3 kg + 3,312 kg (óleo estimado: 4 × 0,9 L × 0,92 kg/L), validades 31/12/2027, 31/08/2027, 31/05/2028 e 31/10/2027, todos pendentes de confirmação (`tests/test_p3a_parser_itens.py`).

## 7. Limitações conhecidas
* Textos ruidosos (como os do simulador) geram fragmentos que o doador precisa remover/corrigir; nenhuma sugestão é aceita sem confirmação.
* Lote misto: desempenho do ranker desconhecido (seção 4).
* Conversões em kg: premissas da taxonomia, sem fonte.
* Interface: nesta etapa não há tela de itens (só o mínimo para os contratos novos); a tela de itens é da Etapa B.
