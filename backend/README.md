# backend — Orquestrador (P2)

## Rodar (a partir da raiz do repo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # preencha as chaves reais quando for integrar de verdade
uvicorn backend.main:app --reload --port 8000
```

## Endpoints (Fase 0 — stubs, dados fixos de /mocks)

- `GET /health`
- `POST /api/config` — valida `ChecklistConfig`, ecoa de volta.
- `POST /api/transcript` — valida `TranscriptPostRequest` (uma fala), confirma recebimento. (P1 → P2)
- `POST /api/turn/end` — valida `TurnEndRequest`, confirma recebimento. Único gatilho de fim de turno. (P1 → P2)
- `POST /api/analyze` — valida `AnalyzeRequest`, retorna sempre `mocks/analyze_response.json`.
- `WS /ws/{station_id}` — replay em loop de `mocks/ws_sequence/*.json`, na ordem numérica.

Contratos completos e decisões de design: ver `/CONTRACTS.md` na raiz.

## O que muda na próxima fase (feat/orquestrador)

- `/api/config` passa a persistir o checklist em memória (por `station_id`).
- `/api/transcript` passa a anexar cada fala ao `transcript_log` do turno,
  ordenando por `seq`, e empurrar `state` atualizado pelo WebSocket.
- `/api/turn/end` passa a ser o gatilho real: roda a análise uma última vez
  e emite `intervention` (se `is_complete=false`) e `slack_card` (sempre)
  pelo WebSocket. Nenhuma inferência de fim de turno por timeout/silêncio.
- `/api/analyze` deixa de ser chamado externamente com mock fixo — o
  orquestrador chama `backend/validacao.py::analisar` (P3) internamente.
- `/ws/{station_id}` empurra `TurnState` real a cada mudança de fato.
- Try/except ao redor de qualquer chamada à Ambiguous (RNF04) — nunca deixe
  travar o fluxo principal.
