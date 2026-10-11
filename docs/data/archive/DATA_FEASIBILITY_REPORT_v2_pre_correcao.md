# DATA_FEASIBILITY_REPORT.md — Go/No-Go da Fase 0 (revisada)

**Projeto:** Rede Alimenta IA · **Fluxo:** DOADOR → ONG · **Data:** 2026-10-02
(Versão anterior — índice de gap de cobertura municipal — arquivada em `docs/data/archive/`.)
**Decisão:** **GO CONDICIONAL** para a Fase 1, como **prova de conceito do pipeline de recomendação sobre dados parcialmente simulados**, com as condições da §9.

---

## 1. Quais dados reais existem (acessados e validados)
| Dado | Fonte | Registros reais | Papel |
|---|---|---|---|
| Universo de ONGs/OSCs (município/UF, natureza jurídica, 11 áreas de atuação) | IPEA/Mapa das OSCs | **960.315** (100% lido); **54.398** com "Assistência social" em 4.421 municípios | lado receptor |
| Bancos de alimentos georreferenciados + modalidade | MDS/RBBA | **192** pontos (161 municípios; 2 com coordenada incoerente) | lado receptor, com localização real |
| KPIs/série mensal/origem/classe NOVA da RBBA 2025 | MDS/RBBA | agregados nacionais (66,29 mi kg recebidos; 4,85% de perda; 161 relatórios) | calibração da simulação |
| Municípios e população 2026 | IBGE | **5.571** (pop. total 214.211.951) | território |
| Coordenadas de município | compilação MIT (origem IBGE **não confirmada**) | **5.571** (100% casam com IBGE; mediana 1,7 km vs pontos reais RBBA) | distância (PROXY) |
| PAA (volumes e adesão por município-mês) | MDS/SAGI | 49.627 + 8.367 + 19.032 + 29.350 | sazonalidade/volume e contexto territorial |
| Referências de desperdício/doação | MAPA 2022, Embrapa 2003, Mesa Brasil Sesc | publicações (não datasets) | ordem de grandeza e critérios |

## 2. Quais podemos usar
- **Uso pleno em pesquisa/prototipagem acadêmica (Checkpoint 1):** todas as acessadas acima.
- **Uso em produção comercial:** somente **PAA (CC-BY)** e a documentação do IPEA. IBGE exige citar licença/termos explícitos (não confirmados). **IPEA/OSC, RBBA e coordenadas = NEEDS_REVIEW → fora de produção** até confirmação formal (planos em `DATA_SOURCE_CANDIDATES.md`).

## 3. Licenças (resumo; detalhe em `DATA_LICENSES.md`)
PAA: CC-BY (compatível, atribuir ao MDS). IBGE: dado aberto, licença explícita **não localizada** (pendência). IPEA/OSC: "Other (Attribution)" — comercial **não confirmado**. RBBA: **não declarada**. Coordenadas: MIT (do repositório), origem primária **não declarada**. CNPJ/Receita: **não verificada** (e dados **não baixados**). Referências publicadas: citar fonte, não copiar tabelas.

## 4. O que precisará ser simulado e por quê
Nenhuma fonte pública traz **doações doador→ONG nem seus desfechos**, nem **perfil operacional de doadores** (a base de CNPJ dá distribuição de estabelecimentos, não quem doa), nem **capacidade/refrigeração das ONGs**, nem **vida útil por categoria**. Portanto são SIMULADOS: doadores, lotes, desfechos de aceite/coleta e (ocultos) atributos operacionais das ONGs — conforme `DATA_SIMULATION_SPEC.md`, parametrizados por: RBBA (escala, mix NOVA, sazonalidade, origem), PAA (sazonalidade hortifrúti), MAPA/Embrapa (ordem de grandeza do excedente), IBGE (geografia/população), IPEA/RBBA (universo real de ONGs).

## 5. Qual problema de IA é realmente viável
**Recomendação (ranking) doador → ONG:** dado um lote (categoria, kg, dias até a validade, refrigeração, janela, localização do doador), ranquear ONGs candidatas pela probabilidade de **aceitar e coletar antes de vencer**.
- **Viável como PoC técnica:** há universo real de receptores (ONGs/bancos), localização real aproximada, território real e parâmetros reais de escala/sazonalidade.
- **NÃO validável contra o mundo real hoje:** o alvo é simulado; qualquer métrica é **métrica de simulação**. O valor da PoC é demonstrar pipeline, rastreabilidade, comparação com baselines e comportamento sob misspecificação — **não** provar eficácia.
- Alternativa descartada: continuar com o "índice de gap de cobertura" (problema anterior; não é o problema do projeto).
- **Extensão opcional Hugging Face (análise semântica de validade/tipo de alimento): NÃO justificada nesta fase** — não há texto real de descrição de lotes nem rótulos reais; sobre texto simulado seria circular e artificial. Reavaliar quando houver lotes cadastrados por usuários (USER_ENTERED).

## 6. Target
- **Unidade de observação:** par (lote × ONG candidata).
- **`target = 1` se a doação foi aceita pela ONG e coletada dentro da validade** (e da janela de coleta); `0` caso contrário. Classe: **SIMULADO** (gerado por processo estocástico com ruído e fatores latentes, §5 da spec).
- **Justificativa:** é o desfecho operacional que importa ao doador (lote não vira desperdício) e à ONG (recebe o que consegue usar). Não mede fome, necessidade ou impacto em beneficiários.
- **Saída do modelo:** probabilidade/ranking → **PREDITO**; sempre rotulado "simulação" enquanto o treino for simulado.

## 7. Features candidatas — origem exata
| Feature | Origem/Fonte | Classe | Observação |
|---|---|---|---|
| categoria do alimento | taxonomia do projeto (premissa) com mix NOVA da RBBA | SIMULADO | |
| quantidade (kg) | simulador (âncora RBBA 411,7 t/relatório/ano) | SIMULADO | |
| dias até a validade | simulador (premissa por categoria) | SIMULADO | **sem fonte real de vida útil** |
| refrigeração exigida | derivada da categoria (premissa) | SIMULADO | |
| janela de coleta | simulador | SIMULADO | |
| dia da semana / hora | simulador | SIMULADO | |
| tipo/porte do doador | simulador; distribuição futura via CNPJ (PROXY) | SIMULADO | |
| UF/município do doador | município REAL amostrado (provisório ∝ população IBGE) | SIMULADO (amostragem) sobre chave REAL | |
| distância doador–ONG | haversine com coordenadas de município (e ponto RBBA quando válido) | **PROXY** | mesmo município = 0 km |
| mesmo município (flag) | derivado de códigos IBGE | REAL (derivado) | |
| tipo da ONG (OSC assistência / banco RBBA) | IPEA + RBBA | **REAL** | elegibilidade = PROXY |
| modalidade do banco (Público Municipal, SESC, OSC…) | RBBA | REAL | só 192 |
| área de atuação / natureza jurídica da OSC | IPEA | REAL | declarado; inconsistência nas subáreas → só áreas |
| nº de OSCs de assistência no município; presença de banco RBBA | derivados de IPEA/RBBA | REAL (derivado) | |
| população do município; adesão ao PAA | IBGE; MDS | REAL | |
| volume PAA histórico no município | MDS | PROXY | cobertura de registros instável |
| capacidade de armazenamento / refrigeração da ONG | **sem fonte real** | SIMULADO e **fora das features v1** (latente) | spec §4.3 |
| `contem_alergenico` | existe em `sim_lot` | SIMULADO | **não entra no modelo** (decisão da equipe) |
| restrição religiosa; `aceita_alergenicos` (ONG) | — | **não existem** | decisões da equipe respeitadas |

## 8. Limitações
1. **Circularidade:** o modelo aprende a lógica do simulador; ganho sobre baselines só tem valor demonstrativo. Mitigação e relato: spec §8.
2. **Ausência de verdade de campo** para aceite/coleta e para vida útil: premissas sem fonte, mitigadas por intervalos, múltiplas seeds e cenários.
3. **Elegibilidade das ONGs é PROXY:** nem toda OSC de assistência social recebe alimentos; sem flag de segurança alimentar nem capacidade.
4. **Localização:** só centroide de município para OSCs (RBBA tem ponto para 192); distância intramunicipal desconhecida; coordenadas de terceiros; 2 pontos RBBA com erro no RAW.
5. **RBBA:** 192 de 362 bancos com ponto; sem dados por banco; endpoint não documentado; só 2024–2025; "pessoas atendidas" apenas como contexto agregado.
6. **PAA:** sem produto/categoria; cobertura de registros muito variável entre anos (4.752 a 13.270 linhas/ano); só 3.781 municípios com execução na modalidade.
7. **Doadores:** sem CNPJ não há base de distribuição; provisório ∝ população (viés em municípios pequenos).
8. **Acesso:** 5 domínios oficiais bloqueados na sessão → CNPJ e malha oficial IBGE não obtidos; licenças IPEA/RBBA/IBGE/CNPJ não confirmadas.
9. **Rótulos contrafactuais completos** (todos os pares) ≠ logs reais (só o par acionado).

## 9. Condições do GO e preparação para a Fase 1
Pré-requisitos **executáveis** na Fase 1: criar `simulation/` + `params_v0.1.0.yaml` conforme a spec; camadas BRONZE/SILVER (normalização OSC, RBBA com `geo_quality`, centroides); testes de determinismo e de realismo R1–R6; baselines; relatório com rótulo "simulação".
Pré-requisitos **dependentes de terceiros (pendências reais):** (a) confirmar licenças IPEA, MDS/RBBA e IBGE; (b) obter CNPJ (estabelecimentos por CNAE/município) e malha oficial IBGE; (c) buscar tabelas públicas de vida útil e eventuais dados de aceite; (d) opcional: contato com Mesa Brasil/bancos para validar premissas.
**NO-GO automático** se, na Fase 1, qualquer dado simulado for apresentado sem `data_origin = SIMULATED` ou qualquer métrica simulada sem rótulo.
