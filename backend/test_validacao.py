"""Testes determinísticos do contrato P3, sem chamar a rede ou a OpenAI."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backend.validacao import (
    _ModelAnalysis,
    ValidationEngineError,
    _analisar_com_cliente,
    _get_client,
    _numeros,
    _separar_bullets_ancorados,
)
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
        self.model_response = _ModelAnalysis(
            checklist_status=[
                {"item": self.response.checklist_status[0].item, "covered": True, "evidence_line": 1},
                {"item": self.response.checklist_status[1].item, "covered": True, "evidence_line": 3},
                {"item": self.response.checklist_status[2].item, "covered": False, "evidence_line": None},
                {"item": self.response.checklist_status[3].item, "covered": False, "evidence_line": None},
            ],
            is_complete=self.response.is_complete,
            intervention_prompt=self.response.intervention_prompt,
            summary=self.response.summary,
            summary_bullets=self.response.summary_bullets,
        )

    def test_aceita_evidencias_literais_e_forca_sem_historico(self) -> None:
        client = _FakeClient(self.model_response)

        result = _analisar_com_cliente(
            self.request["transcript"], self.request["items"], client, model="modelo-de-teste"
        )

        self.assertIsNone(result["ambiguous_alert"])
        self.assertEqual(result["checklist_status"][0]["evidence"], "OPERADOR B: Tranquilo. A carga da Swift ja ta no plug 3, refrigerada certinha.")
        self.assertEqual(result["checklist_status"][1]["evidence"], "OPERADOR B: Ja, liberei a doca 4 faz uns 10 minutos.")
        self.assertEqual(client.completions.kwargs["response_format"], _ModelAnalysis)
        self.assertEqual(client.completions.kwargs["temperature"], 0)
        self.assertEqual(client.completions.kwargs["model"], "modelo-de-teste")
        sent_data = json.loads(client.completions.kwargs["messages"][1]["content"])
        self.assertEqual(sent_data["checklist_items"], self.request["items"])
        self.assertEqual(sent_data["transcript_lines"][1], {
            "index": 1,
            "text": "OPERADOR B: Tranquilo. A carga da Swift ja ta no plug 3, refrigerada certinha.",
        })

    def test_rejeita_indice_de_evidencia_inexistente(self) -> None:
        invalid = self.model_response.model_copy(deep=True)
        invalid.checklist_status[0].evidence_line = 99
        client = _FakeClient(invalid)

        with self.assertRaisesRegex(ValidationEngineError, "índice de fala inexistente"):
            _analisar_com_cliente(self.request["transcript"], self.request["items"], client, model="modelo-de-teste")

    def test_rejeita_status_fora_da_ordem_do_checklist(self) -> None:
        invalid = self.model_response.model_copy(deep=True)
        invalid.checklist_status[0].item, invalid.checklist_status[1].item = (
            invalid.checklist_status[1].item,
            invalid.checklist_status[0].item,
        )
        client = _FakeClient(invalid)

        with self.assertRaisesRegex(ValidationEngineError, "reordenou"):
            _analisar_com_cliente(self.request["transcript"], self.request["items"], client, model="modelo-de-teste")


class BulletsAncoradosTests(unittest.TestCase):
    """`summary_bullets` vai direto para o card do Slack sem passar pela cópia
    literal que protege `evidence` — a ancoragem numérica é o que sobra."""

    setUp = ValidacaoTests.setUp  # mesmos mocks congelados, sem reexecutar os testes da classe

    def test_percentual_nao_vira_o_numero_cem(self) -> None:
        self.assertNotIn(100, _numeros("Bateria em 60 por cento."))
        self.assertIn(100, _numeros("Checklist cem por cento coberto."))

    def test_extrai_numero_por_extenso_e_em_digito(self) -> None:
        self.assertEqual(_numeros("A dois ta em setenta"), {2, 70})
        self.assertEqual(_numeros("Nivel de bateria: 70 e 83"), {70, 83})

    def test_compoe_dezena_com_unidade_na_ordem_do_portugues(self) -> None:
        self.assertIn(83, _numeros("a quatro em oitenta e tres"))

    def test_nao_compoe_na_ordem_invertida(self) -> None:
        # "Livre desde seis e vinte" e um horario (6:20); somar daria um 26
        # que ninguem disse.
        numeros = _numeros("Livre desde seis e vinte")
        self.assertEqual(numeros, {6, 20})

    def test_digito_no_bullet_casa_com_extenso_na_transcricao(self) -> None:
        mantidos, descartados = _separar_bullets_ancorados(
            ["Bateria em 60 por cento."], "OPERADOR B: Sessenta, mas sem forcar ela vai."
        )
        self.assertEqual(mantidos, ["Bateria em 60 por cento."])
        self.assertEqual(descartados, [])

    def test_bullet_com_numero_inventado_e_descartado_sem_derrubar_a_analise(self) -> None:
        analysis = self.model_response.model_copy(deep=True)
        analysis.summary_bullets = ["Bateria em 95 por cento.", *self.response.summary_bullets]
        client = _FakeClient(analysis)

        result = _analisar_com_cliente(
            self.request["transcript"], self.request["items"], client, model="modelo-de-teste"
        )

        self.assertNotIn("Bateria em 95 por cento.", result["summary_bullets"])
        self.assertEqual(result["summary_bullets"], list(self.response.summary_bullets))
        # O resto da analise sobrevive: derrubar tudo jogaria P2 no fallback de
        # mock, trocando um bullet ruim por um checklist inteiro ficticio.
        self.assertEqual(len(result["checklist_status"]), len(self.request["items"]))

    def test_analise_sem_nenhum_bullet_ancorado_e_recusada(self) -> None:
        analysis = self.model_response.model_copy(deep=True)
        analysis.summary_bullets = ["Bateria em 95 por cento.", "Doca 77 liberada."]
        client = _FakeClient(analysis)

        with self.assertRaisesRegex(ValidationEngineError, "ancorados"):
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
