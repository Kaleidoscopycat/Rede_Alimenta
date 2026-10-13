# Pitch final — Rede Alimenta IA (rascunho da Etapa A)

> Rascunho para ensaio. Todo número abaixo tem origem indicada; **nada simulado é apresentado como real**. A URL pública entra na Etapa B.

**Duração sugerida:** 5 minutos · **Critérios da banca:** Impacto Social 30% · Qualidade da IA 30% · DevSecOps 20% · Engenharia & Defesa 20%.

## 1. Problema e ideia (30 s) — Impacto social
* Alimento bom é descartado enquanto ONGs precisam de doações; o gargalo é **encontrar a ONG certa, a tempo, com capacidade e rota**.
* A Rede Alimenta IA conecta **doador → ONG** em tempo real (a distribuição da ONG ao beneficiário está fora do escopo).

## 2. Dados (45 s)
* 🟦 **PÚBLICO:** 54.590 ONGs e bancos de alimentos (IPEA/OSC, RBBA), 5.571 municípios, 27.855 indicadores (IBGE/PAA). Licença em revisão; uso acadêmico.
* 🟧 **SIMULADO:** doadores, lotes e desfechos gerados por simulador reprodutível (semente + versão). Selo visível em toda tela.
* 🟩 **MEDIDO:** entradas reais na plataforma — hoje **"Nenhuma doação real registrada."** Dizer isso é parte da honestidade do projeto.

## 3. IA (90 s) — Qualidade da IA
* O motor: elegibilidade eliminatória → candidatas geográficas → **ML + regras + distância** → ranking explicado.
* Resultado **sobre dados simulados** (teste, 134 mil pares): **MRR 0,695** (HistGradientBoosting) contra 0,465 da *ONG mais próxima* e 0,541 da *regra*; **Top-1 54,6%** contra 27,2% e 35,3%; **ROC-AUC 0,798**, PR-AUC 0,459, F1 0,503.
* Parser de texto: acurácia de categoria 96,1% (texto simulado visto) e 95,6% (família nunca vista) — **não há conjunto rotulado manualmente**.
* Limitações ditas por nós: circularidade do simulador; lote misto desconhecido; ONGs por pseudônimo.
* **Demo:** tela *Recomendações* — informar um lote e ver o ranking; tela *Logística* — três estratégias sobre os mesmos lotes.

## 4. Produto (60 s) — Engenharia
* Três perfis com visibilidade aplicada **na API**: doador não vê scores; ONG vê a proposta e a "Análise da IA" em texto; ADMIN vê tudo (acesso auditado).
* **Demo:** Overview (selos, premissa 0,4 kg/refeição), Mapa (calor, rotas), Doações e matches, IA, Segurança.
* Rotas de coleta com OR-Tools comparadas ao vizinho mais próximo; distâncias são **estimativas**, não rota viária.

## 5. DevSecOps (75 s)
* CI com Ruff, testes (PostgreSQL), Bandit, pip-audit, Trivy, gitleaks e fluxo completo via Compose.
* SAST: Bandit **13 → 0** (7 corrigidos, 6 suprimidos com justificativa registrada); pip-audit 0; STRIDE com riscos, mitigação e status (inclui P3C-1…10 do dashboard).
* Trivy de imagem: **4 HIGH → 0** é comprovado pelo CI; no painel só é contado quando os JSONs *antes/depois* estão em `security/reports/ci/`.
* Observabilidade: log JSON, `X-Request-ID`, auditoria `admin.access`; token ADMIN da defesa criado por `scripts/create_user.py` e **revogado** com `--revoke <rótulo>`.

## 6. Próximos passos (30 s)
* Etapa B: imagens com `PORT`, banco em nuvem, URL pública, smoke test.
* Evolução: lote misto por sublotes; rotulagem manual de textos reais; rate limit e rotação de tokens (Fase 4).

## Perguntas prováveis
| Pergunta | Resposta honesta |
|---|---|
| "Quantos kg já foram salvos?" | Nenhuma doação real ainda. O painel mostra *ofertados* e *coletados* **simulados**, com selo. |
| "Quantas refeições?" | kg ÷ 0,4 — **premissa da equipe**, configurável e exibida na tela. |
| "A IA funciona no mundo real?" | Não sabemos: foi avaliada só em dados simulados, e o simulador é definido por nós (circularidade). |
| "Por que não mostra nome das ONGs?" | A base pública só tem pseudônimo; capacidade e horários são declarados/simulados. |
