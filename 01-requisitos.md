# Relay — Requisitos (Elicitação)

## Contexto
Agente de áudio ambiental que acompanha a passagem de turno no chão de operação, escuta em silêncio e intervém por voz apenas se um item crítico do checklist for esquecido. Publica relatório estruturado no canal de gestão (Slack/Teams).

## Stakeholders / usuários
- **Operadores em turno** (quem fala durante a passagem de bastão) — usuários passivos, não interagem com telas.
- **Gestor de operação** — consome o relatório no Slack/Teams e o dashboard ao vivo.
- **Parceiro técnico (Ambiguous)** — provê a camada de memória longitudinal.

## Problema real
Falhas operacionais (pendências, avarias, reincidências) se perdem na troca de turno porque a passagem de bastão é verbal, informal e sem registro estruturado.

## Restrições externas
- Prazo de execução: **4 horas** (hackathon).
- Integração obrigatória com parceiro **Ambiguous** (memória) para efeito de pontuação/avaliação do desafio.
- Stack sugerida pelo desafio: **CopilotKit** (dashboard), **FastAPI** (orquestração), **OpenAI/Pydantic** (extração estruturada).

## Requisitos Funcionais (RF)
| ID | Descrição |
|----|-----------|
| RF01 | Permitir configurar o checklist de uma estação via texto livre em linguagem natural |
| RF02 | Ingerir áudio (microfone) ou transcrição injetada continuamente |
| RF03 | Transcrever o diálogo em tempo real |
| RF04 | Comparar contextualmente a transcrição com os itens do checklist (não apenas por palavra-chave) |
| RF05 | Exibir dashboard em tempo real com transcrição e cards do checklist (cinza → verde) |
| RF06 | Consultar histórico de reincidência (últimos 7 dias) na Ambiguous ao detectar entidades críticas mencionadas |
| RF07 | Emitir alerta por voz (TTS) uma única vez, ao final do turno, se algum item do checklist não foi coberto |
| RF08 | Gravar na Ambiguous o resultado estruturado do turno (timestamp, pendências, novos incidentes) ao final |
| RF09 | Enviar resumo formatado (card compacto) para um canal do Slack via webhook |

## Requisitos Não-Funcionais (RNF)
| ID | Descrição |
|----|-----------|
| RNF01 | Atualização do dashboard deve ser percebida como "tempo real" (via WebSocket, não polling) |
| RNF02 | Sistema não deve interromper a conversa dos operadores — intervenção só ao final, não durante |
| RNF03 | Sem autenticação/login no MVP — acesso direto ao dashboard |
| RNF04 | Resiliência mínima: falha na Ambiguous não pode travar o fluxo principal (checklist/dashboard/Slack) |
| RNF05 | Setup deve ser demonstrável ao vivo em ambiente de hackathon (sem infra complexa de deploy) |

## Fora de escopo (declarado)
- Diarização biométrica (identificar quem fala)
- Autenticação, login, permissões
- Múltiplos dashboards ou edição pós-turno
