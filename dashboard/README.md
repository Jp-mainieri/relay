# dashboard — CopilotKit/Next.js (P4)

Esqueleto mínimo. A implementação (telas, CopilotKit, TTS, envio ao Slack) é
inteira da fronteira P4 — nada de lógica de negócio foi colocado aqui na Fase 0.

## Contratos

Importe os tipos de `../shared/types.ts` (alias `@shared/*` já configurado em
`tsconfig.json`), por exemplo:

```ts
import type { WSMessage, TurnState } from "@shared/types";
```

Contratos completos, incluindo o formato das mensagens WebSocket e por que
foi decidido assim: ver `/CONTRACTS.md` na raiz do repo.

## Enquanto o backend real não está pronto

Use os arquivos de `/mocks/ws_sequence/*.json` (em ordem numérica) para
simular a sequência de mensagens que o canal `/ws/{station_id}` envia.
A partir da Fase 0, o backend stub em `backend/main.py` já serve essa mesma
sequência de verdade em `ws://localhost:8000/ws/{station_id}` — prefira
conectar nele a hardcodar os mocks, para pegar cedo qualquer divergência de
schema.

## Setup

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

`.env.local.example` é o recorte do `/.env.example` que o dashboard de fato
usa: as três `NEXT_PUBLIC_*` (API, WebSocket e estação) mais
`SLACK_WEBHOOK_URL` e `OPENAI_API_KEY`, que ficam sem prefixo porque são lidas
só nos route handlers — segredo com `NEXT_PUBLIC_` vaza para o browser.
