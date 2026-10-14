# Licenças dos dados — publicação de DEMONSTRAÇÃO (Etapa B)

> **Decisão do grupo:** a publicação em nuvem é uma **demonstração acadêmica, sem fins comerciais** do Projeto Integrador. Nenhuma licença foi "assumida": onde a situação é **não confirmada**, isso está escrito abaixo. O detalhamento por fonte está em `docs/data/DATA_LICENSES.md` e `docs/data/PENDING_LICENSE_CONFIRMATIONS.md` (nada foi marcado como resolvido por causa desta decisão; `publication_cleared=false` continua valendo e é verificado por `tests/test_p2b_uso_academico.py`).
> Aviso mostrado em **todas** as telas do Streamlit e no README: *"Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais"*.

## Por conjunto de dados carregado no banco em nuvem
| Conjunto (origem) | Fonte | Situação da licença | O que vai para a nuvem |
|---|---|---|---|
| ONGs e entidades da sociedade civil (🟦 PÚBLICO) | IPEA — Mapa das OSCs | **Não confirmada** (metadado do portal diz "Other (Attribution)", que não é licença padronizada; termos de uso não lidos por bloqueio; e-mail sem resposta) | registros organizacionais por pseudônimo (sem pessoas físicas) |
| Bancos de alimentos (🟦 PÚBLICO) | MDS — RBBA | **Não confirmada** (licença não declarada na página oficial lida) | registros organizacionais |
| Municípios e população (🟦 PÚBLICO) | IBGE | **Não confirmada explicitamente** (dado aberto pela política de dados abertos, mas a licença/termos de reutilização não foram localizados) | municípios e indicadores de população |
| Coordenadas de município (🟦 PÚBLICO, PROXY) | repositório de terceiros (MIT) | **Não confirmada**: a MIT cobre o repositório, **não** a origem primária das coordenadas | centroides usados no mapa e nas distâncias |
| Indicadores PAA (🟦 PÚBLICO) | MDS — Programa de Aquisição de Alimentos | CC-BY segundo metadado de fase anterior; **reverificação no portal pendente** | indicadores agregados, com atribuição ao MDS |
| Doadores, lotes, textos, desfechos, perfis e frota de ONGs (🟧 SIMULADO) | gerados por `simulation/` (semente e versão) | **Sem terceiros**: produzidos pela própria equipe; rotulados `SIMULATED` | todos, com selo |
| Entradas reais da plataforma (🟩 MEDIDO) | usuários da demonstração | — | **nenhuma carga**: a carga em nuvem não cria registros `USER_ENTERED` |

**Não vão para a nuvem:** `data/raw` e bases brutas, CNPJ/Receita (não adotado), TACO, guias da Anvisa/MDS (RESTRICTED/NEEDS_REVIEW, só citados na documentação) e dados do OpenStreetMap. Não há exportação/download de bases pela API ou pela interface.

## Condições da demonstração
1. Uso **acadêmico, não comercial**, **até a data da apresentação**.
2. Atribuição às fontes nas telas "Dados públicos" e no README.
3. Os dados SIMULADOS nunca são apresentados como reais; métricas de IA são sempre "sobre dados simulados".

## Após o período demonstrativo (obrigatório)
* **Obter a licença** de cada fonte "não confirmada" (e-mail formal ao IPEA, ao MDS/RBBA e consulta aos termos do IBGE; registrar resposta e data em `DATA_LICENSES.md`) **ou remover** os conjuntos que continuarem sem confirmação.
* **Apagar o banco em nuvem** (Supabase → Project Settings → General → *Delete project*) e os serviços do Render; **revogar os tokens** (`python -m scripts.create_user --revoke <rótulo>`).
* Qualquer uso fora do ambiente acadêmico (produto, divulgação aberta de bases) **fica bloqueado** até as licenças serem confirmadas.

## Quem decide
Decisão registrada pelo grupo na **data: 13/10/2026**.
