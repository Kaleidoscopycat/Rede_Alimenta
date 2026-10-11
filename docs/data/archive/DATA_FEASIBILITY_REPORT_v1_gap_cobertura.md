# DATA_FEASIBILITY_REPORT.md

**Projeto:** Rede Alimenta IA
**Fase:** 0 — Data Discovery e Viabilidade Comercial
**Data:** 2026-09-23
**Decisão:** **GO** (condicional — ver limitações e escopo recomendado abaixo)

---

## 1. Quais dados existem (confirmado por acesso real)

Após pesquisa e download efetivo (não simulado) de fontes públicas oficiais, confirmamos a existência e acessibilidade real de:

- **Execução histórica do PAA** (Programa de Aquisição de Alimentos) por município e mês, via API pública do MDS (SAGI), cobrindo 2014–2026 dependendo da modalidade, incluindo valores pagos, quantidade de alimentos adquiridos e indicador de adesão municipal.
- **Dados territoriais e populacionais oficiais do IBGE**: todos os 5.571 municípios brasileiros, com população estimada 2026.
- **Cadastro de Organizações da Sociedade Civil (OSCs)** do IPEA/Mapa das OSCs, com 960.315 organizações, incluindo município, UF e área de atuação (ex.: Assistência social).
- **Localização georreferenciada de bancos de alimentos** vinculados à Rede Brasileira de Bancos de Alimentos (RBBA/MDS), 192 unidades com coordenadas, cidade, UF e modalidade de gestão, além de indicadores agregados nacionais (pessoas atendidas, kg doados/recebidos).

Todos os arquivos foram efetivamente baixados e estão em `data/raw/` (ver `docs/data/DATA_SOURCE_CANDIDATES.md` para detalhamento completo, e `docs/data/VALIDATION_LOG.txt` para a validação programática real com pandas).

## 2. Quais podemos usar

Utilizáveis com confiança (licença clara, dado real, schema validado):

- PAA (4 datasets, MDS, CC-BY) — **uso liberado**, inclusive comercial, com atribuição.
- IBGE Municípios e População — **uso liberado**, dados públicos oficiais.

Utilizáveis com ressalva (dado real, mas licença não plenamente confirmada para produção comercial):

- IPEA/Mapa das OSCs (licença "Other (Attribution)", não-padrão) — usar nesta fase de pesquisa; confirmar formalmente antes de produção comercial.
- RBBA/API resumo (licença não declarada na página) — usar nesta fase de pesquisa; solicitar confirmação formal à CGESAN/MDS (cgesan@mds.gov.br) antes de uso comercial.

Não utilizável (fonte não disponibilizou dados estruturados):

- CONAB (fonte própria) — nenhum dataset estruturado encontrado; necessidade já coberta pelas séries do MDS.

## 3. Quais possuem licença compatível

| Fonte | Licença | Compatível com uso comercial? |
|---|---|---|
| PAA (MDS, 4 datasets) | Creative Commons Attribution (CC-BY) | Sim |
| IBGE (municípios, população) | Dados abertos oficiais do IBGE | Sim |
| IPEA/Mapa das OSCs | "Other (Attribution)" — não-padrão | Não confirmado — requer validação |
| RBBA (MDS/Alimenta Cidades) | Não declarada | Não confirmado — requer validação |

## 4. Qual problema de IA é realmente viável

**NÃO é viável**, com os dados atualmente disponíveis, um modelo que meça diretamente "fome", "insegurança alimentar individual" ou "necessidade real da população" — nenhuma fonte encontrada nesta fase fornece um indicador validado de insegurança alimentar por município (ex.: dados do tipo VIGISAN/PENSSAN não foram localizados/acessados nesta fase; isso é registrado como limitação e pendência, não como dado assumido).

**É viável** um modelo (ou, mais apropriadamente nesta fase inicial, um índice/score de priorização baseado em regras e em proxies reais e mensuráveis) para **priorização operacional/geográfica**, respondendo à pergunta: *"em quais municípios a cobertura da rede de bancos de alimentos e do PAA parece proporcionalmente menor frente à população e à presença de organizações sociais — ou seja, onde expandir a rede de doação poderia ter maior impacto operacional?"*

Este é um problema de **priorização por gap de cobertura de infraestrutura**, não de medição de fome.

## 5. Qual será o target

Não existe, nos dados reais coletados, um rótulo (label) supervisionado validado de "necessidade real" ou "prioridade correta" por município. Portanto:

- **Não é recomendável, nesta fase, um modelo supervisionado** com target de "necessidade" ou "prioridade real" — isso exigiria um rótulo objetivo (ex: taxa validada de insegurança alimentar) que não foi encontrado.
- **Estratégia recomendada: não supervisionada / baseada em regras (score composto)**, justificada pela ausência de rótulo real: construir um **índice de gap de cobertura** a partir de features observadas diretamente (ver seção 6), combinando-as (ex.: via normalização + soma ponderada, ou clustering não supervisionado como k-means para agrupar municípios em perfis de cobertura). A saída é um **ranking/score de priorização operacional**, não uma predição de "fome".

## 6. Quais serão as features (SOMENTE reais, confirmadas nos dados)

| Feature | Fonte | Tipo | Classificação |
|---|---|---|---|
| Município / código IBGE | IBGE | Categórica/chave | Observação real |
| UF | IBGE / PAA / RBBA | Categórica | Observação real |
| População estimada 2026 | IBGE (SIDRA) | Numérica | Observação real |
| Indicador de adesão ao PAA | MDS (PAA) | Binária | Observação real |
| Valor pago / qtd. adquirida no PAA (histórico, por município) | MDS (PAA) | Numérica (série temporal) | Observação real |
| Quantidade de agricultores familiares fornecedores (PAA) | MDS (PAA) | Numérica | Observação real |
| Contagem de OSCs por município (total e por área "Assistência social") | IPEA/Mapa das OSCs | Numérica (derivada) | Observação real (contagem derivada de registros reais) |
| Presença de banco de alimentos RBBA no município | RBBA (MDS) | Binária | Observação real (limitada a 192 bancos georreferenciados) |

**Features solicitadas mas NÃO confirmadas nos dados reais encontrados (não serão usadas, e não devem ser inventadas):**

- Indicadores públicos de insegurança alimentar por município — **não localizados** nesta fase.
- Indicadores socioeconômicos amplos (renda, pobreza) por município — **não coletados** nesta fase (pendência para fase futura, via IBGE/SIDRA outras tabelas ou Cadastro Único, a investigar).
- Quantidade de beneficiários diretos por banco de alimentos, por município — a API RBBA fornece apenas agregados nacionais e top-10 bancos, não uma série completa por município; portanto "quantidade de beneficiários" NÃO pode ser usada como feature municipal granular nesta fase.

## 7. Quais limitações existem

1. **Ausência de indicador de insegurança alimentar validado** — o modelo não pode e não deve alegar medir "fome" ou "necessidade individual". Qualquer priorização gerada é um **proxy de cobertura de infraestrutura**, claramente rotulado como tal no produto final.
2. **RBBA cobre apenas 192 de 362 bancos cadastrados (georreferenciados)** — a rede completa de bancos de alimentos no Brasil pode ser maior do que o que está representado nos dados públicos acessados; há um viés de subcobertura.
3. **Licenças de 2 das 4 fontes (IPEA/OSC e RBBA) não estão plenamente confirmadas para uso comercial** — uso restrito a pesquisa/prototipagem até validação formal junto aos órgãos.
4. **CONAB não disponibilizou fonte estruturada própria** — dados de execução do PAA usados são os consolidados pelo MDS, o que é conceitualmente equivalente, mas não representa a perspectiva operacional/logística da CONAB (armazéns, estoques) que o projeto original também mencionava como interesse.
5. **Amostra do dataset IPEA/OSC (267 MB, 960 mil registros)** foi inspecionada via amostragem de 50.000 linhas por limitação de tempo de execução, não com leitura de 100% das linhas linha-a-linha nesta validação — o schema e a integridade estrutural foram confirmados na amostra; recomenda-se validação de linha completa (streaming/chunked) na Fase 1 antes de uso em produção.
6. **Sem série histórica multianual para RBBA** — API retorna apenas 2024–2025.

## 8. Diferenciação obrigatória: observação real vs. proxy vs. predição

- **Observação real:** população, execução histórica do PAA, presença de OSCs cadastradas, presença de banco de alimentos RBBA georreferenciado — todos diretamente extraídos de fontes oficiais, sem transformação subjetiva.
- **Proxy:** um "índice de cobertura da rede de segurança alimentar" construído a partir da combinação (ex.: normalizada e ponderada) das observações reais acima — é uma **aproximação de infraestrutura disponível**, não uma medição direta de necessidade ou fome.
- **Predição/priorização:** a saída do modelo (ranking ou cluster de municípios como "candidatos a priorização operacional") é uma **recomendação heurística derivada do proxy**, não uma afirmação factual sobre a situação de fome real da população local. Todo output do produto deve comunicar essa distinção explicitamente à ONG/usuário final.

---

## Decisão final: GO (condicional)

**GO** para avançar à Fase 1, com o seguinte escopo recomendado:

1. Construir um **índice de priorização operacional baseado em regras/score composto** (não um modelo supervisionado de "necessidade"), usando exclusivamente as features reais listadas na seção 6.
2. Tratar as fontes IPEA/OSC e RBBA como **NEEDS_REVIEW** — usar nesta fase de prototipagem, mas iniciar contato formal com IPEA e MDS/CGESAN para confirmação de licença antes de qualquer uso comercial/produção real.
3. Documentar claramente, em toda a interface do produto, que o índice é um **proxy de cobertura operacional**, não uma medição de fome ou insegurança alimentar.
4. Nas fases seguintes, investigar fontes adicionais de indicadores socioeconômicos e de insegurança alimentar (ex.: bases do Cadastro Único, VIGISAN/PENSSAN, ou tabelas SIDRA adicionais do IBGE) antes de considerar qualquer modelo supervisionado de necessidade real.
