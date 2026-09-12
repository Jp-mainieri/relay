# backend — Orquestrador (P2)

## Rodar (a partir da raiz do repo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # preencha as chaves reais quando for integrar de verdade
uvicorn backend.main:app --reload --port 8000
```

## Testar

```bash
pip install -r backend/requirements-dev.txt

# Suite in-process (sem subir servidor), ~2s. Cobre: turno completo/incompleto,
# reconexão, múltiplos clientes WS, isolamento entre estações, reset via
# /api/config, seq fora de ordem + retry, timeout e exceção do motor (RNF04),
# /api/turn/end em duplicidade, 422/404, e o fallback de mock.
pytest backend/tests -q

# Smoke-test ponta a ponta com o player REAL de P1 (sobe o backend em :8765,
# injeta uma transcrição de mocks/transcricoes fala por fala, escuta o WS como
# um dashboard faria e confere os invariantes do contrato). Sai 0/1.
python backend/scripts/smoke_test.py
python backend/scripts/smoke_test.py --transcript mocks/transcricoes/completa_padrao.txt --delay 1
python backend/scripts/smoke_test.py --backend-url http://localhost:8000   # contra um backend já rodando
```

A suite troca o motor de validação por um dublê determinístico (item coberto
= texto do item aparece literalmente numa fala), porque o alvo é a
orquestração, não a qualidade da análise — assim ela não depende de P3 nem
de `mocks/analyze_response.json`. O fallback real de mock tem testes próprios
em `backend/tests/test_validation_client.py`.

## Endpoints (feat/orquestrador — fluxo real, Revisão 2 dos contratos)

Todos congelados em CONTRACTS.md:
- `GET /health`
- `POST /api/config` — persiste `ChecklistConfig` em memória por `station_id` e abre um turno novo e limpo.
- `POST /api/transcript` — ingestão de uma fala por vez de P1 (`TranscriptPostRequest`: `station_id`, `seq`, `speaker`, `text`, `ts`). Anexa ao `transcript_log` do turno ordenando por `seq` (não pela ordem de chegada do HTTP), roda a validação e empurra `state` atualizado pelo WS.
- `POST /api/turn/end` — **único gatilho de fim de turno reconhecido pelo sistema** (`TurnEndRequest: {station_id}`). Enviado por P1 logo após a última fala. Empurra o `state` final e dispara `intervention` (só se `is_complete=false`) e `slack_card` (sempre) pelo WS. P2 não infere fim de turno por timeout/silêncio/heurística — só por esta chamada.
- `POST /api/analyze` — chama o motor de validação de verdade (`backend/validacao.py`, P3) via `backend/validation_client.py`, com fallback para `mocks/analyze_response.json` enquanto P3 não entrega ou se o motor falhar.
- `WS /ws/{station_id}` — push real: `state` (ao conectar e a cada mudança), `intervention`/`slack_card` (fim do turno), `error` (falha não-fatal, ex. Ambiguous fora do ar).

**Nota de migração:** a Fase 0 desta fronteira tinha proposto endpoints de
ingestão próprios (`/api/turns/{station_id}/lines` e `/end`), fora do
CONTRACTS.md, enquanto o contrato P1↔P2 não existia. A Revisão 2 fechou esse
contrato oficialmente como `/api/transcript` + `/api/turn/end` (acima) — P1
(`feat/ingestao`) já implementa contra os oficiais. Os endpoints antigos
foram removidos (não tinham nenhum consumidor real) em vez de mantidos como
alias, para não reintroduzir por uma porta lateral a inferência de fim de
turno por heurística que a Revisão 2 proíbe explicitamente.

## Quem executa o quê nos eventos de fim de turno

- P2 (aqui) só **emite** os eventos estruturados `intervention` e `slack_card` pelo WebSocket — nunca chama TTS nem o webhook do Slack diretamente.
- P4 é quem **executa**: toca o TTS ao receber `intervention`, e faz o `POST` do `payload.card` (`SlackCardPayload`, já pronto) ao Incoming Webhook ao receber `slack_card` (CONTRACTS.md secao 5, Revisão 2 — dono do POST HTTP é P4).

## RNF04 — resiliência a falha externa

Duas camadas de isolamento, nenhuma propaga exceção para fora:
1. `backend/validation_client.py::analisar` — tenta o motor real de P3 (`backend/validacao.py`); cai para fallback de mock em qualquer falha ou ausência do módulo. Dentro do fallback, a consulta de reincidência (simulada) tem try/except própria e vira `ambiguous_alert=None` em caso de erro.
2. `backend/main.py::_run_validation_safe` — chama o item 1 em thread própria com try/except adicional; se mesmo assim algo escapar, emite um evento `error` no WS e mantém o último estado conhecido em vez de derrubar a ingestão.
