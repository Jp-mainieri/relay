"""
Relay — Orquestrador FastAPI (feat/orquestrador · fluxo real, Revisão 2 dos contratos).

Endpoints:
  1. POST /api/config       — persiste o checklist da estação em memória e abre um turno novo.
  2. POST /api/transcript   — ingestão de uma fala por vez, vinda de P1 (CONTRACTS.md secao 2.5).
  3. POST /api/turn/end     — ÚNICO gatilho de fim de turno, vindo de P1 (CONTRACTS.md secao 2.6).
  4. POST /api/analyze      — mesmo contrato da Fase 0, agora chamando o motor de validação de verdade.
  5. WS   /ws/{station_id}  — push real de `state`/`intervention`/`slack_card`/`error` (CONTRACTS.md secao 3).

Disparo de TTS e do POST ao webhook do Slack continuam sendo executados por
P4; este módulo só emite os eventos estruturados (`intervention`, `slack_card`)
pelo WebSocket, nunca chama serviço externo diretamente.

P2 NÃO infere fim de turno por timeout/silêncio/heurística de texto —
`POST /api/turn/end` é o único gatilho reconhecido (CONTRACTS.md secao 2.6).
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
    TranscriptPostRequest,
    TranscriptPostResponse,
    TurnEndRequest,
    TurnEndResponse,
    TurnState,
    WSStateMessage,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("relay.main")

# RNF04: teto de espera pelo motor de validação (real ou fallback). Cobre o
# caso que o try/except sozinho não cobre — o motor não lança exceção, só
# demora demais (ex: chamada à OpenAI pendurada). Sem isso, uma unica
# requisição de /api/transcript podia ficar esperando indefinidamente.
# Nota: asyncio.to_thread não cancela a thread de verdade ao estourar o
# timeout (Python não mata threads) — ela termina sozinha em segundo plano;
# o que este teto garante é que quem chamou não fica pendurado esperando.
VALIDATION_TIMEOUT_SECONDS = 8.0
AMBIGUOUS_WRITE_TIMEOUT_SECONDS = 1.5

app = FastAPI(title="Relay Orquestrador", version="0.2.0")

# Dashboard roda em outra origem (Next.js dev server) — sem auth no MVP (RNF03).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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

    Também aplica um teto de tempo (VALIDATION_TIMEOUT_SECONDS): motor que
    não lança exceção mas simplesmente não responde é tratado do mesmo jeito
    que uma falha — sem isso, quem chamou ficaria esperando indefinidamente.
    """
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(validation_client.analisar, transcript, items),
            timeout=VALIDATION_TIMEOUT_SECONDS,
        )
        return AnalyzeResponse(**raw)
    except asyncio.TimeoutError:
        logger.warning(
            "Motor de validacao nao respondeu em %.1fs para station_id=%s — seguindo com ultimo estado conhecido.",
            VALIDATION_TIMEOUT_SECONDS, station_id,
        )
        await store.push_error(station_id, "Motor de validação demorou demais — mantendo último estado conhecido (RNF04).")
        return None
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
            summary_bullets=[],
        )
    return result


# ---------------------------------------------------------------------------
# 4. POST /api/transcript — ingestão de fala (P1 -> P2), CONTRACTS.md secao 2.5
# ---------------------------------------------------------------------------


def _require_turn(station_id: str) -> StationTurn:
    turn = store.active_turn(station_id)
    if turn is None:
        raise HTTPException(status_code=404, detail="Estacao sem checklist configurado — chame POST /api/config antes.")
    return turn


@app.post("/api/transcript", response_model=TranscriptPostResponse)
async def post_transcript(line: TranscriptPostRequest) -> TranscriptPostResponse:
    async with store.lock_for(line.station_id):
        turn = _require_turn(line.station_id)
        turn.upsert_line(line.seq, line.speaker, line.text, line.ts)

        result = await _run_validation_safe(line.station_id, turn.transcript_text(), turn.items)
        if result is not None:
            turn.apply_analysis(result)
        await store.push_state(turn)

    return TranscriptPostResponse()


# ---------------------------------------------------------------------------
# 5. POST /api/turn/end — ÚNICO gatilho de fim de turno, CONTRACTS.md secao 2.6
# ---------------------------------------------------------------------------


@app.post("/api/turn/end", response_model=TurnEndResponse)
async def post_turn_end(request: TurnEndRequest) -> TurnEndResponse:
    async with store.lock_for(request.station_id):
        turn = store.current_turn(request.station_id)
        if turn is None:
            raise HTTPException(status_code=404, detail="Estacao sem checklist configurado — chame POST /api/config antes.")
        await _finish_turn(turn)

    return TurnEndResponse()


async def _finish_turn(turn: StationTurn) -> None:
    """
    Fim de turno (RF07/RF09): empurra o `state` final e dispara os DOIS
    eventos estruturados de encerramento — quem efetivamente toca o TTS e
    chama o webhook do Slack é P4.

    Não revalida aqui: toda ingestão de fala (`POST /api/transcript`) já roda
    a validação com a transcrição completa antes de retornar, então o estado
    do turno já está atualizado com a última fala no momento em que
    `POST /api/turn/end` chega. Uma estação encerrada sem nenhuma fala
    ingerida mantém o checklist zerado, que já é o estado correto para "nada
    foi dito ainda".
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

    # `slack_card` sempre dispara ao fim do turno, com o card PRONTO — P4 só
    # executa o POST ao Incoming Webhook (CONTRACTS.md secao 5, Revisão 2).
    await store.push_slack_card(turn)

    # RF08 não pode atrasar TTS, Slack nem a resposta de fim de turno. O
    # snapshot é capturado agora para não depender de uma eventual nova rodada
    # aberta para a mesma estação enquanto a escrita externa acontece.
    asyncio.create_task(_persist_ambiguous_safe(turn), name=f"ambiguous-turn-{turn.turn_id}")


async def _persist_ambiguous_safe(turn: StationTurn) -> None:
    """Grava o resultado estruturado na Ambiguous sem bloquear o fluxo principal (RNF04)."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                validation_client.persistir_turno,
                station_id=turn.station_id,
                turn_id=turn.turn_id,
                transcript=turn.transcript_text(),
                checklist_status=list(turn.checklist_status),
                is_complete=turn.is_complete,
                summary=turn.summary,
            ),
            timeout=AMBIGUOUS_WRITE_TIMEOUT_SECONDS,
        )
        if result is False:
            await store.push_error(turn.station_id, "Falha ao gravar turno na Ambiguous — seguindo normalmente (RNF04).")
    except asyncio.TimeoutError:
        logger.warning("Gravação na Ambiguous excedeu %.1fs para station_id=%s", AMBIGUOUS_WRITE_TIMEOUT_SECONDS, turn.station_id)
        await store.push_error(turn.station_id, "Ambiguous demorou demais para gravar o turno — seguindo normalmente (RNF04).")
    except Exception:
        logger.exception("Falha inesperada ao persistir turno na Ambiguous para station_id=%s", turn.station_id)
        await store.push_error(turn.station_id, "Falha ao gravar turno na Ambiguous — seguindo normalmente (RNF04).")


# ---------------------------------------------------------------------------
# 6. WS /ws/{station_id} — push real (CONTRACTS.md secao 3)
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
