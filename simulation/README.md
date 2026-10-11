# simulation/ — Simulador de doações (SIMULATED)

Gera doadores, lotes, textos, perfis de ONG (latente e declarado), frota e desfechos de match **doador → ONG**, sempre sobre **ONGs e municípios REAIS** (`data/gold/`). Tudo que sai daqui é `data_origin = SIMULATED`.

```bash
python -m pipelines.run_all                 # pré-requisito: camadas gold (dados reais)
python -m simulation.generator --seed 20261003 --n-lots 60000 --n-donors 8000 --tag main
python -m simulation.validation main        # relatório de realismo (realism.json)
```

Opções de cenário: `--aceitacao baixa|media|alta`, `--hortifruti alto|baixo`, `--declarado fiel|base|otimista`.

## Estrutura

| Arquivo | Função |
|---|---|
| `config/taxonomy_v0.2.yaml` | 11 categorias, 85 produtos, `origin` por produto, massas unitárias |
| `params/params_v0.2.0.yaml` | Todos os parâmetros com `type` (REAL/REF/PREMISSA), `source` e `why` |
| `params.py` | Sorteio dos parâmetros por seed e hash (`params_hash`) |
| `entities.py` | Doadores, lotes, ONGs (latente, declarado, frota) |
| `textgen.py` | Textos F1–F3 (treino) e F4 (reservada), ruído e casos difíceis |
| `pairs.py` | Candidatas (haversine/BallTree), elegibilidade, logit e desfecho estocástico |
| `timeutil.py` | Horário comercial vetorizado |
| `generator.py` | Orquestração e gravação em `data/simulated/<tag>/` |
| `validation.py` | Checks R1–R6, T1–T3, L1–L3, oráculo, monotonicidade |

## Saídas (`data/simulated/<tag>/`)

`sim_donor`, `sim_lot`, `sim_lot_text`, `sim_ong_latent` (**oculta**: nunca usar como feature), `sim_ong_declared`, `sim_fleet`, `sim_pair_outcome`, `sim_oracle_check` (oráculo; só validação), `run_params.json`, `realism.json`. Campos obrigatórios em todas as tabelas: `data_origin`, `generator_version`, `seed`, `dataset_version`, `source_parameters`.

## Regras

* Sem Faker; sem pessoas físicas; sem restrição religiosa; sem `aceita_alergenicos`.
* Mesma seed ⇒ mesmos dados (`tests/test_simulator.py`).
* Métricas calculadas sobre estes dados devem sempre ser rotuladas **"calculada sobre dados SIMULADOS"**.
* Limitações e validação: `docs/data/DATA_SIMULATION.md` (R1 não passa; R6 mostra simulador pessimista).
