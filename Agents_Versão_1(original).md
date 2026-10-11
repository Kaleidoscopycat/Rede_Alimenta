# REDE ALIMENTA IA — AGENTS.md 

Este arquivo contém regras obrigatórias e permanentes para qualquer 
agente de IA que trabalhe neste repositório. 
Antes de analisar, modificar, criar ou excluir qualquer arquivo deste projeto, leia este documento integralmente. 
As regras deste arquivo têm prioridade sobre sugestões de implementação, 
atalhos técnicos e decisões automáticas do agente. 

## REGRA CRÍTICA 

Este projeto NÃO utiliza dados simulados de negócio. 
É proibido substituir ausência de dados reais por Faker, mocks, 
dados sintéticos, números inventados ou dados gerados por IA. 
Quando dados reais não estiverem disponíveis, documente a limitação 
e deixe a funcionalidade pendente.
 
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

================================================== 
1. OBJETIVO DO PRODUTO 
================================================== 
Criar uma plataforma inteligente voltada à redução de desperdício 
de alimentos e apoio à distribuição/doação de alimentos. 

A plataforma deverá combinar: 
- dados públicos reais; 
- organizações e equipamentos reais; 
- localização geográfica real; 
- dados socioeconômicos reais; 
- informações históricas públicas reais; 
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
- perecibilidade; 
- região; 
- indicadores de vulnerabilidade; 
- histórico público relacionado à distribuição de alimentos; 
- capacidade/characterísticas da instituição quando essa informação 
  estiver publicamente disponível; 
- restrições operacionais. 

================================================== 
2. REGRA ABSOLUTA: PROIBIDO SIMULAR DADOS 
================================================== 

É EXPRESSAMENTE PROIBIDO utilizar: 
- Faker; 
- dados sintéticos; 
- datasets artificiais; 
- registros inventados; 
- ONGs fictícias; 
- doadores fictícios; 
- coordenadas inventadas; 
- municípios fictícios; 
- CNPJs inventados; 
- endereços falsos; 
- doações falsas; 
- registros aleatórios; 
- valores randomizados; 
- mock data; 
- dummy data; 
- sample business data; 
- dados gerados por IA; 
- CSV inventado; 
- JSON de negócio inventado; 
- seeds artificiais; 
- treinamento em informações simuladas. 

Essa proibição vale para: 
- treinamento; 
- validação; 
- testes de modelo; 
- dashboard; 
- banco de desenvolvimento; 
- banco de demonstração; 
- exemplos exibidos no frontend; 
- gráficos; 
- métricas de negócio. 

Dados técnicos mínimos usados exclusivamente em unit tests de software 

podem ser usados SOMENTE quando não representarem dados reais de negócio. 
Exemplo permitido: 
testar se uma função retorna HTTP 404. 
Exemplo proibido: 
criar uma ONG fictícia chamada "ONG Esperança" para testar o dashboard. 
Se não existirem dados públicos suficientes para uma determinada 
funcionalidade: 
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
Nunca assumir que: 
"dado público = livre para qualquer uso comercial". 
A licença deverá ser validada. 
Priorizar fontes oficiais brasileiras. 

Fontes candidatas a investigar: 
- CONAB; 
- Programa de Aquisição de Alimentos — PAA; 
- Ministério do Desenvolvimento e Assistência Social; 
- IBGE; 
- SIDRA/IBGE; 
- dados.gov.br;
- Rede Brasileira de Bancos de Alimentos; 
- IPEA / Mapa das OSCs; 
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
- resolver uma tarefa bem definida; 
- usar dados reais; 
- possuir target/label justificável quando supervisionado; 
- ter baseline; 
- ter métricas; 
- ter validação; 
- permitir reprodução; 
- registrar versão; 
- registrar dataset; 
- explicar limitações. 
Se NÃO houver dataset público real que sustente determinado modelo: 
NÃO criar dataset artificial. 
Trocar o problema de IA por outro problema que possa ser validado 
com dados públicos reais, desde que continue coerente com o objetivo 
da Rede Alimenta IA.

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
- outras bibliotecas apenas quando justificadas. 
Frontend: 
- Streamlit inicialmente. 
Banco: 
- PostgreSQL. 
Infra: 
- Docker; 
- Docker Compose. 
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
Todo dado ingerido deve ser rastreável. 
Cada registro processado deve permitir identificar, quando aplicável:
source_id 
source_name 
source_url 
source_dataset 
source_updated_at 
ingested_at 
pipeline_version 
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
- separação entre dados públicos e dados cadastrados futuramente por 
  usuários.

================================================== 
9. NÃO FAZER 
================================================== 

Não: 
- inventar API; 
- inventar dataset; 
- inventar resultado; 
- inventar acurácia; 
- inventar fonte; 
- inventar licença; 
- inventar endpoints externos; 
- inventar números; 
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
2. liste os datasets utilizados; 
3. informe a licença de cada um; 
4. informe testes executados; 
5. informe métricas relevantes; 
6. informe problemas encontrados; 
7. informe pendências REAIS para a próxima fase. 
Nunca represente algo pendente como concluído.
 