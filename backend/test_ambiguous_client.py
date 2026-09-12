"""Testes offline da integração Ambiguous: nenhum deles faz requisição de rede."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.ambiguous_client import (
    AmbiguousClient,
    RECORD_TITLE_PREFIX,
    extract_critical_entities,
    extract_new_incidents,
)
from shared.schemas import AmbiguousTurnRecord, ChecklistItemStatus


class AmbiguousClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = AmbiguousClient("not-a-real-key", "https://app.ambiguous.ai", 1.5)

    def test_extrai_entidades_criticas_sem_repetir(self) -> None:
        entities = extract_critical_entities("A empilhadeira 2 falhou; a doca 5 está livre. Empilhadeira 2 de novo.")
        self.assertEqual(entities, ["empilhadeira 2", "doca 5"])

    def test_so_cria_incidente_com_indicio_explicito(self) -> None:
        transcript = "A empilhadeira 2 está com problema de recarga. A doca 5 está livre."
        incidents = extract_new_incidents(transcript, ["empilhadeira 2", "doca 5"])
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].entity, "empilhadeira 2")

    def test_busca_reincidencia_filtra_documentos_do_relay(self) -> None:
        payload = {
            "data": [
                {"id": "a", "module": "docs", "title": f"{RECORD_TITLE_PREFIX} doca-04 | 2026-09-12 | empilhadeira 2"},
                {"id": "b", "module": "docs", "title": f"{RECORD_TITLE_PREFIX} doca-07 | 2026-09-11 | empilhadeira 2"},
                {"id": "c", "module": "docs", "title": "Documento sem relação com o Relay"},
            ]
        }
        with patch.object(AmbiguousClient, "_request_json", return_value=payload) as request:
            alert = self.client.find_recurrence(
                ["empilhadeira 2"], since=datetime(2026, 9, 5, tzinfo=timezone.utc)
            )

        self.assertEqual(alert, "Histórico Ambiguous: empilhadeira 2 apareceu em 2 registros nos últimos 7 dias.")
        self.assertEqual(request.call_args.args[:2], ("POST", "/api/search"))
        self.assertEqual(request.call_args.args[2]["modules"], ["docs"])

    def test_gravacao_cria_documento_com_registro_estruturado_sem_transcricao(self) -> None:
        record = AmbiguousTurnRecord(
            station_id="doca-04",
            turn_id="turn-1",
            timestamp=datetime(2026, 9, 12, tzinfo=timezone.utc),
            checklist_status=[ChecklistItemStatus(item="bateria", covered=False, evidence=None)],
            is_complete=False,
            summary="Bateria pendente.",
        )
        with patch.object(AmbiguousClient, "_request_json", return_value={"id": "doc-1"}) as request:
            self.client.create_turn_record(record, ["empilhadeira 2"])

        body = request.call_args.args[2]
        self.assertEqual(request.call_args.args[:2], ("POST", "/api/documents"))
        self.assertIn("empilhadeira 2", body["title"])
        self.assertIn('"turn_id": "turn-1"', body["content"])
        self.assertNotIn("OPERADOR", body["content"])


if __name__ == "__main__":
    unittest.main()
