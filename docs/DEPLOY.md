# Guia de publicação em nuvem — Rede Alimenta IA (Etapa B)

> **Para quem é:** quem vai publicar pela primeira vez. Cada passo diz **o que fazer**, **onde clicar** e **como saber que deu certo**.
> **Regra de ouro:** senhas, strings de conexão e tokens são **digitados por você**, direto no painel ou no terminal. **Nunca** os cole em chat, e-mail, issue, commit ou arquivo do repositório. O repositório não contém nenhum segredo.
> **Estado (14/10/2026, Fase 4 · Etapa A):** a demonstração **foi publicada pelo responsável** — API `https://rede-alimenta-api.onrender.com` e frontend `https://rede-alimenta-frontend.onrender.com` (Render, plano gratuito), banco no Supabase (Session pooler, SSL, RLS), `smoke_cloud` com tudo `[OK]`, segundo o relatório de deploy do projeto (**não verificado neste ambiente**). Os passos abaixo seguem como o procedimento de (re)publicação. Riscos residuais e o que NÃO está mitigado: `docs/SEGURANCA_FINAL.md` e `security/STRIDE.md` §16.

## Visão geral
```
Navegador ──► Frontend (Streamlit, Render) ──► API (FastAPI, Render) ──► PostgreSQL (Supabase)
```
* O **Supabase** é usado **só como PostgreSQL gerenciado**. A **única porta de entrada dos dados é a nossa API**; por isso a migration `0004` liga o RLS em todas as tabelas e revoga os papéis `anon`/`authenticated` (a API REST automática do Supabase fica sem acesso).
* O **Render** roda os dois contêineres (plano gratuito) a partir do `render.yaml`. O TLS (https) é feito pelo Render.
* Dados: **PÚBLICO** (ONGs, municípios, indicadores) e **SIMULADO** (doadores, lotes, desfechos). Nada é inventado como real. Aviso em todas as telas: *"Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais"*. Licenças: `docs/LICENCAS_DEMONSTRACAO.md`.

## O que você precisa antes
1. Conta no GitHub com este repositório (e o CI passando) · conta no [Supabase](https://supabase.com) · conta no [Render](https://render.com) ligada ao GitHub.
2. Python 3.10+ na sua máquina (Windows/PowerShell) e o projeto instalado: `pip install -r requirements.txt` (a carga usa `data/gold` e `data/simulated/main`, que ficam **fora** do Git — gere-os pelos comandos do README ou copie a pasta `data/` da sua máquina).
3. Estimativa de tamanho (não toca em banco algum): `python -m scripts.load_to_cloud --estimate` → cerca de **133 MB** para a carga completa; o limite gratuito do Supabase é **500 MB por projeto**.

## Passo 1 — Criar o projeto no Supabase
1. Painel do Supabase → **New project**. Escolha a organização, um nome (ex.: `rede-alimenta`), a **região mais próxima** (ex.: South America – São Paulo) e o plano **Free**.
2. Em **Database password**, **digite você mesmo uma senha forte** (letras, números, `-` e `_` evitam problemas na URL) e guarde-a em um gerenciador de senhas. Não a envie a ninguém.
3. Aguarde o projeto ficar verde ("Healthy"). *Como saber que deu certo:* o painel abre o Table Editor vazio.

## Passo 2 — Copiar a string do pooler em **modo sessão**
1. No projeto: botão **Connect** (topo) → aba **Connection string** → método **Session pooler** (porta **5432**, usuário `postgres.<ref-do-projeto>`).
2. Por quê: o *Session pooler* funciona em **IPv4** (a conexão direta do Supabase é só IPv6 no plano gratuito e o Render gratuito/sua rede podem não alcançá-la) e aceita *prepared statements*. **Não use o modo transação (porta 6543)**: ele não suporta *prepared statements*.
3. A string tem o formato `postgresql://postgres.<ref>:[SUA-SENHA]@<host>.pooler.supabase.com:5432/postgres`. Substitua `[SUA-SENHA]` pela senha do passo 1 **apenas no seu terminal**, e acrescente no final `?sslmode=require`. (O código converte `postgresql://` para o driver correto sozinho.)

## Passo 3 — Aplicar migrations e carregar os dados (no seu PowerShell)
```powershell
cd C:\caminho\para\o\projeto
# digite a string quando o prompt pedir (a entrada não aparece na tela e não vai para o histórico)
$s = Read-Host "Cole a DATABASE_URL (não aparece)" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $s).Password

python -m scripts.load_to_cloud                     # 1) SÓ MOSTRA O PLANO: host mascarado, nada é gravado
python -m scripts.load_to_cloud --confirm-cloud     # 2) aplica `alembic upgrade head` e carrega PÚBLICO + SIMULADO

Remove-Item Env:DATABASE_URL                        # ao terminar, apaga a variável desta janela
```
* O script **nunca imprime a URL**: mostra só o host mascarado (`aws***.com`), o banco, as **contagens por origem** e o tamanho do banco.
* **Idempotente:** pode repetir; não duplica nada. Padrão = carrega **tudo** (decisão do grupo com o professor). `--sim-tag` escolhe a carga do simulador (padrão `main`).
* *Como saber que deu certo:* o JSON final traz `contagens_depois` com ONGs (≈54 590), municípios (5 571), indicadores, doadores e doações simulados, e `tamanho_do_banco_mb` bem abaixo de 500.

## Passo 4 — Conferir o RLS
No Supabase: **SQL Editor** → cole e execute:
```sql
select c.relname as tabela, c.relrowsecurity as rls_ligado
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by 1;
```
*Como saber que deu certo:* **todas** as linhas com `rls_ligado = true`. No **Table Editor** o Supabase mostra "RLS enabled" em cada tabela, e o aviso de "tabelas sem RLS" do **Security Advisor** (Advisors) não lista nenhuma.

## Passo 5 — Criar os serviços no Render
1. Painel do Render → **New** → **Blueprint** → escolha este repositório (branch `main`). O Render lê o `render.yaml` e propõe dois serviços: `rede-alimenta-api` e `rede-alimenta-frontend` (plano **Free**).
2. O Render pedirá os valores das variáveis marcadas como segredo/pendentes (passo 6). Se preferir, crie o Blueprint e preencha depois em **Environment** de cada serviço.
3. Faça o deploy. O primeiro build leva alguns minutos. *Como saber que deu certo:* os dois serviços ficam **Live**; a API passa no *health check* `/ready` (só responde 200 com o banco acessível).

## Passo 6 — Variáveis de ambiente (digitadas por você)
| Serviço | Variável | O que colocar |
|---|---|---|
| API | `DATABASE_URL` | a string do passo 2, **com a sua senha e `?sslmode=require`** (digite no painel) |
| API | `CORS_ALLOW_ORIGINS` | a URL pública do **frontend** (`https://rede-alimenta-frontend….onrender.com`, sem `/` no final) |
| API | `APP_ENV`, `TRUST_PROXY_HEADERS`, limites | já vêm no `render.yaml` (`production`, `true`, …) |
| Frontend | `API_BASE_URL` | a URL pública da **API** (`https://rede-alimenta-api….onrender.com`) |
| Frontend | `API_WAKE_MAX_S` | já vem (`120`): o frontend tenta de novo por até 2 min e avisa "acordando o servidor" |

Ordem prática: crie primeiro (o Render mostra as URLs assim que os serviços existem), depois edite `CORS_ALLOW_ORIGINS` (API) e `API_BASE_URL` (frontend) com as URLs e salve — o serviço reinicia sozinho.
Em `production` a API **recusa subir** com banco remoto sem SSL, desliga `/docs`, `/redoc` e `/openapi.json`, aplica cabeçalhos de segurança e limita tentativas de autenticação inválidas por IP (20 em 5 min, em memória).

## Passo 7 — Token ADMIN da defesa e contas de demonstração
Os tokens **não existem no repositório**: você os gera, e o terminal mostra cada um **uma única vez** (só o hash vai ao banco). Com a `DATABASE_URL` do passo 3 definida na janela:
```powershell
# ADMIN com validade de 24 h (até 720 h); anote o token no seu gerenciador de senhas
python -m scripts.create_user --role ADMIN --label admin-defesa --expires-in-hours 24
# contas de demonstração: liste ids (doadores SIMULADOS / ONGs públicas) e crie uma conta por perfil, com validade
python -m scripts.create_user --list donors --limit 5
python -m scripts.create_user --list orgs --limit 5
python -m scripts.create_user --role DONOR --label demo-doador --donor-id <ID-LISTADO> --demo --expires-in-hours 72
python -m scripts.create_user --role ORG --label demo-ong --org-id <ID-LISTADO> --demo --expires-in-hours 72
```
*Como saber que deu certo:* no frontend, cole o token na barra lateral e a tela do ADMIN abre; o aviso acadêmico aparece no topo.

### Rotação de token (trocar o token de uma conta)
Use quando um token foi exposto, está perto de expirar ou precisa ser renovado. Com a `DATABASE_URL` do passo 3 definida na janela:
```powershell
python -m scripts.create_user --rotate admin-defesa --expires-in-hours 24
```
* Em **uma transação**: cria um usuário novo com o **mesmo perfil, vínculo (doador/ONG) e marca `--demo`** da conta ativa com esse rótulo, **desativa a anterior** e grava a auditoria `user.rotate` (rótulo e perfil; nunca o token). O **novo token aparece uma única vez**; o antigo nunca é mostrado e passa a dar 401 na hora.
* **Exige exatamente uma conta ativa com o rótulo.** Se não houver nenhuma, ou houver mais de uma (rótulo ambíguo), o comando falha com mensagem clara e **nada é alterado** (nesse caso use `--revoke <rótulo>` e crie as contas de novo).
* A **validade não é herdada**: sem `--expires-in-hours` o token novo não expira. Se algo falhar no meio, a transação é desfeita e o token antigo continua valendo.
* Depois de rotacionar, entregue o novo token a quem usa a conta e confirme no frontend. Para o ADMIN, o painel "Segurança e sistema" mostra as contas ativas por perfil.

### Ajustar o rate limit (opcional)
O limite global já vem **ligado, com padrões generosos**, sem nenhuma variável: **1.200 requisições/min por token**, **240/min por IP quando não há token válido** e **teto de 6.000/min por IP** (janela de 60 s). `/health` e `/ready` (health checks do Render) nunca são limitados. O número por token cobre mais de 30 sessões abertas com o mesmo token (as telas do doador e da ONG atualizam a cada 5 s; ≈ 36 chamadas/min por sessão é **estimativa de projeto**, não medição). Os padrões ficam no código porque esta fase não altera o `render.yaml`. Para mudar, adicione em **Environment** do serviço da API: `RATE_LIMIT_TOKEN_MAX`, `RATE_LIMIT_IP_MAX`, `RATE_LIMIT_IP_CEILING_MAX`, `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_MAX_KEYS` (inteiros) ou `RATE_LIMIT_ENABLED=false` para desligar. É **por instância e em memória** (reiniciar zera); ao escalar para várias instâncias, trocar por Redis ou por um gateway.

## Passo 8 — Teste pós-deploy (somente leitura)
```powershell
python -m scripts.smoke_cloud --api https://SUA-API.onrender.com --frontend https://SEU-FRONT.onrender.com --acordar
```
Verifica `/health` e `/ready` da API e do frontend, `/docs` desabilitado (404), rotas ADMIN recusando acesso sem token (401/403) e — se você definir `SMOKE_DONOR_TOKEN` / `SMOKE_ORG_TOKEN` no ambiente — que doador e ONG **não recebem campos de IA**. Não grava dados e não imprime tokens. `--acordar` repete as chamadas com espera crescente por cerca de 2 minutos.
Depois, faça o roteiro manual da defesa: entrar como ADMIN → Overview, Mapa, IA, Segurança; entrar como DOADOR e ONG e confirmar que não veem scores.

## Passo 9 — Depois da defesa
1. **Revogue os tokens:** `python -m scripts.create_user --revoke admin-defesa` (repita para cada rótulo de demonstração). Tokens com `--expires-in-hours` também deixam de valer sozinhos.
2. Decida o destino dos dados conforme `docs/LICENCAS_DEMONSTRACAO.md`: **obter licença ou remover** os conjuntos não confirmados e **apagar o banco em nuvem** (Supabase → Project Settings → General → *Delete project*) e os serviços do Render.

## O que fazer se der erro
| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `banco em nuvem pausado ou inacessível` | o Supabase gratuito **pausa** projetos sem atividade por ~7 dias | Painel do Supabase → o projeto → **Resume project**; espere ficar "Healthy" e repita |
| `banco remoto sem SSL` | faltou `?sslmode=require` | acrescente ao fim da `DATABASE_URL` |
| `password authentication failed` / `Tenant or user not found` | senha errada ou usuário sem o sufixo `.<ref>` | copie de novo a string do **Session pooler**; confira o usuário `postgres.<ref>` |
| `Network is unreachable` / timeout | usou a conexão **direta** (IPv6) | use o **Session pooler** (porta 5432) |
| `prepared statement … does not exist` | usou a porta **6543** (modo transação) | troque para a porta **5432** (modo sessão) |
| Serviço do Render "Deploy failed" | variável faltando ou `DATABASE_URL` inválida | veja **Logs** do serviço (as mensagens não contêm segredos) e corrija em **Environment** |
| Tela do frontend mostra "Acordando o servidor…" | plano gratuito hiberna após 15 min sem uso | aguarde ~1 min; antes da defesa, rode `smoke_cloud --acordar` |
| 429 "muitas tentativas" | muitas tentativas de token inválido do mesmo IP | aguarde 5 min (a janela esvazia) |
| 429 "muitas requisições" | passou do limite global (1.200/min por token; 240/min por IP sem token) | aguarde o tempo do cabeçalho `Retry-After` (≤ 60 s); se for uso legítimo, veja "Ajustar o rate limit" no Passo 7 |
| 401 com token certo | token expirado ou revogado | gere outro com `create_user` |
| A carga estoura o limite | estimativa acima de 80% do plano | a carga é recusada (código 3); use uma tag menor em `--sim-tag` |

## Antes da defesa (checklist de 10 minutos)
1. Supabase **Healthy** (retome se estiver pausado). 2. Rode `smoke_cloud --acordar`. 3. Abra o frontend, entre como ADMIN e navegue pelas telas. 4. Tenha o token ADMIN à mão (gerenciador de senhas) e confirme que ainda não expirou. 5. Se o Wi-Fi do local bloquear alguma porta, use o celular como roteador.

## Limitações conhecidas (registradas em `security/STRIDE.md`)
TLS é da plataforma; os limites (tentativas inválidas e **rate limit global por token/IP**) são **por instância e em memória** (reinicia → zera; não são distribuídos); sem rotação **automática** de tokens (há expiração opcional, revogação e **rotação manual** — Passo 7). O plano gratuito hiberna, o banco gratuito pausa, e não há backup gerenciado. O log de acesso padrão do uvicorn (IP e query string) não está desligado no `CMD` da imagem. Consolidação: `docs/SEGURANCA_FINAL.md`; privacidade: `docs/LGPD.md`.

## Fontes oficiais consultadas (2026-10-13) e o que delas foi usado
* Supabase — conexão com o Postgres (pooler em modo sessão, IPv4, porta 5432 / transação 6543 sem *prepared statements*): <https://supabase.com/docs/guides/database/connecting-to-postgres>
* Supabase — limites do plano gratuito (500 MB por projeto) e pausa por inatividade: <https://supabase.com/docs/guides/platform/billing-on-supabase> · <https://supabase.com/docs/guides/deployment/going-into-prod>
* Supabase — RLS: <https://supabase.com/docs/guides/database/postgres/row-level-security>
* Render — Blueprint (`render.yaml`: `runtime: docker`, `healthCheckPath`, `autoDeployTrigger`, `sync: false`): <https://render.com/docs/blueprint-spec>
* Render — plano gratuito (hibernação após 15 min, ~1 min para acordar, 750 h/mês) e variável `PORT`: <https://render.com/docs/free> · <https://render.com/docs/web-services>
> Planos, limites e telas mudam. Se algo do painel estiver diferente do descrito aqui, vale a documentação oficial acima.

## Pendências do responsável após a publicação
* Gerar um novo token ADMIN na manhã da apresentação (o `admin-defesa` tem validade de 24 h) e criar as contas `--demo` da ONG que o ranking escolher (checklist da defesa no relatório de deploy do projeto).
* Baixar os JSON do Trivy de imagem do job `docker` do CI para `security/reports/ci/antes|depois/` (o painel só conta "4 → 0" com os dois lados).
* Fazer o push dos arquivos novos e alterados (esta fase não faz commit nem push).
* Depois da defesa: revogar tokens (`--revoke`), aplicar a decisão de `docs/LICENCAS_DEMONSTRACAO.md`, apagar o projeto Supabase e os serviços do Render (`docs/LGPD.md` §6 e §11).
