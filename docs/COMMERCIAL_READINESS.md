# Prontidão comercial — Rede Alimenta IA

> **Hoje o projeto é uma demonstração acadêmica, sem fins comerciais, e não está pronto para uso comercial.** Este documento só lista o que bloqueia e o que falta levantar. **Não contém preços, prazos nem valores** porque nenhum foi levantado; onde falta informação está "a levantar" ou "a verificar com assessoria jurídica".

## 1. Dados: licença por fonte

Fonte: `docs/data/DATA_LICENSES.md` (v3, 02/10/2026).

| Fonte | Termo verificado | Uso comercial |
|---|---|---|
| PAA (MDS) | CC-BY (metadado do portal; reverificação bloqueada) | permitido, com atribuição; **reverificar** |
| IBGE (municípios, população) | dado aberto; licença explícita **não localizada** | **não confirmado** |
| IPEA / Mapa das OSCs | "Other (Attribution)", não padronizada | **não confirmado** |
| MDS / RBBA | **não declarada** | **não confirmado** |
| Centroides de município (repositório de terceiros) | MIT no repositório; origem primária não declarada | não resolve a origem; substituir pela malha oficial do IBGE |
| Receita Federal (CNPJ) | não verificada | **não confirmado**; não usada hoje |

**Bloqueio:** fontes NEEDS_REVIEW (`publication_cleared=false`) **não podem entrar em produção** nem ser redistribuídas. A licença Apache-2.0 do software não resolve isso.

## 2. Bloqueios técnicos e de produto

| Tema | Situação hoje | O que falta |
|---|---|---|
| IA | métricas só em dados simulados; circularidade; lote misto desconhecido; sem `MANUALLY_LABELED` | **retreino e reavaliação com dados reais** de doações e desfechos; rotular textos reais |
| Cadastro de doadores e ONGs | ONGs por pseudônimo; capacidade/horários simulados; sem verificação | processo de **verificação** de doador e ONG (a levantar) |
| Condições sanitárias e responsabilidade | o sistema não atesta a segurança do alimento | requisitos sanitários aplicáveis à doação: **a verificar com assessoria jurídica e vigilância sanitária** |
| Logística real | distâncias estimadas; sem tempos de trânsito reais; sem frota real | integração com dados viários e acordo com parceiros logísticos (a levantar) |
| Segurança | token estático (rotação manual), rate limit só em memória por instância, sem MFA, sem backup gerenciado, sem DAST/pentest | itens de `docs/SEGURANCA_FINAL.md` §3 |
| Privacidade | IP em auditoria sem retenção; direitos do titular e fluxo de exclusão só como trabalho futuro | `docs/LGPD.md`; **papéis de controlador/operador, base legal e DPO: a verificar com assessoria jurídica** |
| Operação | planos gratuitos que hibernam e pausam; processo único; sem monitoramento nem plantão | arquitetura de produção e disponibilidade (a levantar) |
| Transferência internacional | Render (Oregon) e Supabase (Virginia): dados nos EUA | enquadramento legal: **a verificar com assessoria jurídica** |

## 3. Custos e limites a levantar

Nada abaixo foi cotado nesta fase.

* Custo de hospedagem fora dos planos gratuitos (aplicação, banco, backup): **a levantar**.
* Limites dos planos gratuitos usados e quando deixam de bastar: **a levantar** nos termos vigentes de cada provedor.
* Custo de licenciamento ou aquisição dos dados que hoje estão sem licença confirmada: **a levantar** com cada órgão.
* Custo de verificação de cadastro, suporte e conformidade: **a levantar**.

## 4. Caminho sugerido (sem prazos)

1. Resolver as licenças das fontes de dados (e-mails formais aos órgãos já listados em `DATA_LICENSES.md`).
2. Parecer jurídico sobre LGPD, responsabilidade sobre o alimento e papéis das partes.
3. Piloto controlado com poucos doadores e ONGs reais, com dados `USER_ENTERED` isolados dos simulados.
4. Coletar desfechos reais, rotular textos, retreinar e reavaliar o modelo; publicar nova ficha (`docs/MODEL_CARD.md`).
5. Endurecer segurança (rate limit distribuído, rotação automática/escopos de token, `verify-full`, backup, retenção de auditoria) e só então tratar escala.

## 5. O que este documento não afirma

Não afirma viabilidade financeira, demanda de mercado nem conformidade legal: nenhum desses pontos foi estudado ou verificado.
