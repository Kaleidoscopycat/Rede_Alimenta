# Roteirização das coletas (Fase 2 · Parte 2)

**Rótulo:** SIMULAÇÃO. Frota, janelas de retirada, capacidades, horários, doadores e lotes são `data_origin=SIMULATED` (premissas da Fase 1, seção 13.2). Distâncias e tempos são **estimativas** (linha reta × fator de desvio ÷ velocidade), **não** rota viária. Nenhum número deste documento é desempenho do mundo real.

## Problema e escopo
Roteirização de veículos com capacidade e janelas de tempo: o veículo sai de uma **base**, coleta em vários **doadores** e entrega a **uma ONG** (destino). Escopo inicial: uma ONG por rota, até 12 doadores (`ROUTE_MAX_STOPS`), doações **já aceitas** (`match.status=ACCEPTED`). Distribuição ONG → beneficiário está fora de escopo.

Restrições (todas verificadas por `routing.core.evaluate`, um verificador independente do solver):
1. capacidade do veículo (kg) e capacidade diária de recebimento da ONG;
2. janela de retirada de cada doador (a carga precisa terminar dentro dela);
3. **entrega concluída até a validade menos a margem de segurança** (`ROUTE_SAFETY_MARGIN_H`, padrão 2 h; também por requisição);
4. refrigeração (lote refrigerado só em veículo refrigerado);
5. janela de funcionamento da ONG e horizonte máximo da viagem (`ROUTE_HORIZON_H`, 12 h).

Lotes que não cabem não entram: ficam em `unassigned` com o motivo (`REFRIGERACAO_INCOMPATIVEL`, `EXCEDE_CAPACIDADE_VEICULO`, `EXCEDE_CAPACIDADE_ONG`, `JANELA_INSUFICIENTE`, `JANELA_INALCANCAVEL`, `PRAZO_INVIAVEL`, `FORA_DO_HORIZONTE`, `JANELA_ONG_INVIAVEL`, `NAO_COUBE_NA_ROTA`). Entregar mais lotes sempre domina economizar km (penalidade por lote deixado de fora = 10 000 km + kg×10 m).

## Metodologia de distância e tempo (igual à Parte 1)
`km = haversine(lat, lon) × 1,35` (desvio); velocidade 22 km/h se a distância em linha reta ≤ 15 km, senão 55 km/h; minutos arredondados para cima; carga em cada doador = `tempo_carga` do doador; descarga na ONG = 30 min. Os mesmos valores de `api/service.py` (há teste de igualdade). Tudo configurável em `core/settings.py` (`ROUTE_*`) e gravado em `routes.parameters`.
Rota por malha viária real (OSRM/OpenStreetMap, ODbL) **não foi adotada**: é extensão futura (a licença ODbL exige atribuição e *share-alike* e a Fase 0 não a aprovou).

## Algoritmos
* **Baseline obrigatório:** vizinho mais próximo (`NEAREST_NEIGHBOR`) — a cada passo vai ao doador mais próximo que mantém a rota viável.
* **Solver:** Google OR-Tools (`ORTOOLS_GLS`): dimensões de tempo e capacidade, disjunções com penalidade, busca local guiada com limite de tempo (`ROUTE_SOLVER_TIME_LIMIT_S`, 3 s), partida a quente a partir do baseline. Se a solução fosse pior que o baseline ou reprovada pelo verificador, o plano mantém o baseline e registra `fallback_to_baseline`.
* **Licença do OR-Tools:** Apache License 2.0 (verificada nos metadados do pacote `ortools==9.15.6755`). Ver `docs/data/SOFTWARE_LICENSES.md`.

## Persistência e API
Migration Alembic `0002` cria `vehicles`, `routes`, `route_stops` (todas com `data_origin`; veículos importados do simulador: 15.758 `SIMULATED`, só 28,9% das ONGs têm frota). Cada plano grava duas linhas em `routes` (`plan_group_id` comum; `is_primary` = solver) com `algorithm`, `algorithm_version` (`routing-1.0.0`), `parameters`, `comparison`, `unassigned`, e as paradas `DEPARTURE`/`PICKUP`/`DELIVERY` em `route_stops`.
`data_origin` da rota = `USER_ENTERED` somente se **todas** as entradas forem; caso contrário `SIMULATED`, com gerador/semente/dataset da primeira fonte simulada.

Endpoints (perfis ORG e ADMIN; ORG só com doações aceitas pela própria ONG e veículos da própria ONG): `POST /api/v1/routes/plan` e `GET /api/v1/routes/{id}`. Testes: `tests/test_p2b_routing_core.py` (restrições, verificador, ótimo por força bruta, baseline × solver) e `tests/test_p2b_routes_api.py` (contrato 201/401/403/404/409/422, persistência, auditoria).

## Comparação baseline × solver (SIMULAÇÃO) — `docs/ROUTING_BENCHMARK.json`
Instâncias montadas com ONGs reais, frota/doadores/lotes simulados do banco, semente 20261011, 8 doadores ofertados por instância, saída 08:00, validade 48 h − margem 2 h, 30 instâncias por cenário. (O benchmark ignora as máscaras de dias da semana.)

| Cenário | Métrica (média) | Baseline (vizinho mais próximo) | Solver (OR-Tools) |
|---|---|---|---|
| Municípios vizinhos (reais, ≤ 40 km; **extensão além do escopo inicial**) | km totais | 82,83 | 95,38 |
| | tempo total (min) | 260,5 | 267,8 |
| | lotes entregues antes da validade | 1,80 | 2,07 |
| | kg entregues | 127,1 | 133,9 |
| Mesmo município (**degenerado**) | km totais | 0,0 | 0,0 |
| | tempo total (min) | 186,7 | 187,5 |
| | lotes entregues | 1,67 | 1,77 |
| | kg entregues | 130,7 | 135,2 |

Leitura honesta:
* Todas as rotas dos dois métodos passaram no verificador; o solver **nunca ficou pior que o baseline no objetivo** (lotes primeiro, depois km). Nos vizinhos: solver entregou **mais lotes em 7 de 30** instâncias e nenhuma vez menos; com o mesmo nº de lotes (23 de 30), usou **menos km em 4** e mais km em 0.
* A média de km do solver é **maior** nos vizinhos porque ele atende mais lotes (mais paradas), não porque percorra mais para os mesmos lotes.
* **Mesmo município é degenerado:** todos os doadores simulados de um município compartilham o centroide municipal (distância 0 entre eles), então km = 0 e só importam lotes/tempo. Por isso o cenário de municípios vizinhos foi acrescentado (ainda é simulação).
* Poucos lotes são elegíveis por instância (≈ 2–3 de 8 ofertados): as janelas de retirada e o prazo restringem fortemente. O ganho do solver é modesto e **não deve ser generalizado**.

## Pendências reais da roteirização
* Rota por malha viária (OSRM/OSM) — não feita; tempos são estimativas.
* Múltiplas ONGs de destino, múltiplos veículos e janelas multi-dia — não feitos.
* Interface (Streamlit) não exibe/solicita rota: só API (e o passo da rota em `scripts/e2e_flow.py`).
* No fluxo e2e do exemplo, base do veículo, doador e ONG ficam no mesmo município ou vizinhos, o que torna `km_est` pequeno; os números não indicam desempenho real.
