# data/manual_labeled/ — conjunto de teste MANUALMENTE rotulado (pendente)

**Estado:** o conjunto `MANUALLY_LABELED` **ainda não existe**. `manual_labeled_text_TEMPLATE.csv` está vazio. `PROVISORIO_rascunho_ia.csv` tem 83 textos **escritos e rotulados por IA** (autoria `IA_RASCUNHO_PROVISORIO_REVISAO_PENDENTE`); servem só como teste de fumaça e **não** podem ser apresentados como dado real ou rotulagem humana.

## Protocolo para a equipe

1. Coletar descrições reais de doação (anônimas; sem nomes, telefones, CPF/CNPJ, e-mail, endereço). Fonte e autorização registradas.
2. Dois anotadores rotulam de forma independente: categoria, produto, perecibilidade, exige_refrigeracao, dias_ate_validade (ou ausente), quantidade, unidade. Guia: `simulation/config/taxonomy_v0.2.yaml`.
3. Calcular concordância (kappa) e arbitrar divergências; guardar as duas rotulagens.
4. Preencher `data_origin = MANUALLY_LABELED` e `authoring` (quem rotulou), separar 50% para ajuste de limiar e 50% para teste final (nunca usar o teste para escolher τ).
5. Rodar `python -m ml.semantic.train_eval main` e reportar os resultados **separados** dos simulados.
