# Pitch final — Rede Alimenta IA

> Roteiro de defesa. Todo número tem origem indicada; **nada simulado é apresentado como real**. O que depende de CI ou da nuvem está marcado. Hoje: **"Nenhuma doação real registrada."**

**Duração sugerida:** 5 minutos · **Critérios da banca:** Impacto Social 30% · Qualidade da IA 30% · DevSecOps 20% · Engenharia & Defesa 20%.
**Demonstração no ar:** frontend https://rede-alimenta-frontend.onrender.com · API https://rede-alimenta-api.onrender.com (plano gratuito: **acorde os serviços ~2 min antes**, o primeiro acesso leva cerca de 1 minuto; disponibilidade **não verificada neste ambiente**).

## 1. Problema e ideia (30 s) — Impacto social
* Alimento bom é descartado enquanto ONGs precisam de doações; o gargalo é **encontrar a ONG certa, a tempo, com capacidade, refrigeração e rota**.
* A Rede Alimenta IA conecta **doador → ONG** (a entrega ao beneficiário final está fora do escopo).

## 2. Os três tipos de impacto — nunca misturados (45 s)
| Tipo | O que é | Estado hoje |
|---|---|---|
| 🟦 **Histórico observado (dados públicos)** | ONGs e bancos de alimentos reais (54.590 por pseudônimo: IPEA/OSC e RBBA), 5.571 municípios, indicadores IBGE/PAA. Mostra **onde existe a rede**, não o que a plataforma salvou | Licença em revisão; uso acadêmico. Totais do PAA: ler da tela (selo PÚBLICO); **este roteiro não repete números não conferidos** |
| 🟧 **Impacto SIMULADO** | kg ofertados/coletados e refeições (kg ÷ 0,4, **premissa da equipe**) calculados sobre doações **geradas por simulador** (semente + versão) | Selo visível em toda tela; **não é resultado real** |
| 🟩 **Impacto de doações reais** | entradas reais na plataforma | **Nenhum.** Dizer isso é parte da honestidade do projeto |

## 3. IA (90 s) — Qualidade da IA
* Motor: elegibilidade eliminatória → 15 candidatas mais próximas → **ML + regras + distância** (`0,5·ML + 0,3·regras + 0,2·distância`, pesos são premissas da equipe) → ranking explicado.
* **Sobre dados simulados** (teste, 134 mil pares; `docs/MODEL_CARD.md`): **MRR 0,695** (HistGradientBoosting) contra 0,465 da *ONG mais próxima* e 0,541 da *regra*; **Top-1 54,6%** contra 27,2% e 35,3%; ROC-AUC 0,798, PR-AUC 0,459, F1 0,503.
* Parser de texto: acurácia de categoria 96,1% (texto simulado visto) e 95,6% (família nunca vista) — **não há conjunto rotulado manualmente**; sugestões sempre confirmadas pelo doador.
* **O que dizemos antes que perguntem:** circularidade do simulador; lote misto desconhecido; ONGs por pseudônimo; o modelo **não** foi validado com dados reais.
* **Demo:** doador monta a doação com itens e validades diferentes → match.

## 4. Produto e demo ao vivo com 3 perfis (75 s) — Engenharia
1. **Doador** (conta demo): cria a doação, envia e acompanha **só a situação** (sem scores).
2. **ONG** (conta demo): recebe a proposta com a "Análise da IA" em texto e **aceita ou recusa**; recusa/expiração leva à próxima candidata.
3. **ADMIN** (token criado na manhã da defesa): dashboard com selos, ranking, scores, aviso de lote misto e auditoria.
* A visibilidade por perfil é aplicada **na API**, não na tela, e há testes para isso (`tests/test_p3a_visibilidade_perfil.py`, `tests/test_p4a_openapi.py`).
* Rotas de coleta com OR-Tools comparadas ao vizinho mais próximo; distâncias **estimadas**, não viárias.

## 5. DevSecOps como argumento (75 s)
* **Executado na entrega (14/10/2026, ambiente de desenvolvimento):** 311 testes passaram, 0 falharam; Ruff limpo; Bandit 0 achados (11.683 linhas; 10 supressões justificadas e registradas); pip-audit sem vulnerabilidades conhecidas em `requirements-dev.txt`. Fonte: `docs/SEGURANCA_FINAL.md`.
* **Confirmado pelo CI (GitHub Actions), não por esta execução:** Trivy (dependências, configuração e imagem), gitleaks, build Docker e fluxo ponta a ponta via Compose. O "4 HIGH → 0" da imagem é afirmação do CI; os JSON antes/depois ainda não estão versionados.
* **Controles:** token de 256 bits com só o hash no banco; perfis e posse do recurso; RLS em todas as tabelas; SSL no banco; `/docs` desligado em produção; CORS e cabeçalhos de segurança; limite de tentativas inválidas por IP; **rate limit global por token/IP** e **rotação de token** (Fase 4 · Etapa B); auditoria sem token; contêiner sem root; STRIDE com 17 novos itens da Fase 4.
* **Riscos residuais — dizemos nós, antes da banca:** API pública com **token estático**; rate limit global **só por instância e em memória** (não distribuído, sem WAF); **rotação de token manual** (não automática), sem MFA; `sslmode=require` **sem verificação do servidor**; sem backup gerenciado; IP em `audit_logs` sem prazo de retenção (`docs/LGPD.md`); hibernação do plano gratuito.
* Privacidade: sem dados pessoais de pessoa física no GOLD; ONGs por pseudônimo; plano de exclusão e direitos do titular descritos como trabalho futuro (`docs/LGPD.md`).

## 6. Próximos passos e prontidão (30 s)
* Hoje é demonstração acadêmica, **não produto**: faltam dados reais, rótulos manuais, verificação de cadastro/sanitária, licenças dos dados e parecer jurídico (`docs/COMMERCIAL_READINESS.md`).
* Evolução: lote misto por sublotes; rate limit distribuído (Redis/gateway) e rotação automática de token; piloto com doadores/ONGs reais; **rede comunitária** como visão futura (não existe hoje).
* Pós-apresentação: revogar tokens e desligar/apagar os serviços e o banco (`docs/LICENCAS_DEMONSTRACAO.md`).

## Perguntas prováveis
| Pergunta | Resposta honesta |
|---|---|
| "Quantos kg já foram salvos?" | Nenhuma doação real ainda. O painel mostra *ofertados* e *coletados* **simulados**, com selo. |
| "Quantas refeições?" | kg ÷ 0,4 — **premissa da equipe**, configurável e exibida na tela. Só vale para dados simulados. |
| "Está no ar? Onde estão os dados?" | Sim, em demonstração (Render + Supabase, ambos plano gratuito, EUA); só dados públicos e simulados; será desligado e apagado depois da apresentação. |
| "A IA funciona no mundo real?" | Não sabemos: foi avaliada só em dados simulados e o simulador é definido por nós (circularidade). |
| "É seguro?" | Há controles testados e varreduras limpas, mas é API pública com token estático (rotação manual) e rate limit só por instância e em memória; não houve teste de intrusão nem DAST. Os riscos estão em `docs/SEGURANCA_FINAL.md`. |
| "Atende à LGPD?" | Não há dados pessoais de usuários finais reais hoje; o IP em auditoria é o ponto aberto. Mapeamos riscos e deixamos direitos do titular como trabalho futuro (`docs/LGPD.md`). Parecer jurídico: a verificar. |
| "Por que não mostra o nome das ONGs?" | A base pública só tem pseudônimo; capacidade e horários são declarados/simulados. |
| "Dá para vender?" | Ainda não; ver `docs/COMMERCIAL_READINESS.md` (licenças de dados e requisitos legais a verificar). |

## Antes de subir ao palco (checklist do responsável)
* Gerar token **ADMIN** novo na manhã da defesa; criar contas demo DONOR e ORG; acordar os dois serviços; rodar `python -m scripts.smoke_cloud --acordar`.
* Ter as capturas de tela prontas (plano B se a nuvem não acordar).
* Revogar tudo depois (`create_user --revoke <rótulo>`).
