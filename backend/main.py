"""
Relay — Orquestrador FastAPI (feat/orquestrador · fluxo real).

Substitui os stubs da Fase 0 pela lógica de negócio:
  1. POST /api/config          — persiste o checklist da estação em memória e abre um turno novo.
  2. POST /api/turns/{id}/lines — ingestão de transcrição contínua vinda de P1 (ver nota abaixo).
  3. POST /api/turns/{id}/end   — gatilho explícito de fim de turno (ver nota abaixo).
  4. POST /api/analyze          — mesmo contrato da Fase 0, agora chamando o motor de validação de verdade.
  5. WS   /ws/{station_id}      — push real de `state`/`intervention`/`slack_sent`/`error` (CONTRACTS.md secao 3).

NOTA — endpoints de ingestão (`/api/turns/...`) NÃO estão no CONTRACTS.md
congelado: o documento define o *formato* da string `transcript` (AnalyzeRequest),
mas não como P1 entrega isso ao orquestrador ao vivo, nem como o fim de turno é
sinalizado. São adições aditivas desta fronteira (P2), documentadas em
backend/README.md — avisar o time (em especial P1) antes de dar como fechado.

Disparo de TTS e do webhook do Slack continuam sendo executados por P4; este
módulo só emite os eventos estruturados (`intervention`, `slack_sent`) pelo
WebSocket, nunca chama serviço externo diretamente.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # habilita `import shared` e `import backend`

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import validation_client
from backend.state import StationTurn, store
from shared.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChecklistConfig,
    ChecklistConfigResponse,
    TurnState,
    WSStateMessage,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("relay.main")

app = FastAPI(title="Relay Orquestrador", version="0.1.0")

# Dashboard roda em outra origem (Next.js dev server) — sem auth no MVP (RNF03).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frases que, ao aparecerem no FIM de uma fala, disparam o fim de turno
# automaticamente — heurística mínima de demo (item 4 da tarefa: "detecte o
# gatilho de encerramento"). P1 também pode sinalizar explicitamente via
# `end_of_turn=true` no corpo de /api/turns/{id}/lines, ou chamar
# /api/turns/{id}/end direto — os três caminhos convergem no mesmo fluxo.
_END_OF_TURN_HINTS = (
    "até amanhã",
    "ate amanha",
    "falou",
    "valeu, até",
    "fechado por aqui",
    "encerrando",
    "câmbio desligo",
    "cambio desligo",
)


def _looks_like_end_of_turn(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in _END_OF_TURN_HINTS)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 1. POST /api/config — persiste o checklist em memória (CONTRACTS.md secao 1)
# ---------------------------------------------------------------------------


@app.post("/api/config", response_model=ChecklistConfigResponse)
async def post_config(config: ChecklistConfig) -> ChecklistConfigResponse:
    turn = store.configure(config.station_id, config.items)
    await store.push_state(turn)  # cliente já conectado vê o checklist zerado imediatamente
    return ChecklistConfigResponse(status="ok", station_id=config.station_id, items=config.items)


# ---------------------------------------------------------------------------
# 2. Motor de validação — chamada interna compartilhada por ingestão e /api/analyze
# ---------------------------------------------------------------------------


async def _run_validation_safe(station_id: str, transcript: str, items: list[str]) -> Optional[AnalyzeResponse]:
    """
    RNF04, camada do orquestrador: mesmo que `validation_client.analisar` já
    isole falhas internamente (motor real -> fallback de mock -> ambiguous
    None), esta chamada é feita em thread + try/except próprios para que
    NENHUMA exceção do motor de validação consiga derrubar a ingestão ou a
    conexão WebSocket. Falha aqui -> evento `error` no canal + mantém o
    último estado conhecido (não zera o progresso do checklist na demo).
    """
    try:
        raw = await asyncio.to_thread(validation_client.analisar, transcript, items)
        return AnalyzeResponse(**raw)
    except Exception:
        logger.exception("Falha inesperada no motor de validacao para station_id=%s", station_id)
        await store.push_error(station_id, "Falha no motor de validação — mantendo último estado conhecido (RNF04).")
        return None


# ---------------------------------------------------------------------------
# 3. POST /api/analyze — mesmo contrato da Fase 0, agora com o motor de verdade
# ---------------------------------------------------------------------------


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def post_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    result = await _run_validation_safe(request.station_id, request.transcript, request.items)
    if result is None:
        # Endpoint stateless (contrato não tem "estado anterior" pra manter) —
        # única saída segura aqui é um AnalyzeResponse degradado, nunca 500.
        result = AnalyzeResponse(
            checklist_status=[{"item": i, "covered": False, "evidence": None} for i in request.items],
            is_complete=False,
            intervention_prompt=None,
            ambiguous_alert=None,
            summary="",
        )
    return result


# ---------------------------------------------------------------------------
# 4. Ingestão de transcrição (P1 -> P2) — ADITIVO, ver nota no topo do arquivo
# ---------------------------------------------------------------------------


class IngestLineRequest(BaseModel):
    """
    Body de POST /api/turns/{station_id}/lines.

    NÃO é um contrato congelado do CONTRACTS.md — proposto por P2 para
    destravar a integração com P1 enquanto o time não fecha algo diferente.
    """

    speaker: Optional[str] = None
    text: str
    end_of_turn: bool = False


async def _finish_turn(turn: StationTurn) -> None:
    """
    Fim de turno (RF07/RF09): empurra o `state` final e dispara os DOIS
    eventos estruturados de encerramento — quem efetivamente toca o TTS e
    chama o webhook do Slack é P4.

    Não revalida aqui: toda ingestão de fala (`ingest_line`) já roda a
    validação com a transcrição completa antes de retornar, então o estado do
    turno já está atualizado com a última fala no momento em que o fim é
    detectado. Uma estação encerrada sem nenhuma fala ingerida (`/end` chamado
    direto após `/api/config`) mantém o checklist zerado, que já é o estado
    correto para "nada foi dito ainda".
    """
    if turn.ended:
        return
    turn.ended = True
    await store.push_state(turn)

    if not turn.is_complete:
        prompt = turn.intervention_prompt
        if not prompt:
            pending = next((s.item for s in turn.checklist_status if not s.covered), None)
            prompt = (
                f"Atenção: antes de encerrar, confirma o item '{pending}'?"
                if pending
                else "Atenção: alguns itens do checklist não foram confirmados antes do fim do turno."
            )
        turn.intervention_sent = True
        await store.push_intervention(turn, prompt)

    # `slack_sent` sempre dispara ao fim do turno — é o sinal estruturado que
    # P4 usa para executar o POST ao Incoming Webhook (contrato deixa em
    # aberto quem faz a chamada HTTP; aqui P2 nunca chama, só sinaliza).
    await store.push_slack_sent(turn)


@app.post("/api/turns/{station_id}/lines", response_model=TurnState)
async def ingest_line(station_id: str, line: IngestLineRequest) -> TurnState:
    async with store.lock_for(station_id):
        turn = store.active_turn(station_id)
        if turn is None:
            raise HTTPException(status_code=404, detail="Estacao sem checklist configurado — chame POST /api/config antes.")

        turn.append_line(line.speaker, line.text)
        result = await _run_validation_safe(station_id, turn.transcript_text(), turn.items)
        if result is not None:
            turn.apply_analysis(result)
        await store.push_state(turn)

        if line.end_of_turn or _looks_like_end_of_turn(line.text):
            await _finish_turn(turn)

        return turn.to_state()


@app.post("/api/turns/{station_id}/end", response_model=TurnState)
async def end_turn(station_id: str) -> TurnState:
    async with store.lock_for(station_id):
        turn = store.current_turn(station_id)
        if turn is None:
            raise HTTPException(status_code=404, detail="Estacao sem checklist configurado — chame POST /api/config antes.")
        await _finish_turn(turn)
        return turn.to_state()


# ---------------------------------------------------------------------------
# 5. WS /ws/{station_id} — push real (CONTRACTS.md secao 3)
# ---------------------------------------------------------------------------


@app.websocket("/ws/{station_id}")
async def ws_channel(websocket: WebSocket, station_id: str) -> None:
    await websocket.accept()
    store.register_socket(station_id, websocket)
    try:
        # "ao conectar, o servidor deve empurrar imediatamente uma mensagem
        # state" — estado atual, ou vazio se o turno ainda não começou.
        snapshot = store.snapshot_or_empty(station_id)
        await websocket.send_json(WSStateMessage(payload=snapshot).model_dump(mode="json"))
        while True:
            # Canal é só de push do servidor; apenas drena o que o cliente mandar
            # (ping/keepalive) para detectar desconexão sem derrubar o processo.
            await websocket.receive_text()
    except WebSocketDisconnect:
        # Reconexão é esperada e não deve gerar erro de servidor (ver CONTRACTS.md).
        pass
    finally:
        store.unregister_socket(station_id, websocket)
