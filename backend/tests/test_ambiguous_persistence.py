"""Integração P2→P3 para a escrita Ambiguous, sem rede."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import backend.main as main
from backend.state import StationTurn


def _turn() -> StationTurn:
    turn = StationTurn.start("doca-04", ["bateria"])
    turn.upsert_line(0, "OPERADOR A", "A empilhadeira 2 está com problema de recarga.", datetime.now(timezone.utc))
    turn.summary = "Empilhadeira 2 com recarga pendente."
    return turn


def test_persistencia_recebe_snapshot_estruturado(monkeypatch):
    received = {}

    def persistir(**kwargs):
        received.update(kwargs)
        return True

    monkeypatch.setattr(main.validation_client, "persistir_turno", persistir)
    asyncio.run(main._persist_ambiguous_safe(_turn()))

    assert received["station_id"] == "doca-04"
    assert received["turn_id"]
    assert received["transcript"] == "OPERADOR A: A empilhadeira 2 está com problema de recarga."
    assert received["summary"] == "Empilhadeira 2 com recarga pendente."


def test_falha_de_persistencia_emite_erro_sem_lancar(monkeypatch):
    errors = []

    def persistir(**kwargs):
        return False

    async def push_error(station_id: str, message: str):
        errors.append((station_id, message))

    monkeypatch.setattr(main.validation_client, "persistir_turno", persistir)
    monkeypatch.setattr(main.store, "push_error", push_error)
    asyncio.run(main._persist_ambiguous_safe(_turn()))

    assert errors == [("doca-04", "Falha ao gravar turno na Ambiguous — seguindo normalmente (RNF04).")]
