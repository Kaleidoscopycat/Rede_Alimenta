# REDE ALIMENTA IA — AGENTS.md (versão adaptada: fluxo Doador → ONG)

Este arquivo contém regras obrigatórias e permanentes para qualquer
agente de IA que trabalhe neste repositório.
Antes de analisar, modificar, criar ou excluir qualquer arquivo deste projeto, leia este documento integralmente.
As regras deste arquivo têm prioridade sobre sugestões de implementação,
atalhos técnicos e decisões automáticas do agente.

## REGRA CRÍTICA

Este projeto separa rigorosamente dados REAIS de dados SIMULADOS.

- Dados REAIS (ONGs, bancos de alimentos, municípios, população,
  indicadores, histórico público, referências de alimentos) NUNCA
  podem ser inventados, mockados ou gerados por IA.
- Dados SIMULADOS são permitidos SOMENTE para o que não existe
  publicamente: doadores (perfis operacionais), lotes de doação e
  desfechos de match doador x ONG. Eles só podem ser gerados por
  simulador documentado, reprodutível, versionado e parametrizado por
  fontes reais, e devem ser marcados em todo lugar com
  `data_origin = SIMULATED`.
- Dado simulado NUNCA é apresentado como real, e métrica obtida em
  dado simulado NUNCA é apresentada como desempenho no mundo real.

Quando dados reais não estiverem disponíveis para algo que não seja
doação/doador/desfecho, documente a limitação e deixe a funcionalidade
pendente.

Você atuará como engenheiro de software sênior, engenheiro de dados, engenheiro de Machine Learning, arquiteto de soluções e especialista em DevSecOps. Leia integralmente o AGENTS.md antes de alterar qualquer arquivo.

PROJETO:
Rede Alimenta IA

CONTEXTO:

Este é um Projeto Integrador do curso de Tecnologia em Inteligência
Artificial da FIAP.
Embora seja inicialmente um projeto acadêmico, ele deve ser construído
desde o início com arquitetura, qualidade de código, segurança,
rastreabilidade de dados e organização suficientes para que possa
evoluir futuramente para um produto comercial real.
O projeto será desenvolvido em fases.
NÃO tente implementar todas as fases de uma vez caso este prompt esteja
sendo executado dentro de uma fase específica.

Entregáveis do professor por checkpoint:
- Mês 1: dataset estruturado (Público/Simulado), modelo funcional
  local, matriz STRIDE;
- Mês 2: Dockerfile + Compose, pipeline GitHub Actions, relatórios
  SAST (Bandit e Trivy);
- Mês 3: URL pública (Render ou Hugging Face), banco em nuvem
  (Supabase ou MongoDB Atlas), README completo e Pitch final.

==================================================
1. OBJETIVO DO PRODUTO
==================================================
Criar uma plataforma inteligente voltada à redução de desperdício
de alimentos, conectando em tempo real o DOADOR de alimentos
(supermercado, restaurante, indústria, atacadista, produtor) à
ONG / banco de alimentos que recebe a doação.

ESCOPO:
- DENTRO: doador → ONG (match, recomendação, logística da coleta).
- FORA: ONG → beneficiário final. A plataforma não seleciona nem
  prevê nada sobre pessoas beneficiadas. Indicadores agregados da
  região podem aparecer apenas como contexto.

A plataforma deverá combinar:
- dados públicos reais;
- organizações e equipamentos reais;
- localização geográfica real;
- dados socioeconômicos reais;
- informações históricas públicas reais;
- simulação documentada de doações (quando não houver dado real);
- inteligência artificial;
- mecanismo de recomendação;
- API;
- dashboard;
- banco de dados;
- segurança;
- rastreabilidade;
- observabilidade.

O objetivo futuro é permitir que doadores cadastrem lotes reais de
alimentos e o sistema identifique organizações potencialmente adequadas
para recebê-los.

A solução deverá levar em consideração, conforme os dados disponíveis:

- localização;
- distância;
- tipo do alimento;
- quantidade;
- validade;
- perecibilidade e necessidade de refrigeração;
- região;
- indicadores territoriais;
- histórico público relacionado à distribuição de alimentos;
- capacidade/características da instituição quando essa informação
  estiver publicamente disponível (ou parâmetro simulado documentado);
- restrições operacionais.

==================================================
2. REGRA ABSOLUTA: REAL vs SIMULADO
==================================================

É EXPRESSAMENTE PROIBIDO, para dados REAIS e em qualquer contexto:
- Faker;
- ONGs fictícias;
- municípios fictícios;
- coordenadas inventadas;
- CNPJs inventados;
- endereços falsos;
- dados gerados por IA apresentados como reais;
- mock data / dummy data / sample business data apresentados como reais.

É EXPRESSAMENTE PROIBIDO, para dados SIMULADOS:
- gerar sem seed, sem versão ou sem documentação das premissas;
- Faker ou valores aleatórios sem premissa vinculada a uma fonte real ou a uma justificativa documentada;
- omitir a marcação `data_origin = SIMULATED`;
- gerar dados de pessoas físicas;
- gerar CNPJ, endereço ou nome de empresa fictícios que possam se passar por entidades reais (doadores simulados usam identificador
interno, tipo, porte e município REAL);
- usar coordenadas inventadas (a localização do doador simulado é
derivada de município real);
- misturar dados reais e simulados em um mesmo número sem separação
visível;
- apresentar kg salvos, refeições, tempo de match ou acurácia
calculados sobre dados simulados sem o rótulo "simulação".

O QUE PODE SER SIMULADO (somente isto):
- doadores (perfil operacional: tipo, porte, município real);
- lotes de doação (categoria, quantidade, validade, refrigeração);
- descrições textuais dos lotes, usadas no treino da análise
  semântica de tipo, perecibilidade e validade (ver lacunas abaixo);
- desfechos de match (aceite, coleta, tempo);
- premissas logísticas: janela de retirada do doador, tempo de
  resposta e probabilidade de aceite da ONG, capacidade da ONG sem
  fonte real e frota de coleta (veículo, capacidade, refrigeração).

REGRAS DA LOGÍSTICA INTELIGENTE (recomendação geográfica, match em
tempo real e rotas de coleta):
- coordenadas só de fonte real; ONG sem coordenada exata usa o
  centroide do município e carrega `location_precision`
  (EXACT | MUNICIPALITY_CENTROID), exibido ao usuário;
- distância em linha reta e fator de desvio são premissas
  documentadas, nunca apresentadas como distância viária real;
- resultados de rota, tempo de match e comparação entre estratégias
  obtidos com premissas simuladas são rotulados como simulação;
- serviços de mapa e roteamento (OpenStreetMap, geocodificadores)
  só entram após análise de licença (ODbL) e de limites de uso.

LACUNAS DE DADOS CONHECIDAS (registro da equipe):
- Não há fonte pública confiável conhecida de descrições de doação em texto livre com rótulos (categoria, perecibilidade, validade). Por isso, os textos de treino da análise semântica são SIMULADOS, gerados a partir de nomes REAIS de produtos (PAA/CONAB, TACO e similares) e marcados com `data_origin = SIMULATED`.
- Consequência: métricas dessa análise obtidas em texto simulado
  podem superestimar o desempenho real (o modelo pode aprender os
  modelos de frase do gerador). Por isso é obrigatório manter um
  conjunto de teste escrito e rotulado manualmente pela equipe, fora
  do treino, com `data_origin = MANUALLY_LABELED`, e reportar suas
  métricas separadamente.
- Se surgir fonte pública confiável, ou se doações reais passarem a
  ser cadastradas, registrar aqui, avaliar a licença e substituir ou
  complementar o texto simulado.
- A análise semântica nunca declara um alimento próprio ou impróprio
  para consumo; ela estrutura os dados e sinaliza incertezas para
  confirmação humana. Vida útil sem fonte é premissa documentada,
  nunca dado de fonte.

O QUE NUNCA É SIMULADO:
- ONGs e bancos de alimentos;
- municípios, população, território e indicadores;
- categorias de alimento e referências de validade (vêm de fonte);
- histórico público (PAA etc.).

REQUISITOS DA SIMULAÇÃO:
- simulador em `simulation/`, com `generator_version` e `seed`;
- documento `docs/data/DATA_SIMULATION.md` com premissas, fonte de cada parâmetro, incertezas e validação de realismo;
- desfecho gerado por processo estocástico com ruído e fatores não
  observáveis, nunca por regra determinística que o modelo apenas
  redescobre;
- risco de circularidade documentado (o modelo aprende a lógica do
  simulador, não o mundo real);
- campos obrigatórios: `data_origin`, `generator_version`, `seed`,
  `dataset_version`;
- valores aceitos para `data_origin`: PUBLIC, SIMULATED, MANUALLY_LABELED (conjunto de teste escrito e rotulado pela equipe) e USER_ENTERED.

PREMISSAS DE PROJETO DEFINIDAS PELA EQUIPE:
- 0,4 kg por refeição (refeições = kg / 0,4), configurável e exibida
  na interface e na documentação.

DADOS TÉCNICOS EM TESTES:
Dados técnicos mínimos usados exclusivamente em unit tests de software
podem ser usados SOMENTE quando não representarem dados reais de negócio.
Exemplo permitido:
testar se uma função retorna HTTP 404.
Exemplo proibido:
criar uma ONG fictícia chamada "ONG Esperança" para testar o dashboard.

Se não existirem dados públicos suficientes para uma funcionalidade
que NÃO seja doação/doador/desfecho:
NÃO invente dados.

Em vez disso:

1. documente a ausência;
2. implemente a interface/estrutura necessária;
3. deixe a funcionalidade aguardando dados reais;
4. procure outra fonte pública confiável;
5. se necessário, altere a estratégia do modelo de IA;
6. documente a decisão.

==================================================
3. DADOS: PUBLIC-FIRST E COMMERCIAL-READY
==================================================
Todos os datasets externos devem ter:

- fonte;
- URL oficial;
- organização responsável;
- data de acesso;
- data de atualização do dataset;
- descrição;
- licença;
- condições de reutilização;
- possibilidade ou restrição para uso comercial;
- necessidade de atribuição;
- método de obtenção;
- hash/checksum quando o arquivo for armazenado;
- versão/data do snapshot utilizado.

Criar:
docs/data/
    DATA_SOURCES.md
    DATA_DICTIONARY.md
    DATA_LINEAGE.md
    DATA_LICENSES.md
    DATA_SIMULATION.md
Nunca assumir que:
"dado público = livre para qualquer uso comercial".
A licença deverá ser validada.
Priorizar fontes oficiais brasileiras.

Fontes candidatas a investigar:
- IPEA / Mapa das OSCs (ONGs);
- Rede Brasileira de Bancos de Alimentos;
- Ministério do Desenvolvimento e Assistência Social;
- IBGE (municípios, população, malha/coordenadas);
- SIDRA/IBGE;
- CONAB;
- Programa de Aquisição de Alimentos — PAA;
- dados abertos de estabelecimentos (Receita Federal / CNPJ), apenas
  nível de estabelecimento por CNAE, sem dados de pessoas físicas;
- referências públicas de desperdício, validade e perecibilidade de
  alimentos (Embrapa, FAO, MDS, ABRAS);
- dados.gov.br;
- bases governamentais estaduais/municipais;
- outras fontes oficiais.

Fontes internacionais poderão ser usadas apenas quando fizer sentido e quando sua licença for compatível.
Open Food Facts poderá ser analisado, mas NÃO deve ser integrado
automaticamente sem verificar as implicações da licença ODbL para um
produto comercial futuro.
==================================================
4. PRINCÍPIO DA IA
==================================================
Não criar Machine Learning apenas para dizer que existe IA.

Todo modelo deve:
- resolver uma tarefa bem definida (recomendação doador → ONG);
- usar dados reais sempre que existirem, e dados simulados apenas
  conforme a seção 2;
- possuir target/label justificável quando supervisionado;
- ter baseline;
- ter métricas;
- ter validação;
- permitir reprodução;
- registrar versão;
- registrar dataset (real e simulado);
- explicar limitações.

Métricas calculadas sobre dados simulados devem ser rotuladas como
tal em relatórios, API, dashboard, README e pitch.

Se NÃO houver base que sustente determinado modelo nem for possível
simulá-lo de forma honesta e documentada:
trocar o problema de IA por outro que possa ser validado, desde que
continue coerente com o objetivo da Rede Alimenta IA.

==================================================
5. ARQUITETURA BASE
==================================================

Estrutura desejada:

/
├── api/
├── app/
├── data/
│   ├── raw/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   └── metadata/
├── simulation/
├── ml/
│   ├── training/
│   ├── inference/
│   ├── evaluation/
│   └── artifacts/
├── pipelines/
├── database/
├── security/
├── tests/
├── docs/
│   ├── data/
│   ├── architecture/
│   ├── security/
│   └── api/
├── scripts/
├── .github/
│   └── workflows/
├── docker/
├── README.md
├── AGENTS.md
├── .env.example
├── docker-compose.yml
└── pyproject.toml ou requirements adequados

Stack preferencial:
Backend:
- Python;
- FastAPI;
- Pydantic;
- SQLAlchemy;
- Alembic.
IA:
- pandas;
- NumPy;
- scikit-learn;
- Hugging Face apenas quando justificado.
Frontend:
- Streamlit inicialmente.
Banco:
- PostgreSQL (Supabase na nuvem, ou MongoDB Atlas).
Infra:
- Docker;
- Docker Compose;
- Render ou Hugging Face para deploy.
CI/CD:
- GitHub Actions.
Segurança:
- Bandit;
- Trivy;
- dependency scanning;
- secret scanning quando possível.
Testes:
- pytest.
==================================================
6. QUALIDADE
==================================================

Obrigatório:
- typing;
- logging;
- tratamento de erros;
- configuração via environment variables;
- separação por camadas;
- código modular;
- migrations;
- testes;
- lint;
- documentação;
- sem secrets hardcoded;
- sem credenciais no Git;
- sem arquivos gigantes desnecessários versionados.
==================================================
7. RASTREABILIDADE DOS DADOS
==================================================
Todo dado ingerido deve ser rastreável. Cada registro processado deve
permitir identificar, quando aplicável:
source_id
source_name
source_url
source_dataset
source_updated_at
ingested_at
pipeline_version
data_origin   (PUBLIC | SIMULATED | USER_ENTERED)

Registros simulados também carregam:
generator_version
seed
dataset_version

O pipeline deverá seguir preferencialmente:
RAW → BRONZE → SILVER → GOLD.

RAW:
cópia original.

BRONZE:
estrutura padronizada.

SILVER:
dados limpos.

GOLD:
dados preparados para produto/IA/dashboard.
Nunca modificar silenciosamente o RAW.
Dados simulados ficam separados dos dados reais e só se juntam na
camada GOLD, com `data_origin` preservado.
==================================================
8. LGPD E PRIVACIDADE
==================================================
Dados públicos não eliminam obrigações de privacidade.
Evitar armazenar CPF, telefone, e-mail ou dados pessoais desnecessários.
Não coletar informações pessoais simplesmente porque estão disponíveis
publicamente.

Adotar:
- minimização;
- finalidade;
- controle de acesso;
- política de retenção;
- registro da origem;
- separação entre dados públicos, dados simulados e dados cadastrados
  futuramente por usuários.

Doadores e ONGs são pessoas jurídicas. Dados simulados não contêm
dados pessoais. Nenhum dado de beneficiário final é tratado.

==================================================
9. NÃO FAZER
==================================================

Não:
- inventar API;
- inventar dataset real;
- inventar resultado;
- inventar acurácia;
- inventar fonte;
- inventar licença;
- inventar endpoints externos;
- inventar números;
- apresentar simulação como realidade;
- ocultar falhas de ingestão;
- colocar valores hardcoded apenas para a demonstração parecer pronta.
Se uma API estiver indisponível:
registre o erro.
Se o dataset mudou:
adapte o parser.
Se os dados forem insuficientes:
documente.

==================================================
10. REGRA DE EXECUÇÃO
==================================================

Em cada fase:
Analise → planeje → implemente → execute → teste → corrija → teste novamente.
Não solicite confirmação entre pequenas etapas técnicas.
Não considere algo concluído sem executar os testes correspondentes.

Ao terminar uma fase:
1. liste o que foi implementado;
2. liste os datasets utilizados (reais e simulados);
3. informe a licença de cada um;
4. informe testes executados;
5. informe métricas relevantes (rotuladas quanto à origem dos dados);
6. informe problemas encontrados;
7. informe pendências REAIS para a próxima fase.
Nunca represente algo pendente como concluído.
