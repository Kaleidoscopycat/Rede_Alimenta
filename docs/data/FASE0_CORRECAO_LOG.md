# Fase 0 — Correção de pendências (log) — 2026-10-02

Escopo: correção de pendências da Fase 0 (v2 → v3). Nada foi baixado de novo, nenhum dado simulado foi gerado, a Fase 1 não foi iniciada. Versões anteriores em `archive/` (sufixo `_v2_pre_correcao`).

## Contradições encontradas e corrigidas
1. FEASIBILITY §5 dizia que a análise semântica "NÃO é justificada nesta fase" × Agents.md/prompts da Fase 1 a incluem → seção reescrita (§5.1, decisão da equipe, risco de circularidade mantido, mitigação MANUALLY_LABELED).
2. Capacidade da ONG tratada só como oculta × motor de match da Fase 2-P1 usando capacidade/refrigeração declaradas → separada em LATENTE (oculta) e DECLARADA (observável, SIMULATED, ≠ real) em SPEC §4.3, FEASIBILITY §7 e DICTIONARY.
3. Nomes de produto atribuídos ao PAA/CONAB/TACO → PAA não traz produto, CONAB sem dataset, TACO NEEDS_REVIEW; nomes = fontes citadas + premissa do projeto (`product_name_origin`).
4. Panificados com vida útil 0–3 dias × Anvisa (≤24 h) → corrigido para 0–1 dia na SPEC.
5. CONAB (C5) classificada como dataset → reclassificada (dataset REJECTED; Compêndio PAA 2021 como referência).
6. `data_origin` sem MANUALLY_LABELED → DICTIONARY com 4 valores.
7. `location_precision` indefinido → EXACT / MUNICIPALITY_CENTROID / NONE + `geo_quality` (2 pontos RBBA SUSPEITA, 3 REVISAR; RAW não corrigido).
8. Coordenadas: confirmado em LICENSES que seguem PROXY, origem primária não confirmada.

## Verificação do Agents.md (apenas listagem; arquivo NÃO alterado)
- §7 lista `data_origin` só como PUBLIC|SIMULATED|USER_ENTERED (falta MANUALLY_LABELED).
- "NUNCA SIMULADO: categorias de alimento e referências de validade" contradiz "vida útil sem fonte é premissa".
- Lacuna dos textos diz gerados "a partir de nomes REAIS de produtos (PAA/CONAB, TACO)" — não confirmado pelas fontes.
- Não menciona capacidade declarada × latente nem campos declarados (categorias aceitas, horário).
- `location_precision` só EXACT|MUNICIPALITY_CENTROID (falta NONE e `geo_quality`).
- Nome DATA_SIMULATION.md vs DATA_SIMULATION_SPEC.md; arquivo chama-se `Agents.md`.
- Haversine nas Fases 1 e 2-P1 / OSRM como extensão opcional: não verificado como presente.

## Pendências reais
- Licenças/termos IPEA, RBBA, IBGE: PENDENTES. CNPJ (Receita) e malha municipal IBGE: PENDENTES.
- Domínios .gov.br inacessíveis do ambiente (não contornado); números das fontes da P3 lidos por resumo — reconferir nos PDFs.
- Tamanho do conjunto MANUALLY_LABELED: decisão da equipe (critério na SPEC §7).
- Tabela pública de vida útil por categoria: não localizada → premissa.
- Análise jurídica ODbL antes de qualquer uso de OSM/OSRM.
