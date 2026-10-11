# Licenças de software adicionadas na Fase 2 Parte 2

| Componente | Versão | Uso | Licença | Como foi verificada |
|---|---|---|---|---|
| Google OR-Tools (`ortools`) | 9.15.6755 | solver da roteirização (`routing/`) | **Apache License 2.0** | metadados do pacote instalado (`License`/classificador) |
| Ruff | 0.17.0 | lint (CI) | MIT | declarada pelo projeto; não incorporado às imagens |
| Bandit | 1.9.4 | SAST (CI) | Apache-2.0 | idem |
| pip-audit | 2.10.1 | varredura de dependências (CI) | Apache-2.0 | idem |
| Trivy | 0.75.0 / ação `setup-trivy` | varredura de imagens/dependências/configuração (CI) | Apache-2.0 | idem |
| gitleaks | 8.30.1 | varredura de segredos (CI) | MIT | idem |

Observação: **OR-Tools, Bandit e pip-audit** tiveram a licença conferida nos metadados do pacote instalado; **Ruff, Trivy e gitleaks** constam como as licenças declaradas publicamente pelos projetos e **não foram reverificadas** nesta sessão. Nenhuma dessas ferramentas é distribuída nas imagens de produção (apenas o OR-Tools).
