# LGPD e privacidade — Rede Alimenta IA (Fase 4 · Etapa A)

> **Este documento NÃO é parecer jurídico.** Descreve o que o sistema **realmente faz hoje** (conferido no código, nos modelos de banco e nos testes) e o que seria necessário **antes de qualquer uso real**. Onde há dúvida jurídica, está escrito "a verificar com assessoria jurídica". Nada aqui declara que o projeto "está em conformidade com a LGPD": a conformidade plena depende de base legal, encarregado (DPO), política de privacidade e registro das operações, que **ainda não existem** (seção 12).
> Fontes de verificação citadas: `database/models.py`, `api/auth.py`, `core/hardening.py`, `core/logging_setup.py`, `scripts/create_user.py`, `security/STRIDE.md`, `docs/LICENCAS_DEMONSTRACAO.md`. Tudo que depende da nuvem (Render, Supabase) é marcado como **não verificado neste ambiente**.

## 1. Finalidade

* **Finalidade do sistema:** conectar **doador pessoa jurídica** a **ONG / banco de alimentos pessoa jurídica** para reduzir o desperdício de alimentos (recomendação, proposta, aceite e rota de coleta). Fora do escopo: qualquer tratamento sobre o beneficiário final.
* **Finalidade do tratamento hoje:** **demonstração acadêmica** do Projeto Integrador (FIAP), sem fins comerciais e sem doações reais (`docs/LICENCAS_DEMONSTRACAO.md`). Na interface e no README consta: *"Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais"*.
* Princípios adotados (Lei 13.709/2018, art. 6): **finalidade** (só o fluxo doador → ONG), **necessidade/minimização** (pseudônimo de ONG, sem nome, CNPJ, telefone, e-mail nem endereço) e **segurança** (seção 7).

## 2. Categorias de dados (`data_origin`)

| Categoria | `data_origin` | O que é | Contém dado pessoal? | Estado atual |
|---|---|---|---|---|
| **PUBLIC DATA** | `PUBLIC` | ONGs e bancos de alimentos (IPEA/OSC e RBBA), municípios, população, indicadores territoriais e PAA | **Não**: só pessoa jurídica por **pseudônimo** (`organizations.ong_id`); sem nome, CNPJ, endereço, telefone ou e-mail. `native_id` é o identificador interno da fonte (6 a 8 dígitos, não é CNPJ — conferido em `data/gold/organizations.parquet`, 54.590 registros: 54.398 IPEA/OSC + 192 RBBA) | Carregado no banco (licença **não confirmada**, uso acadêmico — `docs/data/DATA_LICENSES.md`) |
| **SIMULATED DATA** | `SIMULATED` | Doadores, lotes, descrições de lote, desfechos, perfil declarado e frota das ONGs, gerados por `simulation/` (semente e versão) | **Não**: sem Faker, sem pessoa física, sem CPF/CNPJ/telefone/e-mail/URL (`tests/test_simulator.py::test_sem_campos_proibidos` e checagem T2 do `simulation/validation.py`; STRIDE S3). Doador simulado = tipo, porte e município **real**; localização = centroide do município | Carregado no banco, com selo SIMULADO em toda tela |
| **USER PROVIDED DATA** | `USER_ENTERED` | O que um usuário real cadastrar (doador, doação, perfil da ONG) | Poderia conter (texto livre) | **Hoje: 0 registros por desenho.** A carga em nuvem não cria `USER_ENTERED` (`scripts/load_to_cloud.py`), contas `--demo` só operam sobre `SIMULATED` e a doação herda a origem do doador (`api/routers/drafts.py`, `api/routers/donations.py`). Contagem no banco em nuvem **não verificada neste ambiente** |

Observação importante: quem opera uma conta de demonstração pode **digitar texto** (nome de alimento, descrição, observação). Esse texto é gravado numa doação cuja origem é herdada do doador, ou seja, **`SIMULATED`**, e não `USER_ENTERED`. Por isso a regra de segurança é *não digitar dado pessoal* (seção 5, risco R3).

## 3. O que é (e o que não é) dado pessoal no sistema atual

**Não há, por desenho, dado de pessoa física identificada em PUBLIC nem em SIMULATED.** O que existe de "dado do usuário" hoje:

| Dado | Onde fica | É dado pessoal? | Finalidade | Retenção hoje | Como apagar |
|---|---|---|---|---|---|
| **Endereço IP do cliente** | `audit_logs.client_ip` (`String(64)`), gravado por `api/auth.py::audit()` em **todas** as ações auditadas (negativas 401/403/429, `admin.access`, criação/edição de doação, match, rotas, criação de usuário etc.; lista no código: ~30 ações) | **Sim, tratado como pessoal (por prudência; IP identifica ou torna identificável).** Atrás do proxy do Render só vale o último elemento de `X-Forwarded-For` com `TRUST_PROXY_HEADERS=true` (`core/hardening.py::client_ip`). Como o Streamlit chama a API a partir do servidor dele, nas ações feitas pela tela o IP tende a ser o do **serviço frontend**, não o do navegador da pessoa (inferência da arquitetura, **não verificado em produção**); chamadas diretas à API gravam o IP de quem chamou | Segurança, auditoria e detecção de abuso (`auth.rate_limited`) | **Sem prazo e sem rotina automática**: nenhuma rotina apaga `audit_logs` (conferido no código). Fica até o banco ser apagado | Manual, no banco: ver 3.1 |
| Rótulo da conta | `users.label` (`String(80)`) | **Não, desde que não seja nome de pessoa física.** A regra "rótulo não é nome de pessoa" está **só documentada** (docstring de `create_user.py`, descrição do campo na API). **Não há validação em código**: o `create_user.py` não valida o rótulo e a API apenas restringe os caracteres (`^[A-Za-z0-9 ._\-]+$`, 3 a 80). Risco R2 | Identificar a conta (ex.: `admin-defesa`) | Até o projeto/banco ser apagado; `--revoke` só desativa | `DELETE`/anonimização manual da linha de `users` (ver 3.1) |
| Hash do token | `users.token_hash` (SHA-256 de token aleatório de 256 bits) | Não identifica pessoa; é credencial. O token em claro nunca é gravado | Autenticar | Idem; `--revoke` desativa e `--rotate` troca (o anterior é desativado) | Idem |
| Eventos de auditoria | `audit_logs` (`action`, `role`, `user_id`, `resource_*`, `method`, `path`, `outcome`, `status_code`, `detail`) | Indiretamente, por ligar IP + conta + ação + horário. `detail` guarda parâmetros de consulta do ADMIN (`admin.access`), motivo de falha e rótulo na revogação — **nunca o token** (`tests/test_p2_auth.py::test_token_invalido_401_e_nao_grava_token`) | Rastreabilidade | Idem | Idem |
| Texto livre digitado | `donations.raw_text`, `donation_items.produto/description`, nota da ONG (`respond`, 300 car.), `donors.display_name` (opcional, ADMIN, "nome da pessoa jurídica") | **Pode conter dado pessoal inserido por engano** (STRIDE, ativo "Texto livre do doador"). Limites de tamanho e tipos estritos existem; **não há detecção/remoção de dado pessoal** no texto | Descrever o lote | Idem | Manual (ver 3.1) |

### 3.1 Como apagar (procedimento manual; **nada disto foi executado nesta sessão**)

O sistema **não tem** rotina de retenção nem endpoint de exclusão de titular. Procedimentos possíveis, a executar por quem administra o banco (Supabase → SQL Editor), com a conta de dono:

```sql
-- (a) Remover só o IP, mantendo a trilha de auditoria:
UPDATE audit_logs SET client_ip = NULL WHERE client_ip IS NOT NULL;           -- ou com "AND at < <data-limite>"
-- (b) Apagar eventos antigos (prazo de retenção a definir; não há prazo decidido):
DELETE FROM audit_logs WHERE at < <data-limite>;
-- (c) Revogar contas e, se for o caso, remover a linha da conta (sem dependências de FK em audit_logs, que não tem FK para users):
--   python -m scripts.create_user --revoke <rótulo>        -- desativa e audita (user.revoke)
```
Apagar linhas de `users` que sejam referenciadas por `donations.created_by/confirmed_by` ou `match_events.actor_user_id` exige tratar essas FKs antes; **não testado**. O caminho completo e testado de exclusão hoje é **apagar o projeto inteiro** (seção 6).

## 4. Pessoas jurídicas, beneficiários e dados simulados

* **Doadores e ONGs são pessoas jurídicas.** A base pública usa apenas campos de pessoa jurídica no silver/gold; `tests/test_transform.py::test_sem_pessoa_fisica_nem_documento_em_gold` (ausência de colunas de PII) e `quality/data_quality.py` (varredura por valor) tratam isso (STRIDE P4). As colunas de áreas de atuação do gold (incluindo `area_religiao`) descrevem a **entidade**; o banco e o modelo usam apenas `area_assistencia_social` (`database/models.py`, `ml/dataset.py`).
* **Nenhum dado de beneficiário final é tratado** (fora de escopo; indicadores territoriais agregados aparecem só como contexto).
* **Dados simulados não contêm dados pessoais** (sem Faker; testes de ausência de CPF/CNPJ/telefone/e-mail/URL).
* Limite desta garantia: ONGs muito pequenas podem corresponder a poucas pessoas; o sistema não mostra nome ao doador (só pseudônimo após o aceite). Avaliar com assessoria jurídica antes de dados reais.

## 5. Riscos de privacidade identificados

| ID | Risco | Gravidade | Situação |
|---|---|---|---|
| R1 | **IP em `audit_logs` sem retenção definida nem rotina de exclusão** | Média | Aberto. Documentado; decisão de prazo e rotina pendentes |
| R2 | Rótulo de conta pode virar nome de pessoa (regra só documentada, sem validação em código) | Baixa–Média | Aberto. Mitigação possível (validação de rótulo) fica fora desta fase |
| R3 | Dado pessoal digitado por engano em texto livre | Média | Aberto. Mitigado por orientação, limites de tamanho e dados de demonstração; sem detecção automática |
| R4 | **Log de acesso padrão do uvicorn**: o `CMD` das imagens (`docker/Dockerfile.api`) não usa `--no-access-log`; o uvicorn imprime no stdout o endereço remoto **e a query string** de cada requisição (comportamento confirmado em teste local desta sessão com uvicorn 0.54.0). Isso **contradiz a frase "nunca registra IP/query" de `core/logging_setup.py`, que vale só para o logger da aplicação**. Atrás do proxy do Render o endereço visto tende a ser o do proxy, **não verificado em produção**; a API não recebe token em query string (usa `Authorization`) | Média | Aberto. A correção (desligar o log de acesso) exige alterar `Dockerfile`/`render.yaml`, o que esta fase proíbe; registrado como pendência |
| R5 | A plataforma de hospedagem pode registrar IP e metadados de acesso por conta própria (Render, Supabase, GitHub) | Média | Fora do controle do projeto; **não verificado neste ambiente** |
| R6 | Crescimento de `audit_logs` sob ataque (rotas negadas gravam linha por desenho) | Baixa | Registrado em STRIDE (P4A-3, P4B-4); o rate limit global (Etapa B) limita a taxa por IP, mas não impõe retenção nem teto total de `audit_logs` |

## 6. Minimização, retenção e exclusão

* **Minimização:** ONG por pseudônimo, sem contato nem endereço; localização por **centroide do município** para 54.400 das 54.590 ONGs (`MUNICIPALITY_CENTROID`) e coordenada exata apenas para 190 bancos de alimentos já públicos (execução desta sessão sobre `data/gold/organizations.parquet`); doador simulado sem CNPJ, nome ou endereço; sem cookies de rastreamento; sem mapa-base de terceiros nem chave (`app/page_dashboard.py`, STRIDE P3C-7).
* **Retenção (demonstração):** dados e contas existem **até a apresentação**; depois, obrigatoriamente: revogar tokens, decidir sobre as licenças e **apagar** o banco e os serviços (`docs/LICENCAS_DEMONSTRACAO.md`, `docs/DEPLOY.md` passo 9).
* **Retenção (uso real):** **a definir** — não existe política de prazos hoje.
* **Exclusão — procedimento real após a apresentação:**
  1. `python -m scripts.create_user --revoke <rótulo>` para cada conta (`admin-defesa`, `demo-doador`, `demo-ong` etc.; grava `user.revoke`);
  2. decidir o destino dos dados de licença não confirmada (obter licença ou remover);
  3. **Supabase** → Project Settings → General → *Delete project* (apaga o banco inteiro, inclusive `audit_logs` e IPs);
  4. **Render** → apagar os serviços `rede-alimenta-api` e `rede-alimenta-frontend`;
  5. repositório GitHub: o histórico não contém segredos nem dados de pessoas (gitleaks do histórico: 0 achados em `security/reports/depois/`); logs do GitHub Actions seguem a política da plataforma.
  Dados em backups/snapshots da plataforma **não verificados** (não há backup gerenciado configurado pelo projeto).

## 7. Segurança — controles reais (com a prova no repositório)

| Controle | Onde está | Prova |
|---|---|---|
| Token com 256 bits, só o **hash SHA-256** no banco, exibido uma vez | `api/auth.py`, `scripts/create_user.py` | `tests/test_p2_auth.py` |
| Expiração opcional do token e revogação por rótulo | `users.expires_at`, `--expires-in-hours`, `--revoke` | `tests/test_p3d_banco_producao.py::test_token_expirado_e_recusado_*` (expiração), `tests/test_p3c_observabilidade_seguranca.py::test_revogar_token_por_rotulo` (revogação) |
| Resposta de autenticação genérica (não revela se o token existe/expirou) | `api/auth.py` | `test_token_expirado_resposta_generica_*` |
| Limite de **tentativas inválidas** por IP (20 em 300 s ⇒ 429), **em memória, por instância**; só em `production` | `core/hardening.py::AuthFailureLimiter` | `test_limitador_*` (`tests/test_p3d_banco_producao.py`, `tests/test_p3d_producao.py`) |
| **RLS** em todas as tabelas + `REVOKE` de `anon`/`authenticated` (API REST automática do Supabase sem acesso) | migration `0004` | `test_rls_em_todas_as_tabelas`; no Supabase real, conferir pelo passo 4 do `docs/DEPLOY.md` (**não verificado neste ambiente**) |
| **SSL** obrigatório em banco remoto em `production` (`sslmode=require`: criptografa, **não verifica o servidor**) | `core/settings.py::exigir_ssl_se_remoto` | `test_production_exige_ssl_*` |
| **CORS** restrito a `CORS_ALLOW_ORIGINS` (sem curinga) e cabeçalhos de segurança (CSP, HSTS, `nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store` etc.) | `core/hardening.py`, `api/main.py` | `test_cors_sem_curinga`, `test_production_desliga_docs_e_poe_cabecalhos` |
| `/docs`, `/redoc`, `/openapi.json` desligados em produção | `api/main.py` | idem |
| **Auditoria** de 401/403/429 e de acessos do ADMIN (`admin.access`), sem token | `api/auth.py` | `test_acesso_admin_e_auditado_sem_token` |
| **Visibilidade por perfil** aplicada na API (DONOR não vê scores/ranking/saída da IA) | `api/schemas_views.py` | `tests/test_p3a_visibilidade_perfil.py`, `tests/test_p3b_campos_ia_proibidos.py`, `tests/test_p4a_openapi.py` |
| **Sanitização de texto na interface**: texto digitado por terceiros é escapado antes de ir ao Markdown (sem imagem/link externo, sem HTML) | `app/ui_common.py::esc/limpar` | `test_nome_de_alimento_malicioso_*`, `test_esc_neutraliza_*`. **Na API** o texto é validado por tipo e tamanho, mas **não é sanitizado nem filtrado para dado pessoal** |
| Segredos só em variáveis de ambiente; `render.yaml` sem valores (`sync: false`); gitleaks no CI | `core/settings.py`, `render.yaml`, `.github/workflows/ci.yml` | gitleaks local 0 achados (`security/reports/depois/`); CI **a confirmar no GitHub** |

## 8. Logs: o que é registrado e o que nunca é

* **Logger da aplicação (`api.request`, JSON em produção):** método, caminho **sem query string**, status e duração, `request_id`. Nunca cabeçalhos, corpo, token nem IP (`core/logging_setup.py`). O teste `tests/test_p3c_observabilidade_seguranca.py::test_log_de_requisicao_nao_vaza_token_nem_query` cobre token e query string; a ausência de IP vem do código do middleware (o teste não a verifica).
* **Eventos de negócio:** só identificadores técnicos e contagens.
* **`audit_logs` (banco):** ver seção 3 — **inclui o IP**; nunca o token.
* **NÃO coberto por essas garantias:** log de acesso padrão do uvicorn (R4) e logs da plataforma (R5).
* **Nunca registrados:** token, senha, `DATABASE_URL` (`scripts/load_to_cloud.py` mascara o host e redige erros; `tests/test_p3d_producao.py::test_mask_e_redact`).

## 9. Direitos do titular (art. 18) — **evolução futura**

Hoje não há cadastro de pessoas, portanto não há titular identificado nem canal de atendimento. **Nada abaixo existe ainda**; descreve o que seria feito quando houver cadastro real:

| Direito (art. 18) | Como seria atendido | Hoje |
|---|---|---|
| Confirmação e acesso | Tela/endpoint "meus dados" para a conta autenticada | **Não existe** |
| Correção | Edição do próprio cadastro | Não existe (só o ADMIN edita) |
| Anonimização, bloqueio ou eliminação | Rotina de exclusão por conta, com tratamento de FKs e de `audit_logs` | **Não existe**; só procedimento manual (3.1) |
| Portabilidade | Exportação estruturada dos dados da conta | Não existe |
| Informação sobre compartilhamento | Política de privacidade com operadores e transferência internacional | Não existe |
| Revogação do consentimento / oposição | Depende da **base legal escolhida** (a definir) | Não se aplica ainda |
| Atendimento ao titular | Canal do encarregado (DPO) | **Sem encarregado** |

## 10. Operadores, suboperadores e transferência internacional

| Entidade | Papel | Dados que toca | Localização informada |
|---|---|---|---|
| **Render** | hospedagem da API e do frontend (planos gratuitos) | tráfego HTTP (IP de acesso, nos logs da plataforma), `audit_logs` não, variáveis de ambiente | EUA (região Oregon, segundo o relatório de deploy do projeto) |
| **Supabase** | PostgreSQL gerenciado (plano gratuito) | todo o banco, inclusive `audit_logs` com IP | EUA (região Virginia, idem) |
| **GitHub** | repositório e CI | código, segredos do CI (nenhum dado de pessoas) | EUA |

**Risco/limitação a tratar antes de qualquer uso real:** os servidores estão nos **EUA** ⇒ há **transferência internacional** de dados (LGPD, art. 33), inclusive do IP em `audit_logs`. Não há contrato/cláusulas-padrão, avaliação de adequação nem escolha de região por requisito legal. **Fora de escopo desta fase; a verificar com assessoria jurídica.** Região exata e termos de cada plataforma **não foram verificados** neste ambiente.

## 11. Responsabilidades e resposta a incidente

**Responsabilidades (demonstração):** a **equipe** opera a demonstração e responde por tokens, banco e serviços; o **professor/instituição** é destinatário acadêmico do trabalho; os **usuários da demonstração** (banca e colegas) devem usar apenas contas de demonstração e **não digitar dado pessoal**. A definição formal de controlador, operador e encarregado **não foi feita** (a verificar com assessoria jurídica/FIAP).

**Plano de resposta a incidente (passos concretos, a executar por quem opera o projeto):**
1. **Conter:** revogar os tokens afetados — `python -m scripts.create_user --revoke <rótulo>` (grava `user.revoke`); se houver dúvida sobre vários, revogar todos e recriar com `--expires-in-hours`.
2. **Isolar:** no Render, suspender o serviço `rede-alimenta-api` (e o frontend, se necessário).
3. **Trocar a credencial do banco:** Supabase → Project Settings → Database → redefinir a senha; atualizar `DATABASE_URL` no painel do Render (digitada por você, nunca no chat); reiniciar a API.
4. **Investigar:** consultar `audit_logs` (`auth.invalid_token`, `auth.rate_limited`, `authz.*`, `admin.access`) e os logs do Render; guardar evidências.
5. **Recuperar:** gerar novos tokens e conferir `smoke_cloud`.
6. **Encerrar de vez, se for o caso:** apagar os serviços e o projeto Supabase (seção 6).
7. **Comunicar:** se houver dado pessoal envolvido (hoje, em tese, o IP em `audit_logs`), avaliar com assessoria jurídica a comunicação à ANPD e aos titulares (art. 48) — **processo não definido**.

## 12. Limitações honestas

* **Não é parecer jurídico** e não substitui avaliação por advogado.
* **Base legal não definida** (art. 7), **sem encarregado/DPO** (art. 41), **sem política de privacidade**, **sem registro das operações** (art. 37) nem relatório de impacto (art. 38). Tudo isso precisa existir **antes** de dados reais.
* **Sem política de retenção**; o IP em `audit_logs` permanece até o banco ser apagado (R1). O log de acesso do uvicorn imprime IP e query string (R4).
* **Direitos do titular, exclusão por conta e portabilidade não existem** (seção 9).
* Transferência internacional (EUA) sem salvaguardas definidas (seção 10).
* Verificações que dependem de Render, Supabase, GitHub ou Docker (RLS no Supabase real, logs da plataforma, contagem de `USER_ENTERED` no banco em nuvem) **não foram feitas neste ambiente**.
