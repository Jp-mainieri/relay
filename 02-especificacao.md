# Relay — Especificação (Backlog Priorizado)

## Priorização MoSCoW

### Must have (sem isso não há demo)
- Configurar checklist via texto (RF01)
- Ingerir transcrição (real ou injetada) (RF02/RF03)
- Motor de validação contextual comparando fala x checklist (RF04)
- Dashboard com cards mudando de estado (RF05)
- Webhook para Slack com resumo (RF09)

### Should have (eleva a demo, mas não quebra o "caminho feliz")
- Consulta de reincidência na Ambiguous (RF06)
- Alerta por voz (TTS) no fim do turno (RF07)

### Could have (só se sobrar tempo)
- Gravação estruturada na Ambiguous ao fim do turno (RF08)
- Polimento visual do dashboard além do essencial

### Won't have (explicitamente fora)
- Diarização por voz
- Autenticação/login
- Múltiplos dashboards / edição pós-turno

## User Stories

**US01** — Como *gestor de operação*, quero configurar o checklist da minha estação em linguagem natural, para não depender de um formulário rígido.
> Critério de aceite: POST `/api/config` aceita lista de itens em texto livre e retorna 200.

**US02** — Como *operador em turno*, quero que o sistema escute a conversa sem interromper, para que a passagem de bastão continue natural.
> Critério de aceite: nenhuma intervenção de voz ocorre antes do fim do turno.

**US03** — Como *gestor de operação*, quero ver ao vivo quais itens do checklist já foram cobertos, para acompanhar a passagem de turno remotamente.
> Critério de aceite: cards do dashboard mudam de cinza para verde via WebSocket em tempo real, com a evidência (trecho da fala) associada.

**US04** — Como *operador em turno*, quero ser avisado por voz se esqueci algo crítico, para corrigir antes de encerrar o turno.
> Critério de aceite: TTS dispara no máximo uma vez, apenas se `is_complete = false` ao final da conversa.

**US05** — Como *gestor de operação*, quero receber um resumo no Slack ao fim de cada turno, para não precisar acompanhar o dashboard ao vivo.
> Critério de aceite: webhook envia card com ID da estação, data/hora, % do checklist coberto, alerta da Ambiguous e resumo em bullets.

**US06** — Como *gestor de operação*, quero saber se um problema já mencionado em turnos anteriores está se repetindo, para priorizar manutenção.
> Critério de aceite: ao mencionar uma entidade crítica (ex: "empilhadeira 2"), o sistema consulta a Ambiguous e retorna alerta de reincidência se houver registro nos últimos 7 dias.

## Contratos de dados
Ver `05-arquitetura.md` — schemas de `/api/config`, `/api/analyze`, integração Ambiguous e payload Slack já especificados no pitch original.
