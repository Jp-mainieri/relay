"""Testes determinísticos do contrato P3, sem chamar a rede ou a OpenAI."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.validacao import ValidationEngineError, _analisar_com_cliente
from shared.schemas import AnalyzeResponse


ROOT_DIR = Path(__file__).resolve().parent.parent


class _FakeCompletions:
    def __init__(self, response: AnalyzeResponse) -> None:
        self.response = response
        self.kwargs: dict | None = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(refusal=None, parsed=self.response)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeClient:
    def __init__(self, response: AnalyzeResponse) -> None:
        self.completions = _FakeCompletions(response)
        self.chat = SimpleNamespace(completions=self.completions)


class ValidacaoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = json.loads((ROOT_DIR / "mocks" / "analyze_request.json").read_text(encoding="utf-8"))
        self.response = AnalyzeResponse.model_validate_json(
            (ROOT_DIR / "mocks" / "analyze_response.json").read_text(encoding="utf-8")
        )

    def test_aceita_evidencias_literais_e_forca_sem_historico(self) -> None:
        client = _FakeClient(self.response)

        result = _analisar_com_cliente(
            self.request["transcript"], self.request["items"], client, model="modelo-de-teste"
        )

        self.assertIsNone(result["ambiguous_alert"])
        self.assertEqual(result["checklist_status"], self.response.model_dump(mode="json")["checklist_status"])
        self.assertEqual(client.completions.kwargs["response_format"], AnalyzeResponse)
        self.assertEqual(client.completions.kwargs["temperature"], 0)
        self.assertEqual(client.completions.kwargs["model"], "modelo-de-teste")
        sent_data = json.loads(client.completions.kwargs["messages"][1]["content"])
        self.assertEqual(sent_data, {"checklist_items": self.request["items"], "transcript": self.request["transcript"]})

    def test_rejeita_falso_positivo_sem_evidencia_literal(self) -> None:
        invalid = self.response.model_copy(deep=True)
        invalid.checklist_status[0].evidence = "Carga refrigerada confirmada pelo sistema."
        client = _FakeClient(invalid)

        with self.assertRaisesRegex(ValidationEngineError, "evidência literal"):
            _analisar_com_cliente(self.request["transcript"], self.request["items"], client, model="modelo-de-teste")

    def test_rejeita_status_fora_da_ordem_do_checklist(self) -> None:
        invalid = self.response.model_copy(deep=True)
        invalid.checklist_status[0].item, invalid.checklist_status[1].item = (
            invalid.checklist_status[1].item,
            invalid.checklist_status[0].item,
        )
        client = _FakeClient(invalid)

        with self.assertRaisesRegex(ValidationEngineError, "reordenou"):
            _analisar_com_cliente(self.request["transcript"], self.request["items"], client, model="modelo-de-teste")


if __name__ == "__main__":
    unittest.main()
