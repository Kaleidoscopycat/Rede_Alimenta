# Motor de match DOADOR → ONG (Fase 2 Parte 1)

Versão do motor: `match-engine-1.0.0` · modelo: `ranker-1.0.0` (treinado em dados **SIMULADOS**) · distância: **haversine** (linha reta; **não** é rota; o roteamento é da Parte 2).

## Pipeline em tempo real (medido por etapa em `latency_ms`)
1. **Busca espacial** (BallTree haversine, raio configurável) → ONGs candidatas geográficas.
2. **Elegibilidade eliminatória** (7 regras, abaixo) sobre todas do raio; contagem por regra devolvida.
3. **Seleção**: as K=15 mais próximas entre as elegíveis (desempate: `BUSINESS_RULE_SCORE`, depois id).
4. **Scores separados**: `ML_SCORE`, `BUSINESS_RULE_SCORE`, `DISTANCE_SCORE` → `FINAL_SCORE = 0,5·ML + 0,3·REGRAS + 0,2·DIST`.
5. **Proposta** à 1ª colocada com reserva de capacidade em transação; ver ciclo de vida.

## Regras eliminatórias (usam só atributos DECLARADOS da ONG)
`E_LOCALIZACAO_AUSENTE` · `E_NAO_CADASTRADA` (doação real só para ONG cadastrada; doação SIMULATED pode usar registros públicos) · `E_CATEGORIA_NAO_ACEITA` · `E_CAPACIDADE` (capacidade diária − reservas do dia) · `E_REFRIGERACAO` · `E_HORARIO` (janela de 7 dias) · `E_PRAZO_VALIDADE` (espera + deslocamento ≥ horas até a validade).

## Premissas (NÃO calibradas com dados reais; configuráveis por ambiente)
* Pesos do FINAL_SCORE 0,5/0,3/0,2; componentes de regras: capacidade 0,35, refrigeração 0,30, tipo de ONG 0,20, contexto regional 0,15.
* `DISTANCE_SCORE = 0,5·exp(−d/30 km) + 0,5·folga relativa até a validade`.
* Deslocamento estimado: desvio × velocidade média + tempo de serviço (premissas da Fase 1; **não é rota**).
* 1 refeição = 0,4 kg (premissa da equipe, exposta na API).
* Prazo de resposta da ONG: 30 min; varredura de expiração a cada 15 s (tarefa em segundo plano no processo da API, sem fila externa).

## Ciclo de vida (`match_events`)
`RANKED → PROPOSED → ACCEPTED | DECLINED | EXPIRED → (próxima candidata: PROPOSED | SKIPPED | EXHAUSTED) → COLLECTED | FAILED`. Cada transição grava ator, ONG, posição e timestamp. Recusa/expiração libera a reserva e propõe à próxima; sem candidatas, `EXHAUSTED` e doação `NO_MATCH`. `FAILED` encerra o match e devolve a doação a `READY`. A UI usa polling (5 s).

## Lote: guloso × ótimo (simulação)
`POST /matches/batch-compare` (ADMIN): escolha gulosa (ordem de chegada) × atribuição ótima (`scipy linear_sum_assignment`), 1 lote por ONG por rodada, só as K candidatas. A diferença é gravada em `batch_assignment_runs`. Resultado de **simulação**, não é ganho real.

## Limitações
Capacidade, horários, categorias e refrigeração das ONGs são **declarados simulados**; ML_SCORE aprende o simulador (circularidade); distâncias são aproximadas quando há centroide de município (`location_precision`, `distancia_aproximada`); datas sem ano já passadas são projetadas para o ano seguinte pelo parser (o campo fica pendente e exige confirmação do doador); "vence ontem" não é reconhecido (bloqueio por validade ausente).
