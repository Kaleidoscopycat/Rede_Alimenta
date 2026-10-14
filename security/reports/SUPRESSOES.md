# Supressões de alertas — justificativas registradas

Regra do projeto: **nenhum alerta é suprimido sem justificativa registrada aqui**. Cada linha com `# nosec`/`# noqa` aponta para este arquivo.
Auditoria: o Bandit lista as supressões em `metrics._totals.nosec`/`skipped_tests` (`security/reports/depois/bandit.json`: 7 na Fase 2; **10** na execução da Fase 4 · Etapa A, que acrescentou três linhas que já existiam no código sem registro nesta tabela).

## Bandit (`# nosec`)

| Arquivo | Regra | Por que é seguro | Reavaliar quando |
|---|---|---|---|
| `api/auth.py` (`TOKEN_PREFIX = "rai_"`) | B105 | É apenas o **prefixo público** do formato do token (facilita varredura de segredos); não é credencial. O token real é gerado com `secrets` e só o hash é armazenado. | Se o prefixo passar a conter segredo (não deve). |
| `scripts/bootstrap_db.py` (import `subprocess`) | B404 | Ferramenta administrativa local; o módulo é usado só para chamar o Alembic. | Se o script passar a aceitar comandos externos. |
| `scripts/bootstrap_db.py` (`subprocess.run([... "alembic" ...])`) | B603 | Lista de argumentos **fixa** (`sys.executable -m alembic upgrade head`), sem shell e sem entrada do usuário. | Idem. |
| `scripts/e2e_flow.py` (import `subprocess`) | B404 | Script de validação ponta a ponta, executado por quem opera o ambiente. | — |
| `scripts/e2e_flow.py` (`subprocess.run([... "scripts.create_user" ...])`) | B603 | Argumentos montados pelo próprio script (papel, rótulo, UUIDs), sem shell; não recebe entrada de terceiros. | — |
| `simulation/generator.py` (`random.Random(...)`) | B311 | O simulador **precisa** de PRNG reprodutível por semente (requisito de reprodutibilidade da Fase 1); não é uso criptográfico. | — |
| `scripts/e2e_flow.py` (segundo `subprocess.run`, linha que lê o token da saída do CLI) | B603 | Mesma montagem de argumentos do item anterior: lista fixa `[sys.executable, "-m", "scripts.create_user", ...]`, sem shell e sem entrada de terceiros. *Registrado na Fase 4 · Etapa A (o `# nosec` já existia no código).* | — |
| `routing/strategies.py` (`random.Random(seed)`) | B311 | Amostragem reprodutível por semente das instâncias da comparação de estratégias; sem uso criptográfico. *Registrado na Fase 4 · Etapa A.* | — |
| `scripts/smoke_cloud.py` (`urllib.request.urlopen`) | B310 | A URL passa por `_check_url`, que exige esquema `https` e host; o script é somente leitura e roda no terminal do responsável. *Registrado na Fase 4 · Etapa A.* | Se o script passar a aceitar `http` ou URLs de terceiros. |
| `routing/benchmark.py` (`random.Random(seed)`) | B311 | Amostragem reprodutível por semente das instâncias do benchmark; sem uso criptográfico. | — |

## Ruff (`ruff.toml` e `# noqa`)

| Escopo | Regras | Justificativa |
|---|---|---|
| global | E501, E701, E702, E741 | Estilo de linha larga/compacta já adotado no projeto; sem risco. |
| global | S101 | `assert` ocorre só em testes; o código de produção usa exceções explícitas (os asserts de produção foram substituídos — ver `LEIA-ME.md`). |
| global | B008 | `Depends()` do FastAPI em argumentos é o padrão do framework. |
| global | B905 | `zip()` sem `strict`: os comprimentos são garantidos pelo contexto; `strict=True` mudaria comportamento já validado. |
| `tests/**` | S, B, E402, F841 | Testes usam `assert`, tokens de teste e imports após ajuste de `sys.path`. |
| `scripts/*.py`, `app/streamlit_app.py` | E402 (e S603/S607 nos scripts) | O *bootstrap* de `sys.path` (correção de portabilidade) precisa vir antes dos imports do projeto; ver `tests/test_portabilidade.py`. |
| `database/migrations/versions/*.py` | W291 | Migração já aplicada não é editada só por espaço em docstring. |
| `simulation/**` | F841, E731 | O simulador é versionado e reprodutível por semente; algumas atribuições consomem o gerador aleatório, então não se altera o código só para limpar variáveis. |
| `# noqa: B023` em `ml/evaluation/metrics.py` | B023 | A lambda é consumida na própria iteração do laço. |
| `# noqa: E402` em `ml/semantic/train_eval.py` | E402 | Import tardio intencional. |
| `# noqa: BLE001` em `ml/semantic/validity.py` e `routing/core.py` | — | Fallback opcional: falha registrada/ignorada com comportamento seguro (campo ausente → bloqueio; aquecimento do solver → partida padrão). |

## Alertas **não** suprimidos e pendentes
- Varredura de vulnerabilidades do Trivy (dependências e imagens): não pôde ser executada no ambiente de desenvolvimento (banco de vulnerabilidades inacessível). Roda no CI (job `docker`/`dependencies-and-secrets`); **nenhum resultado foi presumido**.
- Verificação de tipos (mypy 2.4.0): falha com `INTERNAL ERROR` neste código; **não adotada** (registrado no relatório final).
