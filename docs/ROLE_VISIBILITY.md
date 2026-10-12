# Visibilidade por perfil e contas/tokens (Fase 3 · Parte 1 · Etapa A)

A restrição é aplicada **na API** (não só na tela): cada perfil tem seu próprio `response_model` (`api/schemas_views.py`), com união discriminada pelo campo `perfil`.
O `response_model` também **descarta chaves extras**, como defesa em profundidade se um construtor de view passar campos a mais.

## 1. O que cada perfil vê
| Recurso | DONOR | ORG | ADMIN |
|---|---|---|---|
| Doação (`/donations…`) | só as próprias; itens e status; situação em linguagem simples | — (vê a doação **dentro** da proposta) | todas, com `parser_suggestion` e `weight_basis` |
| Match (`/matches…`) | `DonorMatchView`: `status`, `situacao`, `ong_aceita` (pseudônimo, **só após o aceite**) | `OrgMatchView`: a doação (itens, resumo, **análise textual sem scores**), a própria candidatura (distância, tempos, folga) e se aguarda resposta | `AdminMatchView`: ranking completo, scores, elegibilidade, pesos, latências |
| Eventos (`/matches/{id}/events`) | tipo, estado e tempos | só os próprios, só `nota` e prazo | completos (ONG, posição, detalhes) |
| `GET /matches/{id}/ranking` | 403 | 403 | sim (auditado) |
| `POST /predictions`, `GET /model/info` | 403 | 403 | sim (auditado) |
| `/organizations` | identificação pública mínima (`PUBLICA`) | registro completo **só da própria ONG**; demais `PUBLICA` | completo (`COMPLETA`) |
| `/me` | identidade, escopo de dados (`SIMULATED` para contas demo) | idem | `ALL` |

Nunca saem para DONOR/ORG: `ML_SCORE`, `BUSINESS_RULE_SCORE`, `DISTANCE_SCORE`, `FINAL_SCORE`, componentes das regras, pesos, contagens de elegibilidade,
`ranking`, `posicao`/`current_position`, `current_org` (antes do aceite), `org_id` de ONGs não escolhidas, `engine_version`, `model_version`, latências.
Para o doador a plataforma não mostra nome de ONG: a base só tem **pseudônimo** (`ong_id`); exibe-se o pseudônimo após o aceite.

## 2. Auditoria do acesso ADMIN
Cada acesso do ADMIN a dados restritos grava em `audit_logs` a ação `admin.access` (recurso: `match`, `match.ranking`, `match.events`, `model_info`, `predictions`, `donations`, `matches`, `metrics`, `batch_compare`), com perfil, caminho e parâmetros de consulta — **nunca o token**.
Negativas de perfil ficam como `authz.role_denied` (403) e de dono como `authz.owner_denied`.

## 3. Criação de contas e tokens por perfil
O token é gerado com `secrets.token_urlsafe(32)`, mostrado **uma vez**; no banco fica só o SHA-256. Contas `--demo` operam **apenas** sobre dados `SIMULATED`.
```bash
# ADMIN
python -m scripts.create_user --role ADMIN --label admin-local
# DONOR de demonstração (doador SIMULATED do simulador)
python -m scripts.create_user --role DONOR --label conta-doador-demo --donor-id <uuid-do-doador> --demo
# ORG de demonstração (ONG real de fonte pública, perfil SIMULADO)
python -m scripts.create_user --role ORG --label conta-ong-demo --org-id <uuid-da-ong> --demo
# via API (ADMIN): POST /api/v1/admin/users {"role": "...", "label": "...", "donor_id"/"organization_id": "...", "is_demo": true}
```
Rótulos **não** podem ser nome de pessoa física. Contas reais (`USER_ENTERED`): DONOR de doador real; ORG exige organização `REGISTERED`.

### Tokens predefinidos no CI (um por perfil)
O CI gera `E2E_ADMIN_TOKEN`, `E2E_DONOR_TOKEN` e `E2E_ORG_TOKEN` (mascarados no log) e o e2e cria as contas **sem imprimir o token**:
```bash
export E2E_ADMIN_TOKEN="rai_$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m scripts.create_user --role ADMIN --label admin-ci --token-env E2E_ADMIN_TOKEN
```
O formato exigido é `rai_` + 40 ou mais caracteres; token repetido é recusado. Os tokens ficam só no processo do CI que roda `scripts.e2e_flow`
(a API guarda apenas hashes e os contêineres **não** recebem tokens). Nunca coloque valores de token em `.env`, `.env.example` ou no repositório.

## 4. Como cada perfil é verificado
* `tests/test_p3a_visibilidade_perfil.py`: DONOR e ORG sem chaves proibidas (inclusive em listas e eventos), 403 nas rotas ADMIN, `admin.access` auditado sem token, `response_model` descartando extras, organizações `PUBLICA`/`COMPLETA`, `/me`.
* `scripts.e2e_flow` (HTTP real): tokens por perfil; confere que doador e ONG não recebem scores/ranking e recebem 403 nas rotas ADMIN; conta os `admin.access`.

## 5. Limitações
Token estático sem expiração/rotação/escopos, sem TLS e sem rate limit nesta fase (`security/STRIDE.md`: P2-3, P2-6, P2B-19, P2B-20). Localização exata e contato do doador para a ONG só após cadastro real (P2B-7) — pendente.
