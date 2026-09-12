"""
Relay — Orquestrador (P2): estado do turno em memória.

Sem banco no MVP (ver 05-arquitetura.md) — um turno ativo por estação,
guardado em memória do processo, mais o registro dos WebSockets conectados
por estação para poder empurrar `state`/`intervention`/`slack_sent`/`error`
(ver CONTRACTS.md, seção 3) a quem estiver ouvindo.

Nada aqui é contrato congelado — é implementação interna da fronteira do
orquestrador (P2). Os *payloads* que saem daqui (TurnState, InterventionPayload,
SlackSentPayload, ErrorPayload) são os tipos congelados de `shared/schemas.py`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket

from shared.schemas import (
    AnalyzeResponse,
    ChecklistItemStatus,
    ErrorPayload,
    InterventionPayload,
    SlackSentPayload,
    TranscriptLine,
    TurnState,
    WSErrorMessage,
    WSInterventionMessage,
    WSSlackSentMessage,
    WSStateMessage,
    new_turn_id,
)

logger = logging.getLogger("relay.state")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StationTurn:
    """Turno em andamento (ou recém-encerrado) de uma estação."""

    station_id: str
    items: list[str]
    turn_id: str = field(default_factory=new_turn_id)
    checklist_status: list[ChecklistItemStatus] = field(default_factory=list)
    is_complete: bool = False
    ambiguous_alert: Optional[str] = None
    summary: str = ""
    intervention_prompt: Optional[str] = None
    transcript_log: list[TranscriptLine] = field(default_factory=list)
    ended: bool = False
    intervention_sent: bool = False

    @classmethod
    def start(cls, station_id: str, items: list[str]) -> "StationTurn":
        return cls(
            station_id=station_id,
            items=list(items),
            checklist_status=[ChecklistItemStatus(item=i, covered=False, evidence=None) for i in items],
        )

    def append_line(self, speaker: Optional[str], text: str) -> TranscriptLine:
        line = TranscriptLine(seq=len(self.transcript_log), speaker=speaker, text=text, ts=_utcnow())
        self.transcript_log.append(line)
        return line

    def transcript_text(self) -> str:
        """Formato definido em CONTRACTS.md: 'LOCUTOR: fala', uma por linha."""
        lines = []
        for l in self.transcript_log:
            lines.append(f"{l.speaker}: {l.text}" if l.speaker else l.text)
        return "\n".join(lines)

    def apply_analysis(self, analysis: AnalyzeResponse) -> None:
        self.checklist_status = analysis.checklist_status
        self.is_complete = analysis.is_complete
        self.ambiguous_alert = analysis.ambiguous_alert
        self.summary = analysis.summary
        if analysis.intervention_prompt:
            self.intervention_prompt = analysis.intervention_prompt

    def to_state(self) -> TurnState:
        return TurnState(
            station_id=self.station_id,
            turn_id=self.turn_id,
            checklist_status=self.checklist_status,
            is_complete=self.is_complete,
            ambiguous_alert=self.ambiguous_alert,
            summary=self.summary,
            transcript_log=self.transcript_log,
            updated_at=_utcnow(),
        )


def _empty_state(station_id: str) -> TurnState:
    """Estado inicial vazio para um cliente que conecta antes de /api/config (CONTRACTS.md secao 3)."""
    return TurnState(
        station_id=station_id,
        turn_id="",
        checklist_status=[],
        is_complete=False,
        ambiguous_alert=None,
        summary="",
        transcript_log=[],
        updated_at=_utcnow(),
    )


class StationStore:
    """Estado do orquestrador em memória durante a sessão (uma instância por processo)."""

    def __init__(self) -> None:
        self._items: dict[str, list[str]] = {}
        self._turns: dict[str, StationTurn] = {}
        self._sockets: dict[str, set[WebSocket]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, station_id: str) -> asyncio.Lock:
        return self._locks.setdefault(station_id, asyncio.Lock())

    def configure(self, station_id: str, items: list[str]) -> StationTurn:
        """POST /api/config: persiste os itens e abre um turno novo e limpo para a estação."""
        self._items[station_id] = list(items)
        turn = StationTurn.start(station_id, items)
        self._turns[station_id] = turn
        return turn

    def items_for(self, station_id: str) -> Optional[list[str]]:
        return self._items.get(station_id)

    def current_turn(self, station_id: str) -> Optional[StationTurn]:
        return self._turns.get(station_id)

    def active_turn(self, station_id: str) -> Optional[StationTurn]:
        """
        Turno em que ingestão deve continuar: se o último terminou, abre um
        novo automaticamente (mesmo checklist), sem exigir novo POST /api/config.
        """
        items = self._items.get(station_id)
        if items is None:
            return None
        turn = self._turns.get(station_id)
        if turn is None or turn.ended:
            turn = StationTurn.start(station_id, items)
            self._turns[station_id] = turn
        return turn

    def snapshot_or_empty(self, station_id: str) -> TurnState:
        turn = self._turns.get(station_id)
        return turn.to_state() if turn is not None else _empty_state(station_id)

    def register_socket(self, station_id: str, ws: WebSocket) -> None:
        self._sockets.setdefault(station_id, set()).add(ws)

    def unregister_socket(self, station_id: str, ws: WebSocket) -> None:
        self._sockets.get(station_id, set()).discard(ws)

    async def _broadcast(self, station_id: str, message: dict) -> None:
        dead = []
        for ws in list(self._sockets.get(station_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister_socket(station_id, ws)

    async def push_state(self, turn: StationTurn) -> None:
        msg = WSStateMessage(payload=turn.to_state())
        await self._broadcast(turn.station_id, msg.model_dump(mode="json"))

    async def push_intervention(self, turn: StationTurn, prompt: str) -> None:
        payload = InterventionPayload(station_id=turn.station_id, turn_id=turn.turn_id, intervention_prompt=prompt)
        await self._broadcast(turn.station_id, WSInterventionMessage(payload=payload).model_dump(mode="json"))

    async def push_slack_sent(self, turn: StationTurn) -> None:
        payload = SlackSentPayload(station_id=turn.station_id, turn_id=turn.turn_id, summary=turn.summary)
        await self._broadcast(turn.station_id, WSSlackSentMessage(payload=payload).model_dump(mode="json"))

    async def push_error(self, station_id: str, message: str) -> None:
        payload = ErrorPayload(station_id=station_id, message=message)
        await self._broadcast(station_id, WSErrorMessage(payload=payload).model_dump(mode="json"))


store = StationStore()
