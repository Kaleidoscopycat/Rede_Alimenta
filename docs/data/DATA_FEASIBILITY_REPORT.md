# DATA_FEASIBILITY_REPORT.md — Go/No-Go da Fase 0 (revisada e corrigida)

**Projeto:** Rede Alimenta IA · **Fluxo:** DOADOR → ONG · **Versão:** v3 (correção de pendências, 2026-10-02)
Históricos: `archive/DATA_FEASIBILITY_REPORT_v1_gap_cobertura.md` (índice de gap de cobertura) e `archive/DATA_FEASIBILITY_REPORT_v2_pre_correcao.md` (v2, antes da correção).
**Decisão:** **GO CONDICIONAL** para a Fase 1, como **prova de conceito do pipeline de recomendação, análise semântica da doação e logística sobre dados parcialmente simulados**, com as condições da §9. **A Fase 1 não foi iniciada.**

---

## 1. Quais dados reais existem (acessados e validados)
| Dado | Fonte | Registros reais | Papel |
|---|---|---|---|
| Universo de ONGs/OSCs (município/UF, natureza jurídica, 11 áreas) | IPEA/Mapa das OSCs | **960.315** (100% lido); **54.398** com "Assistência social" em 4.421 municípios | lado receptor |
| Bancos de alimentos georreferenciados + modalidade | MDS/RBBA | **192** pontos (161 municípios; 2 com coordenada incoerente) | lado receptor, localização real |
| KPIs/série mensal/origem/classe NOVA da RBBA 2025 | MDS/RBBA | agregados (66,29 mi kg recebidos; 4,85% de perda; 161 relatórios) | calibração |
| Municípios e população 2026 | IBGE | **5.571** (214.211.951 hab.) | território |
| Coordenadas de município | compilação MIT (origem primária **não confirmada**) | **5.571** (100% casam; mediana 1,7 km vs pontos RBBA) | distância (PROXY) |
| PAA (volume/adesão por município-mês; **sem produto**) | MDS/SAGI | 49.627 + 8.367 + 19.032 + 29.350 | sazonalidade/volume, contexto territorial |
| **Referências publicadas** (desperdício, doação, composição do PAA, cadeia fria, taxonomia) | MAPA 2022; Embrapa 2003; Mesa Brasil; **Conab 2021**; **Anvisa 2019/2022/2024**; **MDS 2018** | publicações (não datasets) | ordem de grandeza, taxonomia e limites de cadeia fria (CANDIDATES §E, §G) |

## 2. Quais podemos usar
- **Pesquisa/prototipagem acadêmica (Checkpoint 1):** todas as acessadas.
- **Produção comercial:** somente **PAA (CC-BY)** e o dicionário do IPEA. IBGE exige citar licença explícita (não localizada). **IPEA/OSC, RBBA, coordenadas, TACO e CNPJ = NEEDS_REVIEW → fora de produção.** Guias Anvisa/MDS (G1, G2, G4) são **RESTRICTED** (reprodução comercial proibida; citar/parafrasear, revisão jurídica antes de uso comercial).

## 3. Licenças (resumo; detalhe em `DATA_LICENSES.md`)
PAA CC-BY · IBGE dado aberto (licença explícita não localizada) · IPEA "Other (Attribution)" (comercial não confirmado) · RBBA não declarada · coordenadas MIT (origem não declarada) · CNPJ/Receita não verificada (e não baixado) · TACO sem licença na página · Anvisa Guia de Doação 2022 e Guia 16/2018 e MDS Guia de avaliação 2018: reprodução livre com fonte, **uso comercial proibido** · MDS Catálogo 2018 e Conab Compêndio 2021: reprodução com citação · OpenStreetMap: ODbL (atribuição + share-alike), **não integrado**.

## 4. O que será simulado e por quê
Nenhuma fonte pública traz **doações doador→ONG e desfechos**, **perfil de doadores**, **descrições textuais de doações rotuladas**, **capacidade/refrigeração/horário reais das ONGs**, **frota**, nem **vida útil por categoria no momento da doação**. São SIMULADOS (`DATA_SIMULATION_SPEC.md` v0.2.0):
1. doadores, lotes e desfechos de aceite/coleta/tempos;
2. **descrições textuais dos lotes** (texto livre + rótulos de verdade), `data_origin = SIMULATED`, com avaliação separada em conjunto **MANUALLY_LABELED**;
3. **atributos operacionais da ONG em dois níveis:** LATENTE (oculto; dirige o desfecho) e **DECLARADO** (observável, simulado, ≠ real; usado em regras de elegibilidade e, rotulado, como feature);
4. **premissas logísticas:** janela de retirada (dias e horário), tempo de resposta e probabilidade de aceite da ONG, frota (tipo, capacidade, refrigeração, base), fator de desvio e velocidade.
Parametrização: RBBA (escala, mix NOVA, sazonalidade, origem), PAA/Conab (composição e sazonalidade agrícola), MAPA/Embrapa (ordem de grandeza do excedente), Anvisa (limites de tempo/temperatura), IBGE (geografia/população), IPEA/RBBA (universo real de ONGs). **Taxonomia, lista de nomes de produto e vida útil são premissas do projeto** (com âncoras parciais citadas).

## 5. Problema de IA e decisão sobre a análise semântica
**Problema principal (inalterado): recomendação (ranking) doador → ONG.** Dado um lote (categoria, kg, dias até a validade, refrigeração, janela, localização do doador), ranquear ONGs candidatas pela probabilidade de **aceitar e coletar antes de vencer**. **Target inalterado:** `target = aceitou ∧ coletou_dentro_validade` (SIMULADO). Saída do modelo = PREDITO, sempre rotulada "simulação" enquanto o treino for simulado. Alternativa descartada: índice de gap de cobertura (v1).

**Escopo ampliado — Logística Inteligente:** recomendação geográfica (haversine, `location_precision`), ciclo do match em tempo real (proposta → resposta → coleta, com timestamps) e rotas de coleta (extensão). **Todos os resultados de distância, tempo de match, rota e comparação entre estratégias obtidos com premissas simuladas são rotulados "simulação"**; a distância é em **linha reta** com fator de desvio **premissa**, nunca distância viária real.

### 5.1 Decisão sobre a análise semântica (Hugging Face) — **registro de decisão**
- **Decisão da equipe (registrada em 2026-10-02): a análise semântica de tipo, perecibilidade e validade ENTRA no projeto** (Fase 1, seção 12; Fase 2 Parte 1, seção 3.2), **treinada sobre textos SIMULADOS** e **avaliada em conjunto escrito e rotulado manualmente pela equipe** (`data_origin = MANUALLY_LABELED`).
- **Esta decisão substitui** a redação anterior (v2, seção 5) que afirmava que a extensão **"NÃO é justificada nesta fase"** por ser circular sobre texto simulado.
- **Motivo:** **falta de fonte pública conhecida de descrições de doação rotuladas** (categoria, perecibilidade, validade). Sem ela, a análise semântica só é viável com texto simulado; a equipe decidiu aceitá-la de forma documentada.
- **Risco original mantido (não foi eliminado):** a **circularidade continua existindo** — o modelo pode aprender os modelos de frase e o léxico do gerador, e as métricas em texto simulado podem **superestimar** o desempenho real. **O que mudou é a decisão de aceitar o risco com mitigação documentada**, não o risco.
- **Mitigação:** (i) conjunto **MANUALLY_LABELED** fora do treino e da validação, linguagem diferente do gerador (spec §7); (ii) **baseline de regras/dicionário** e escada de modelos (regras → TF-IDF de caracteres + regressão logística → modelo em português do Hugging Face **somente se superar o degrau anterior de forma mensurável no conjunto manual**; verificar licença do modelo); (iii) **métricas separadas por origem** (simulado/famílias vistas, simulado/famílias reservadas, MANUALLY_LABELED); (iv) a diferença simulado − manual é reportada como estimativa do otimismo.
- **Salvaguardas de segurança alimentar:** a IA **estrutura e sinaliza**; **nunca** afirma que um alimento é próprio ou impróprio; campos com baixa confiança vão para confirmação humana; **lote vencido é bloqueado por regra determinística, nunca por modelo**; subestimar perecibilidade é mais grave que superestimar. **Vida útil sem fonte é premissa documentada, nunca dado de fonte.**

## 6. Target
Inalterado (§5). Unidade de observação: par (lote × ONG candidata). Não mede fome, necessidade ou impacto em beneficiários. O parser semântico tem seus próprios rótulos de verdade (texto simulado e MANUALLY_LABELED), separados do target de match.

## 7. Features candidatas — origem exata
| Feature | Origem/Fonte | Classe | Observação |
|---|---|---|---|
| categoria, produto, perecibilidade | **taxonomia do projeto (premissa)**; no uso real, **PREDITO** pelo parser semântico (a partir do texto) | SIMULADO (treino) / PREDITO (inferência) | nomes **não** vêm do PAA/TACO (spec §3.2) |
| quantidade (kg) | simulador (âncora RBBA 411,7 t/relatório/ano) | SIMULADO | |
| dias até a validade; `validity_source` | simulador (premissa por categoria, âncoras Anvisa); no uso real, extraído do texto | SIMULADO / PREDITO | **sem fonte de vida útil** |
| refrigeração exigida | derivada da categoria/estado (premissa, âncora Anvisa) | SIMULADO / PREDITO | |
| janela de retirada (dias e horário); tempo de carga | simulador | SIMULADO | |
| dia da semana / hora | simulador | SIMULADO | |
| tipo/porte do doador | simulador; distribuição futura via CNPJ (PROXY) | SIMULADO | |
| UF/município do doador | município REAL amostrado (provisório ∝ população) | SIMULADO sobre chave REAL | |
| distância doador–ONG (linha reta) | haversine sobre coordenadas | **PROXY** | mesmo município = 0 km |
| tempo de deslocamento estimado; razão deslocamento/validade | distância × desvio ÷ velocidade + serviço | **SIMULADO** (premissas) | estimativa, não rota |
| `location_precision` (EXACT / MUNICIPALITY_CENTROID / NONE) e `geo_quality` | derivados de IPEA/RBBA/centroides | REAL (derivado) | feature **e** alerta na explicação |
| mesmo município (flag) | códigos IBGE | REAL (derivado) | |
| tipo da ONG; modalidade do banco; área de atuação; natureza jurídica | RBBA; IPEA | **REAL** | elegibilidade = PROXY |
| nº de OSCs de assistência no município; presença de banco RBBA | derivados | REAL (derivado) | |
| população; adesão ao PAA | IBGE; MDS | REAL | |
| volume PAA histórico no município | MDS | PROXY | cobertura de registros instável |
| **capacidade declarada, câmara fria declarada, categorias aceitas declaradas, horário declarado da ONG** | **gerados do latente, com ruído** | **SIMULADO (observável)** | **usáveis em regras e, rotulados, como feature**; nunca exibidos junto ao nome da ONG real como característica dela |
| **capacidade efetiva, câmara fria efetiva, aptidão, afinidade, efeitos aleatórios, horário real (LATENTES)** | simulador | SIMULADO (**oculto**) | **proibidos** como feature/regra |
| frota (tipo, capacidade, refrigerada, base) | simulador | SIMULADO | premissa |
| `contem_alergenico` | `sim_lot` / extraído do texto | SIMULADO / PREDITO | **fora das features do modelo** |
| restrição religiosa; `aceita_alergenicos` (ONG) | — | **não existem** | decisões da equipe respeitadas |

## 8. Limitações
1. **Circularidade (match):** o modelo aprende a lógica do simulador; ganho sobre baselines é demonstrativo (spec §10).
2. **Circularidade (texto):** o parser pode aprender os modelos de frase do gerador; métricas em texto simulado podem superestimar o desempenho real (spec §6). **Lacuna registrada:** não há fonte pública conhecida de descrições de doação rotuladas; a única medida honesta de generalização será o conjunto **MANUALLY_LABELED**, cujo **tamanho e anotadores ainda dependem de decisão da equipe**.
3. **Ausência de verdade de campo** para aceite/coleta, vida útil, frota, tempos de resposta e desvio/velocidade: premissas sem fonte, mitigadas por intervalos, múltiplas seeds e cenários.
4. **Capacidade da ONG:** não existe em fonte pública; o **declarado** é simulado e **diferente do real por construção**, e seu ganho preditivo mede a lógica do simulador.
5. **Taxonomia e nomes de produto são premissa do projeto** (guias Anvisa/MDS são RESTRICTED e inspiram, não fornecem dados); TACO em NEEDS_REVIEW.
6. **Elegibilidade das ONGs é PROXY:** sem flag de segurança alimentar nem capacidade.
7. **Localização:** só centroide de município para OSCs; 32 OSCs sem município (`NONE`, não ranqueáveis por distância); coordenadas de terceiros; 2 pontos RBBA com erro no RAW; **distância em linha reta** (sem malha viária; rota OSM só como extensão opcional, após análise de ODbL).
8. **RBBA:** 192 de 362 bancos com ponto; sem dados por banco; endpoint não documentado; 2024–2025; "pessoas atendidas" só como contexto agregado.
9. **PAA:** sem produto; cobertura de registros instável; 3.781 municípios com execução na modalidade.
10. **Doadores:** sem CNPJ, distribuição provisória ∝ população.
11. **Acesso/licenças:** CNPJ e malha oficial IBGE não obtidos; licenças IPEA/RBBA/IBGE/CNPJ/TACO não confirmadas; **as leituras da pendência 3 foram por resumo — números a reconferir nos PDFs originais**.
12. **Rótulos contrafactuais completos** (todos os pares) ≠ logs reais.

## 9. Condições do GO e preparação para a Fase 1
**Executáveis na Fase 1:** `simulation/` + `params_v0.2.0.yaml` conforme a spec; gerador de textos e conjunto de validação por famílias reservadas; BRONZE/SILVER (normalização OSC; RBBA com `geo_quality`; centroides; `location_precision`); função haversine testada; testes de determinismo e de realismo (R1–R6, T1–T3, L1–L3); baselines; parser semântico com baseline de regras; relatório com rótulo "simulação".
**Dependentes de terceiros/da equipe (PENDENTES, não resolvidas):** (a) licenças IPEA, MDS/RBBA, IBGE, NEPA/TACO; (b) CNPJ e malha oficial do IBGE; (c) conferir os PDFs originais dos guias e baixar o compêndio da Conab; (d) **decidir tamanho/anotadores do MANUALLY_LABELED**; (e) validar premissas de frota/resposta/desvio com operadores; (f) análise jurídica da ODbL se a extensão OSRM for aprovada.
**NO-GO automático** se, na Fase 1, dado simulado for apresentado sem `data_origin` ou métrica simulada sem rótulo, ou se atributo latente for usado como feature/regra.

## Adendo da Fase 1 (2026-10-03) — lacunas registradas

* **Textos de doação reais:** não foi encontrada fonte pública; a análise semântica foi treinada/avaliada em texto SIMULADO. O conjunto `MANUALLY_LABELED` não existe (ver `data/manual_labeled/README.md`).
* **Universo de doadores:** a base de CNPJ não foi obtida; a distribuição de doadores usa população por município como proxy (premissa).
* **Calibração do volume por banco de alimentos (R1):** não passa; volumes absolutos simulados não devem ser usados.
* **Viés pessimista do desfecho (R6):** 45,5% do kg simulado sem destino vs ~4,85% de perda reportada pela RBBA.
* **Modelo pré-treinado (Hugging Face):** não foi testado; a decisão do §5.1 permanece válida (só se o baseline TF-IDF+regras for insuficiente em texto real).
* **Licenças** de IPEA/OSC, RBBA e centroides de terceiros: continuam dependendo de confirmação (ver `DATA_LICENSES.md`); nenhuma licença foi presumida.
