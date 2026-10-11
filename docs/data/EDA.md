# EDA — Rede Alimenta IA (Fase 1)

Gerado automaticamente por `python -m eda.eda`. **Seção A = dados REAIS (`data_origin=PUBLIC`). Seção B = dados SIMULADOS (`data_origin=SIMULATED`).** Nada de B deve ser lido como fato do mundo real.

## A. Dados REAIS

### A.1 Organizações (gold/organizations)

- Total: **54,590** organizações (`ong_tipo`: OSC_ASSISTENCIA 54,398, BANCO_ALIMENTOS_RBBA 192).
- Ranqueáveis por distância (coordenada utilizável): **54,590** (100.0%).
- `location_precision`: MUNICIPALITY_CENTROID 54,400, EXACT 190.
- `geo_quality`: NAO_APLICAVEL 54,398, OK 187, REVISAR 3, SUSPEITA 2.

### A.2 Cobertura por UF (organizações por 100 mil habitantes)

Extremos (vieses de cobertura do cadastro IPEA/OSC e da RBBA):

| uf | orgs | ranqueaveis | bancos | pop_milhoes | orgs_por_100mil_hab |
|---|---|---|---|---|---|
| RR | 64.00 | 64.00 | 1.00 | 0.76 | 8.41 |
| PA | 842.00 | 842.00 | 4.00 | 8.76 | 9.62 |
| AP | 107.00 | 107.00 | 1.00 | 0.81 | 13.21 |
| AM | 613.00 | 613.00 | 1.00 | 4.36 | 14.06 |
| SE | 355.00 | 355.00 | 3.00 | 2.31 | 15.39 |
| SP | 12,944.00 | 12,944.00 | 39.00 | 46.18 | 28.03 |
| DF | 858.00 | 858.00 | 2.00 | 3.01 | 28.51 |
| RS | 3,436.00 | 3,436.00 | 9.00 | 11.23 | 30.59 |
| PR | 3,725.00 | 3,725.00 | 10.00 | 11.95 | 31.17 |
| MG | 9,474.00 | 9,474.00 | 52.00 | 21.46 | 44.15 |

Viés: o cadastro IPEA/OSC cobre organizações formais; ONGs informais (as que mais recebem doação direta) estão **ausentes**. A RBBA cobre só bancos de alimentos da rede. Distribuição por UF segue o cadastro, não a necessidade.

- Municípios com ≥1 organização: **4,425** de 5,571; sem nenhuma: 1,146. Mediana de organizações por município com ≥1: 4.

### A.3 Referência agregada RBBA (REAL, agregada)

```json
{
 "ano": 2025,
 "kpis": {
  "bancos": 362,
  "aderidos": 208,
  "municipios": 176,
  "ufs": 27,
  "relatorios": 161,
  "kg_recebidos": 66285063.38,
  "kg_doados": 62483403.16,
  "kg_perdidos": 3215754.25,
  "pct_perda": 0.04851401033690918,
  "pessoas_atendidas": 5167799,
  "instituicoes": 11071,
  "bancos_perdas": 78,
  "bancos_acoes": 119,
  "bancos_projetos": 60,
  "registros_descartados": 0
 },
 "mensal": [
  {
   "mes": "Jan",
   "recebido": 5244552.86,
   "doado": 4840828.54
  },
  {
   "mes": "Fev",
   "recebido": 5352755.31,
   "doado": 5039820.38
  },
  {
   "mes": "Mar",
   "recebido": 5207349.85,
   "doado": 4854757.45
  },
  {
   "mes": "Abr",
   "recebido": 5254775.23,
   "doado": 4919383.12
  },
  {
   "mes": "Mai",
   "recebido": 5721468.83,
   "doado": 5390808.16
  },
  {
   "mes": "Jun",
   "recebido": 5201945.36,
   "doado": 4881912.03
  },
  {
   "mes": "Jul",
   "recebido": 5533178.45,
   "doado": 5191874.12
  },
  {
   "mes": "Ago",
   "recebido": 5009493.04,
   "doado": 4770085.92
  },
  {
   "mes": "Set",
   "recebido": 5752836.8,
   "doado": 5348430.5
  },
  {
   "mes": "Out",
   "recebido": 6107488.39,
   "doado": 5880886.74
  },
  {
   "mes": "Nov",
   "r
```

## B. Dados SIMULADOS

Conjunto `main` — 0.2.0+477ed37e+20261003; cenário {'aceitacao': 'media', 'hortifruti': 'alto', 'declarado': 'base'}. Rótulo obrigatório: *calculado sobre dados SIMULADOS*.

- Lotes: **60,000**; doadores: **8,000**; pares candidatos: **895,177**; target médio: **0.197**.

### B.1 Mix de lotes por categoria

| categoria | lotes | kg_total | kg_mediana | validade_mediana_dias | pct_lotes |
|---|---|---|---|---|---|
| FRUTAS | 13,395.0 | 4,706,969.2 | 221.0 | 5.0 | 22.3 |
| HORT_FRUTOS | 10,479.0 | 2,775,301.6 | 172.0 | 6.0 | 17.5 |
| HORT_FOLHOSAS | 10,403.0 | 1,095,136.8 | 69.0 | 2.0 | 17.3 |
| HORT_RAIZES | 10,399.0 | 4,532,086.5 | 280.0 | 22.0 | 17.3 |
| INDUSTRIALIZADOS | 2,876.0 | 1,714,150.5 | 396.0 | 151.0 | 4.8 |
| GRAOS_CEREAIS | 2,615.0 | 2,038,109.5 | 490.0 | 186.0 | 4.4 |
| LATICINIOS_OVOS | 2,258.0 | 607,782.5 | 168.0 | 9.0 | 3.8 |
| CARNES_PESCADOS | 2,141.0 | 478,183.5 | 146.0 | 30.0 | 3.6 |
| PANIFICADOS | 1,993.0 | 131,094.5 | 42.0 | 0.0 | 3.3 |
| REFEICOES_PRONTAS | 1,984.0 | 150,519.2 | 48.0 | 1.0 | 3.3 |
| BEBIDAS | 1,457.0 | 726,031.0 | 312.0 | 94.0 | 2.4 |

Comparação com referências (`realism.json`):

- **R2 (PASSA)** — mix NOVA em kg vs RBBA 2025.
- **R3 (PASSA)** — índice mensal de kg (jan..dez) vs RBBA 2025.
- **R4 (PASSA)** — nº de lotes por UF vs população por UF.
- **R6 (REPORTADO)** — kg de lotes sem NENHUM par positivo (sem destino possível dentro da validade) vs perda RBBA.

- **R1 NÃO PASSA (registrado, não escondido):** volume anual simulado por banco de alimentos é ~2 ordens de grandeza menor que a referência RBBA (411,7 t/relatório/ano) porque o simulador gera apenas o fluxo de doadores do universo simulado, sem calibrar o volume por banco.
- **R6:** 45.5% do kg simulado fica sem nenhum destino dentro da validade, contra ~4,85% de perda reportada pela RBBA: o simulador é **pessimista** quanto ao sucesso do desfecho; as taxas absolutas de sucesso não devem ser usadas como estimativa real.

### B.2 Desfecho simulado

- Resposta: RECUSOU 46.4%, ACEITOU 35.7%, SEM_RESPOSTA 17.9%; coleta 24.9%; target (coletou dentro da validade) 19.7%.
- Pares elegíveis pela regra: 17.8%; taxa de sucesso entre elegíveis 33.5% vs não elegíveis 16.7% (elegível ≠ sucesso: desfecho estocástico).

Taxa de sucesso por distância (SIMULADO):

| dist_km | target_% | pares |
|---|---|---|
| (-1.0, 0.001] | 20.4 | 626,972.0 |
| (0.001, 15.0] | 23.4 | 87,392.0 |
| (15.0, 30.0] | 15.0 | 90,869.0 |
| (30.0, 60.0] | 15.6 | 55,199.0 |
| (60.0, 100.0] | 17.1 | 23,903.0 |
| (100.0, 160.0] | 18.8 | 10,842.0 |

- Tempo de resposta simulado (h): mediana 21.4, p90 90.1. Tempo até coleta (h): mediana 45.9.

### B.3 Textos simulados

- Famílias de template: F2 16,823, F3 16,790, F1 14,363, F4 12,024 (F4 reservada = teste fora do treino).
- Validade: INFORMADA 83.7%, AUSENTE 12.3%, INFERIDA_PELA_CATEGORIA 4.0%.
- Casos difíceis (% dos textos):  64.2, validade_ausente 12.1, validade_ambigua 8.5, vago 7.0, duas_categorias 6.1, inconsistente_com_categoria 2.0.
- **Lacuna:** não existe nenhum corpus REAL de descrições de doação; os textos são gerados por templates da equipe. A avaliação em texto real depende do conjunto `MANUALLY_LABELED`, ainda inexistente.

### B.4 Vieses e limitações

- Circularidade: modelos aprendem o simulador; métricas medem aderência às premissas do gerador, não desempenho real.
- Doadores sintéticos: população como proxy da densidade de estabelecimentos (base de CNPJ não obtida).
- Localização do doador = centroide do município (`MUNICIPALITY_CENTROID`); distâncias dentro do mesmo município são 0 e rankings dentro do município dependem de atributos, não de distância.
- Rótulos contrafactuais: todos os pares candidatos têm desfecho, o que não ocorre em produção (só se observa o par acionado).

Figuras: `docs/data/eda_figs/` (`real_orgs_por_uf.png`, `sim_mix_categoria.png`, `sim_target_por_distancia.png`).
