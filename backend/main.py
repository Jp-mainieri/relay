"""
Relay — Orquestrador FastAPI (Fase 0 · stubs).

Objetivo desta fase: todo endpoint do CONTRACTS.md responde de verdade, com
dados fixos vindos de /mocks, para que P1/P3/P4 tenham algo real para
integrar contra enquanto o P2 implementa a lógica de negócio.

NÃO HÁ LÓGICA DE NEGÓCIO AQUI. Nenhuma chamada real a OpenAI, Ambiguous, TTS
ou Slack. Isso é substituído na próxima etapa (branch feat/orquestrador).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # habilita `import shared`

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.mock_data import load, load_ws_sequence
from shared.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChecklistConfig,
    ChecklistConfigResponse,
)

app = FastAPI(title="Relay Orquestrador", version="0.0.1-stub")

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


@app.post("/api/config", response_model=ChecklistConfigResponse)
def post_config(config: ChecklistConfig) -> ChecklistConfigResponse:
    """
    STUB (Fase 0): valida o shape via ChecklistConfig e ecoa de volta.
    Fase seguinte: persistir em memória (ver 05-arquitetura.md — sem banco no MVP).
    """
    return ChecklistConfigResponse(status="ok", station_id=config.station_id, items=config.items)


@app.post("/api/analyze", response_model=AnalyzeResponse)
def post_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    STUB (Fase 0): ignora o conteúdo real da transcrição e retorna o mock fixo
    de mocks/analyze_response.json. Valida que o input respeita AnalyzeRequest.

    Fase seguinte: chamar backend/validacao.py::analisar (P3) no lugar deste mock.
    """
    return AnalyzeResponse(**load("analyze_response.json"))


@app.websocket("/ws/{station_id}")
async def ws_channel(websocket: WebSocket, station_id: str) -> None:
    """
    STUB (Fase 0): ao conectar, replay da sequência fixa de mocks/ws_sequence/
    (estado inicial -> progresso -> final -> intervenção -> slack_sent), em
    loop, com um pequeno delay entre mensagens — o bastante para P4 exercitar
    a transição cinza->verde e os dois eventos únicos sem esperar o P2 real.

    `station_id` do path é aceito e ignorado nesta fase (mock é o mesmo para
    qualquer estação). Fase seguinte: state real por estação, indexado por
    station_id, com push a cada mudança de fato.
    """
    await websocket.accept()
    sequence = load_ws_sequence()
    try:
        while True:
            for message in sequence:
                await websocket.send_json(message)
                await asyncio.sleep(1.5)
            await asyncio.sleep(3)  # pausa entre replays do loop de demo
    except WebSocketDisconnect:
        # Reconexão é esperada e não deve gerar erro de servidor (ver CONTRACTS.md).
        return
