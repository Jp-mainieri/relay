# Relay — Projeto / Arquitetura

## Stack
- **Backend/orquestração**: FastAPI + WebSocket
- **Extração estruturada**: OpenAI + Pydantic (força o schema de saída do LLM)
- **Dashboard**: CopilotKit
- **Memória longitudinal**: Ambiguous (parceiro)
- **Saída de voz**: TTS
- **Notificação**: Slack (Incoming Webhook)

## Diagrama de fluxo
```
[Áudio no Ambiente / Microfone]
             │
             ▼
    [Camada de Transcrição]
             │
             ▼
    [Orquestrador FastAPI]
    ├── 1. Atualização de Estado (WebSocket) ──────> [Dashboard CopilotKit]
    ├── 2. Extração Estruturada (OpenAI / Pydantic)
    └── 3. Consulta de Reincidência ───────────────> [Memória Ambiguous]
             │
       (Fim do Turno)
             ├─ [Faltou item?] ── Sim ──> [Áudio TTS no Ambiente]
             └─ [100% Coberto] ─────────> [Webhook Slack / Gestão]
```

## Contratos de dados

### 1. Configuração do checklist — `POST /api/config`
```json
{
  "station_id": "doca-04",
  "items": [
    "status da carga refrigerada",
    "liberacao da doca",
    "nivel de bateria das empilhadeiras",
    "avarias ou pendencias de manutencao"
  ]
}
```

### 2. Retorno da análise — `POST /api/analyze`
```json
{
  "checklist_status": [
    {
      "item": "status da carga refrigerada",
      "covered": true,
      "evidence": "Carga da Swift já tá no plug 3."
    },
    {
      "item": "nivel de bateria das empilhadeiras",
      "covered": false,
      "evidence": null
    }
  ],
  "is_complete": false,
  "intervention_prompt": "Atenção: vocês não mencionaram a bateria das empilhadeiras. Alguma pendência?",
  "ambiguous_alert": "Histórico: Empilhadeira 2 apresentou falha de recarga nos últimos 2 turnos.",
  "summary": "Doca liberada e carga refrigerada conectada. Pendência na checagem de maquinário."
}
```

### 3. Integração Ambiguous (memória)
- **Leitura**: na menção de entidades críticas (equipamentos, números de doca/quarto), busca registros vinculados nos últimos 7 dias.
- **Gravação**: ao final do turno, salva objeto estruturado com timestamp, pendências resolvidas e novos incidentes.

### 4. Notificação Slack (payload)
Card compacto contendo: ID da estação, data/hora, percentual do checklist validado, alerta da Ambiguous e resumo operacional em bullet points.

## Pendente de definição
- **Formato da mensagem WebSocket** (estado incremental por item vs. payload completo a cada atualização) — decidir antes de paralelizar P2/P4, ver `04-planejamento.md`.
- Estrutura exata do objeto gravado na Ambiguous (schema de gravação, além do de leitura já mostrado acima).

## Modelagem de dados
Não há persistência própria no MVP além da Ambiguous (memória externa) e do estado em memória do orquestrador durante o turno — não há banco de dados dedicado no escopo das 4h. Se necessário evoluir pós-MVP, o candidato natural é uma tabela `turnos` (station_id, timestamp, checklist_status, summary) espelhando o schema de `/api/analyze`.
