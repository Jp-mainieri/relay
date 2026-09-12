# Casos de demonstração

Cada resposta que confirma um item de checklist repete explicitamente a
entidade e a condição verificadas. Isto reduz ambiguidade no ensaio ao vivo e
permite auditar a evidência literal mostrada no dashboard.

| Arquivo | Resultado esperado |
| --- | --- |
| `completa_padrao.txt` | 4 de 4 itens cobertos; não há intervenção final. |
| `empilhadeira2_problema.txt` | 4 de 4 itens cobertos, com incidentes explícitos na empilhadeira 2 para testar memória longitudinal. |
| `incompleta_sem_refrigerada.txt` | 3 de 4 itens cobertos; somente `status da carga refrigerada` fica pendente e deve disparar intervenção ao fim. |

Os casos são material de demonstração, não regras de validação. O motor P3
continua obrigado a rejeitar evidência de entidade ou condição diferente.
