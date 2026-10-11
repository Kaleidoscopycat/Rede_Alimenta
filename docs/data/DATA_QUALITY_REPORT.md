# Relatório de qualidade de dados (automático)

Gerado em 2026-10-03T16:30:41.673413+00:00 por `python -m quality.data_quality` (conjunto simulado: `main`).

**Status:** OK

## Achados

- Nenhum achado automático.

## Dados REAIS (silver/gold, data_origin=PUBLIC)

| Tabela | Linhas | Cols | Dup. chave | Colunas c/ nulos | PII (nome/valor) |
|---|---:|---:|---:|---:|---|
| silver/osc | 960.315 | 30 | 0 | 2 | 0/0 |
| silver/rbba | 192 | 24 | 0 | 0 | 0/0 |
| silver/municipios | 5.571 | 13 | 0 | 0 | 0/0 |
| gold/organizations | 54.590 | 26 | 0 | 8 | 0/0 |
| gold/territory | 5.571 | 16 | 0 | 0 | 0/0 |

- `silver/osc` maiores % de nulos: municipio_ibge 0.0%, uf 0.0%
- `gold/organizations` maiores % de nulos: modalidade_rbba 99.7%, natureza_juridica 0.4%, ano_fundacao 0.4%, area_assistencia_social 0.4%, area_desenv_direitos 0.4%, area_saude 0.4%
- `gold/organizations.lat`: min -33.5, max 4.48, fora da faixa: 0
- `gold/organizations.lon`: min -72.9, max -32.4, fora da faixa: 0
- `gold/organizations.populacao_2026`: min 1.18e+03, max 1.19e+07, fora da faixa: 0
- `gold/territory.latitude`: min -33.7, max 4.6, fora da faixa: 0
- `gold/territory.longitude`: min -72.9, max -32.4, fora da faixa: 0
- `gold/territory.populacao_2026`: min 857, max 1.19e+07, fora da faixa: 0

## Dados SIMULADOS (data_origin=SIMULATED)

| Tabela | Linhas | Cols | Dup. chave | Colunas c/ nulos | PII (nome/valor) |
|---|---:|---:|---:|---:|---|
| sim_donor | 8.000 | 18 | 0 | 0 | 0/0 |
| sim_lot | 60.000 | 26 | 0 | 0 | 0/0 |
| sim_ong_declared | 54.590 | 23 | 0 | 0 | 0/0 |
| sim_fleet | 54.590 | 12 | 0 | 2 | 0/0 |
| sim_pair_outcome | 895.177 | 39 | 0 | 4 | 0/0 |

- `sim_donor.lat`: min -33.7, max 4.6, fora da faixa: 0
- `sim_donor.lon`: min -72.9, max -34.8, fora da faixa: 0
- `sim_lot.quantidade_kg`: min 5, max 5e+03, fora da faixa: 0
- `sim_lot.dias_ate_validade`: min 0, max 319, fora da faixa: 0
- `sim_lot.horas_ate_validade`: min 3.04, max 7.67e+03, fora da faixa: 0
- `sim_fleet` maiores % de nulos: tipo_veiculo 71.1%, capacidade_kg 71.1%
- `sim_fleet.capacidade_kg`: min 200, max 1.2e+04, fora da faixa: 0
- `sim_pair_outcome` maiores % de nulos: coleta_em 75.1%, horas_ate_coleta 75.1%, resposta_em 17.9%, horas_resposta 17.9%
- `sim_pair_outcome.dist_km`: min 0, max 150, fora da faixa: 0
- `sim_pair_outcome.tempo_deslocamento_est_h`: min 0.505, max 4.84, fora da faixa: 0

## Geografia das organizações (REAL)

- `location_precision`: {'MUNICIPALITY_CENTROID': 54400, 'EXACT': 190}
- `geo_quality`: {'NAO_APLICAVEL': 54398, 'OK': 187, 'REVISAR': 3, 'SUSPEITA': 2}
- ranqueáveis por distância: 54590 de 54590
