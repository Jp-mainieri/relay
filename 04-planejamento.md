# Relay — Planejamento

## Metodologia
Kanban informal por pessoa/fronteira do sistema — justificado pelo contexto: time fixo de 4 pessoas, prazo rígido de 4h, sem tempo para cerimônias de Scrum. Cada pessoa é dona de uma fronteira da arquitetura (ver `05-arquitetura.md`) e integra pelos contratos de dados já definidos.

## Equipe e alocação
| Pessoa | Responsabilidade |
|--------|-------------------|
| P1 | Ingestão de áudio/texto (transcrição real ou simulada) |
| P2 | Orquestrador FastAPI + WebSocket (estado em tempo real) |
| P3 | Motor de validação (OpenAI/Pydantic) + integração Ambiguous |
| P4 | Dashboard CopilotKit + saídas (TTS e Slack) |

## Cronograma (4h)

| Tempo | Marco |
|-------|-------|
| 0:00 – 0:20 | Setup do monorepo, secrets/env vars (`OPENAI_API_KEY`, `AMBIGUOUS_API_KEY`, `SLACK_WEBHOOK_URL`, chave TTS), contrato do WebSocket fechado entre P2 e P4 |
| 0:20 – 2:00 | Desenvolvimento em paralelo por fronteira, usando mocks dos contratos de dados para não bloquear entre si |
| 2:00 – 2:30 | **Marco de integração**: rodar o fluxo ponta a ponta uma vez, mesmo que feio, com os mocks — expõe incompatibilidade de schema cedo |
| 2:30 – 3:30 | Correção de integração, substituição de mocks pela lógica real, polimento do "should have" (TTS, reincidência Ambiguous) |
| 3:30 – 3:50 | Buffer para bugs + ensaio da demo |
| 3:50 – 4:00 | Corte de escopo de emergência se algo não fechar (ver plano de fallback abaixo) |

## Riscos e mitigação

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Integração com Ambiguous não fecha a tempo | Perde diferencial de "memória longitudinal" na demo | RNF04: falha na Ambiguous não trava o fluxo principal; demo funciona sem RF06/RF08 se necessário |
| STT (reconhecimento de voz) real não funciona ao vivo | Demo trava por dependência externa | Começar com transcrição simulada/injetada (texto); só trocar por STT real se sobrar tempo |
| Contrato de WebSocket diverge entre backend (P2) e dashboard (P4) | Retrabalho tardio, dashboard não atualiza | Fechar o formato exato da mensagem WebSocket ANTES de codar (ver nota abaixo) |
| TTS ou webhook do Slack falham no ambiente da demo | Parte visível do "caminho feliz" quebra | Testar esses dois pontos isoladamente antes do marco de integração, não só no fim |
| Prompt de extração (OpenAI/Pydantic) alucina cobertura de item | Checklist mostra falso positivo/negativo na demo | Validar manualmente com 2-3 transcrições de teste antes da demo |

## Pendência de decisão
O formato exato das mensagens que o backend empurra via WebSocket para o dashboard ainda não foi fechado — decisão bloqueante para P2 e P4 trabalharem em paralelo sem retrabalho.
