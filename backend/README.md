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
- `POST /api/analyze` — valida `AnalyzeRequest`, retorna sempre `mocks/analyze_response.json`.
- `WS /ws/{station_id}` — replay em loop de `mocks/ws_sequence/*.json`, na ordem numérica.

Contratos completos e decisões de design: ver `/CONTRACTS.md` na raiz.

## O que muda na próxima fase (feat/orquestrador)

- `/api/config` passa a persistir o checklist em memória (por `station_id`).
- `/api/analyze` deixa de ser chamado externamente com mock fixo — o
  orquestrador chama `backend/validacao.py::analisar` (P3) internamente a
  cada trecho novo de transcrição.
- `/ws/{station_id}` empurra `TurnState` real a cada mudança de fato, e os
  eventos `intervention`/`slack_sent` só disparam no fim do turno de verdade.
- Try/except ao redor de qualquer chamada à Ambiguous (RNF04) — nunca deixe
  travar o fluxo principal.
