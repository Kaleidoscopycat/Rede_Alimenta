# Fluxo de dados — Rede Alimenta IA

> Conferido em `pipelines/`, `simulation/`, `database/importers.py`, `api/routers/drafts.py`, `match/lifecycle.py`, `match/engine.py`, `docs/FASE2_P1_MATCH_ENGINE.md`.

## 1. Da fonte ao banco (rastreabilidade)

```mermaid
flowchart TD
    A["Fonte pública oficial<br/>(IPEA/OSC, RBBA, IBGE, PAA)"] -->|"download HTTPS<br/>SHA-256 por arquivo"| RAW["RAW<br/>cópia original (nunca alterada)"]
    RAW --> BRZ["BRONZE<br/>estrutura padronizada"]
    BRZ --> SLV["SILVER<br/>dados limpos, só pessoa jurídica"]
    SLV --> GLD["GOLD<br/>data/gold/organizations.parquet<br/>(ONG por pseudônimo, data_origin = PUBLIC)"]

    GEN["simulation.generator<br/>--seed --n-lots --n-donors"] --> SM["data/simulated/&lt;tag&gt;<br/>doadores, lotes, textos, perfil declarado,<br/>desfechos (data_origin = SIMULATED)"]
    GLD -->|"lê ONGs reais<br/>(o simulador nunca as gera)"| GEN

    GLD --> IMP["database/importers.py<br/>bootstrap_db · load_to_cloud"]
    SM --> IMP
    IMP --> PG[("PostgreSQL<br/>CHECK: SIMULATED exige<br/>generator_version, seed, dataset_version")]

    GLD --> TRN["ml.training.train<br/>+ sim_pair_outcome"]
    SM --> TRN
    TRN --> ART["ml/artifacts/ranker<br/>model.joblib + metadata.json (SHA-256)"]
    ART --> API["API: Ranker.__init__<br/>verifica o hash ao carregar"]
    PG --> API
```

Regras que o desenho impõe: dados reais nunca são inventados ou gerados; dados simulados ficam separados até o GOLD/banco e **sempre** com `data_origin`; o modelo é treinado com rótulos **simulados** (circularidade registrada em `docs/MODEL_CARD.md`).

## 2. Fluxo DOADOR → ONG (estados da doação e do match)

```mermaid
sequenceDiagram
    autonumber
    actor D as Doador (DONOR)
    participant API as API (FastAPI)
    participant M as Motor de match
    participant DB as PostgreSQL
    actor O as ONG (ORG)

    D->>API: POST /donations/drafts (cabeçalho do lote)
    D->>API: POST /donations/{id}/items (itens manuais) ou /items/from-text (sugestões)
    D->>API: PATCH item (confirma campos sugeridos)
    D->>API: POST /donations/{id}/finalize
    API->>DB: doação READY (validade = item mais próximo)
    D->>API: POST /matches
    API->>M: elegibilidade → K=15 candidatas → scores
    M->>DB: ranking guardado, reserva de capacidade e PROPOSED à 1ª colocada
    API-->>D: situação em linguagem simples (sem scores)
    O->>API: GET /matches (propostas dirigidas a ela)
    alt ONG aceita
        O->>API: POST /matches/{id}/respond accept=true
        API->>DB: match ACCEPTED, doação MATCHED
        O->>API: POST /matches/{id}/outcome COLLECTED ou FAILED
    else ONG recusa ou o prazo (30 min) expira
        O->>API: respond accept=false (ou varredura de expiração a cada 15 s)
        API->>M: libera reserva e propõe à próxima candidata
        M->>DB: PROPOSED à próxima, ou EXHAUSTED e doação NO_MATCH
    end
```

### 2.1 Estados

```mermaid
stateDiagram-v2
    direction LR
    [*] --> PROPOSED : POST /matches (1ª candidata)
    PROPOSED --> ACCEPTED : ONG aceita
    PROPOSED --> PROPOSED : recusa ou expiração, próxima candidata
    PROPOSED --> EXHAUSTED : sem candidatas restantes
    ACCEPTED --> COLLECTED : coleta registrada
    ACCEPTED --> FAILED : coleta falhou
    COLLECTED --> [*]
    FAILED --> [*]
    EXHAUSTED --> [*]
```

* Estados do match (`ck_match_status`): `PROPOSED`, `ACCEPTED`, `COLLECTED`, `FAILED`, `EXHAUSTED`. Eventos (`match_events`): `RANKED`, `PROPOSED`, `ACCEPTED`, `DECLINED`, `EXPIRED`, `SKIPPED`, `EXHAUSTED`, `COLLECTED`, `FAILED`, cada um com ator, ONG, posição e carimbo de tempo.
* Estados da doação (`ck_donation_status`): `DRAFT`, `PENDING_CONFIRMATION`, `READY`, `BLOCKED_EXPIRED`, `BLOCKED_NO_VALIDITY`, `MATCHING`, `MATCHED`, `NO_MATCH`, `HISTORICAL` (histórico simulado). `FAILED` devolve a doação a `READY`; `EXHAUSTED` leva a `NO_MATCH`.
* Uma candidata cujas regras deixam de valer no momento da proposta é **pulada** (`SKIPPED`), com reavaliação das regras eliminatórias.

## 3. Dentro do motor (uma requisição de match)

```mermaid
flowchart TD
    L["Doação READY<br/>(kg, validade, refrigeração, categorias, janela de retirada)"] --> S["Busca espacial: ONGs dentro do raio (150 km)"]
    S --> E["Regras eliminatórias sobre o DECLARADO<br/>localização, cadastro, categoria, capacidade,<br/>refrigeração, horário, prazo de validade"]
    E -->|"reprovadas"| X["Fora do ranking<br/>(motivo guardado; visível só ao ADMIN)"]
    E -->|"elegíveis"| K["K = 15 mais próximas"]
    K --> ML["ML_SCORE (ranker HGB)"]
    K --> BR["BUSINESS_RULE_SCORE<br/>capacidade, refrigeração, tipo, contexto regional"]
    K --> DS["DISTANCE_SCORE<br/>distância e folga até a validade"]
    ML --> F["FINAL = 0,5·ML + 0,3·REGRAS + 0,2·DIST"]
    BR --> F
    DS --> F
    F --> R["Ranking explicado → proposta à 1ª colocada"]
```

Pesos e premissas são **premissas da equipe, não calibradas com dados reais** (`docs/FASE2_P1_MATCH_ENGINE.md`). A distância é em linha reta (haversine), **não** rota viária; para 99,65% das ONGs a coordenada é o centroide do município.

## 4. Quem vê o quê

| Perfil | Vê | Não vê |
|---|---|---|
| DONOR | situação da doação e do match; ONG (pseudônimo) **só após o aceite** | scores, ranking, elegibilidade, saída do parser |
| ORG | a doação proposta, a própria distância e a "Análise da IA" em texto | scores, posição, outras ONGs |
| ADMIN | tudo (ranking, scores, modelo, parser), com `admin.access` auditado | — |

Detalhes e testes: `docs/ROLE_VISIBILITY.md`.

## 5. Validação dos diagramas Mermaid

Ver o fim de [`deployment.md`](deployment.md).
