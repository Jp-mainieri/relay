# backend — Orquestrador (P2)

## Rodar (a partir da raiz do repo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # preencha as chaves reais quando for integrar de verdade
uvicorn backend.main:app --reload --port 8000
```

## Endpoints (feat/orquestrador — fluxo real)

Contratos congelados (CONTRACTS.md):
- `GET /health`
- `POST /api/config` — persiste `ChecklistConfig` em memória por `station_id` e abre um turno novo e limpo.
- `POST /api/analyze` — chama o motor de validação de verdade (`backend/validacao.py`, P3) via `backend/validation_client.py`, com fallback para `mocks/analyze_response.json` enquanto P3 não entrega ou se o motor falhar.
- `WS /ws/{station_id}` — push real: `state` (ao conectar e a cada mudança), `intervention`/`slack_sent` (fim do turno), `error` (falha não-fatal, ex. Ambiguous fora do ar).

**Aditivo, NÃO congelado** (CONTRACTS.md não define como P1 entrega transcrição ao vivo — só o formato da string `transcript`). Proposto por P2 para destravar a integração; time avisado, sujeito a ajuste se P1 já tiver assumido outro formato:
- `POST /api/turns/{station_id}/lines` — body `{ "speaker": "OPERADOR A" | null, "text": "...", "end_of_turn": false }`. Acrescenta uma fala ao turno ativo da estação, roda a validação e empurra `state` via WS. `end_of_turn=true` força o encerramento do turno após processar a fala.
- `POST /api/turns/{station_id}/end` — encerramento explícito do turno (sem body). Revalida com a transcrição completa, empurra `state` final e os eventos `intervention` (só se `is_complete=false`) e `slack_sent` (sempre).
- Fim de turno também é detectado automaticamente por uma heurística de palavras-chave em `_looks_like_end_of_turn` (main.py) — best-effort para a demo, não é NLP de verdade.
- Ambos exigem `POST /api/config` prévio para a estação (404 caso contrário). Se o turno da estação já tiver encerrado, a próxima fala ingerida abre um turno novo automaticamente (mesmo checklist).

## Quem executa o quê nos eventos de fim de turno

- P2 (aqui) só **emite** os eventos estruturados `intervention` e `slack_sent` pelo WebSocket — nunca chama TTS nem o webhook do Slack diretamente.
- P4 é quem **executa**: toca o TTS ao receber `intervention`, e faz o POST ao Incoming Webhook ao receber `slack_sent` (ver CONTRACTS.md secao 3 — o contrato deixa em aberto quem faz a chamada HTTP de fato).

## RNF04 — resiliência a falha externa

Duas camadas de isolamento, nenhuma propaga exceção para fora:
1. `backend/validation_client.py::analisar` — tenta o motor real de P3 (`backend/validacao.py`); cai para fallback de mock em qualquer falha ou ausência do módulo. Dentro do fallback, a consulta de reincidência (simulada) tem try/except própria e vira `ambiguous_alert=None` em caso de erro.
2. `backend/main.py::_run_validation_safe` — chama o item 1 em thread própria com try/except adicional; se mesmo assim algo escapar, emite um evento `error` no WS e mantém o último estado conhecido em vez de derrubar a ingestão.
