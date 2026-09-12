"""
Relay — Orquestrador (P2): estado do turno em memória.

Sem banco no MVP (ver 05-arquitetura.md) — um turno ativo por estação,
guardado em memória do processo, mais o registro dos WebSockets conectados
por estação para poder empurrar `state`/`intervention`/`slack_card`/`error`
(ver CONTRACTS.md, seção 3, Revisão 2) a quem estiver ouvindo.

Nada aqui é contrato congelado — é implementação interna da fronteira do
orquestrador (P2). Os *payloads* que saem daqui (TurnState, InterventionPayload,
SlackCardMessagePayload, ErrorPayload) são os tipos congelados de `shared/schemas.py`.
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
    SlackCardMessagePayload,
    SlackCardPayload,
    TranscriptLine,
    TurnState,
    WSErrorMessage,
    WSInterventionMessage,
    WSSlackCardMessage,
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
    summary_bullets: list[str] = field(default_factory=list)
    intervention_prompt: Optional[str] = None
    ended: bool = False
    intervention_sent: bool = False
    _lines_by_seq: dict[int, TranscriptLine] = field(default_factory=dict, repr=False)

    @classmethod
    def start(cls, station_id: str, items: list[str]) -> "StationTurn":
        return cls(
            station_id=station_id,
            items=list(items),
            checklist_status=[ChecklistItemStatus(item=i, covered=False, evidence=None) for i in items],
        )

    def upsert_line(self, seq: int, speaker: Optional[str], text: str, ts: datetime) -> TranscriptLine:
        """
        Insere (ou substitui, se `seq` já existia — retry idempotente de P1)
        uma fala pelo `seq` que P1 atribuiu. `seq` é a fonte da verdade de
        ordem (CONTRACTS.md secao 2.5), não a ordem de chegada do HTTP.
        """
        line = TranscriptLine(seq=seq, speaker=speaker, text=text, ts=ts)
        self._lines_by_seq[seq] = line
        return line

    @property
    def transcript_log(self) -> list[TranscriptLine]:
        return [self._lines_by_seq[seq] for seq in sorted(self._lines_by_seq)]

    def transcript_text(self) -> str:
        """Formato definido em CONTRACTS.md secao 2.5: 'LOCUTOR: fala', uma por linha, ordenado por seq."""
        lines = []
        for l in self.transcript_log:
            lines.append(f"{l.speaker}: {l.text}" if l.speaker else l.text)
        return "\n".join(lines)

    def apply_analysis(self, analysis: AnalyzeResponse) -> None:
        """
        Aplica o resultado do motor ao turno.

        `checklist_status` confia sempre na última resposta do motor, sem
        travar itens como cobertos permanentemente. Chegamos a testar um
        merge "trava uma vez coberto" (um item nunca regride a
        covered=false) para evitar itens "piscando" entre coberto e não
        coberto quando o motor reanalisa a transcrição do zero a cada fala.
        Revertido: ao vivo, um item foi marcado covered=true com evidência
        sendo a PERGUNTA sobre ele ("...foi confirmado?"), não a resposta —
        e a resposta real, na fala seguinte, negava a cobertura ("Não, não
        foi conferido"). A trava teria escondido esse falso positivo pelo
        resto do turno. Falso positivo permanente é estritamente pior que
        piscar: falso positivo é o erro mais grave do projeto (CONTRACTS.md),
        e piscar pelo menos é visível e se autocorrige com mais contexto. A
        correção de verdade é o motor (P3) validar que a evidência é sobre o
        item certo, não só que o texto existe literalmente na transcrição.
        """
        self.checklist_status = analysis.checklist_status
        self.is_complete = analysis.is_complete
        self.ambiguous_alert = analysis.ambiguous_alert
        self.summary = analysis.summary
        if analysis.summary_bullets:
            self.summary_bullets = analysis.summary_bullets
        if analysis.intervention_prompt:
            self.intervention_prompt = analysis.intervention_prompt

    def coverage_pct(self) -> int:
        if not self.checklist_status:
            return 0
        covered = sum(1 for c in self.checklist_status if c.covered)
        return round(100 * covered / len(self.checklist_status))

    def to_slack_card(self) -> SlackCardPayload:
        bullets = self.summary_bullets or ([self.summary] if self.summary else [])
        return SlackCardPayload(
            station_id=self.station_id,
            timestamp=_utcnow(),
            coverage_pct=self.coverage_pct(),
            ambiguous_alert=self.ambiguous_alert,
            summary_bullets=bullets,
        )

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

    async def push_slack_card(self, turn: StationTurn) -> None:
        """
        `slack_card` (renomeado de `slack_sent` na Revisão 2): P2 monta e
        entrega o SlackCardPayload PRONTO; P4 só faz o POST ao webhook.
        """
        payload = SlackCardMessagePayload(station_id=turn.station_id, turn_id=turn.turn_id, card=turn.to_slack_card())
        await self._broadcast(turn.station_id, WSSlackCardMessage(payload=payload).model_dump(mode="json"))

    async def push_error(self, station_id: str, message: str) -> None:
        payload = ErrorPayload(station_id=station_id, message=message)
        await self._broadcast(station_id, WSErrorMessage(payload=payload).model_dump(mode="json"))


store = StationStore()
