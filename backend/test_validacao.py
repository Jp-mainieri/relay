"""Testes determinísticos do contrato P3, sem chamar a rede ou a OpenAI."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backend.validacao import ValidationEngineError, _analisar_com_cliente, _get_client
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


class SelecaoDeProvedorTests(unittest.TestCase):
    """O caminho de contingência via OpenRouter não pode virar o padrão sem querer."""

    def setUp(self) -> None:
        self._original = {
            k: os.environ.get(k)
            for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "LLM_MODEL", "OPENAI_MODEL")
        }
        for k in self._original:
            os.environ.pop(k, None)
        # load_dotenv() não sobrescreve variáveis já definidas; um valor fixo
        # aqui impede que o .env local vaze para dentro do teste.
        os.environ["OPENAI_API_KEY"] = "chave-openai-de-teste"
        # _get_client() chama load_dotenv(); sem neutralizar isso o .env real da
        # máquina reinjeta credenciais e o teste deixa de testar o que promete.
        self._no_dotenv = mock.patch("backend.validacao.load_dotenv", lambda *a, **k: False)
        self._no_dotenv.start()

    def tearDown(self) -> None:
        self._no_dotenv.stop()
        for k, v in self._original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_usa_openai_por_padrao(self) -> None:
        _, model = _get_client()
        self.assertEqual(model, "gpt-4o-mini")

    def test_usa_openrouter_quando_a_credencial_existe(self) -> None:
        os.environ["OPENROUTER_API_KEY"] = "chave-openrouter-de-teste"
        client, model = _get_client()
        self.assertEqual(model, "openai/gpt-4o-mini")
        self.assertIn("openrouter.ai", str(client.base_url))

    def test_sem_nenhuma_credencial_falha_explicitamente(self) -> None:
        os.environ.pop("OPENAI_API_KEY")
        with self.assertRaisesRegex(ValidationEngineError, "Nenhuma credencial"):
            _get_client()


if __name__ == "__main__":
    unittest.main()
