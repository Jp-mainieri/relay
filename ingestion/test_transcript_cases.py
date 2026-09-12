"""Contratos mínimos dos casos de demonstração usados no ensaio ao vivo."""

from __future__ import annotations

import unittest
from pathlib import Path

from ingestion.parser import parse_transcript


ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "mocks" / "transcricoes"


class TranscriptCaseTests(unittest.TestCase):
    def _text(self, name: str) -> str:
        lines = parse_transcript(CASES / name)
        self.assertTrue(lines)
        self.assertTrue(all(line.speaker in {"OPERADOR A", "OPERADOR B"} for line in lines))
        return "\n".join(line.text for line in lines).casefold()

    def test_caso_completo_nomeia_todos_os_itens(self) -> None:
        text = self._text("completa_padrao.txt")
        for expected in (
            "status da carga refrigerada confirmado",
            "liberação da doca oito confirmada",
            "nível de bateria das empilhadeiras confirmado",
            "pendência de manutenção",
        ):
            self.assertIn(expected, text)

    def test_caso_incompleto_declara_a_pendencia_sem_ambiguidade(self) -> None:
        text = self._text("incompleta_sem_refrigerada.txt")
        self.assertIn("carga refrigerada não foi conferido", text)
        self.assertIn("carga refrigerada continua pendente", text)
        self.assertIn("nível de bateria confirmado", text)
        self.assertIn("avaria registrada", text)

    def test_caso_de_reincidencia_identifica_entidade_e_incidente(self) -> None:
        text = self._text("empilhadeira2_problema.txt")
        self.assertIn("empilhadeira dois tem problema de recarga", text)
        self.assertIn("pendência de manutenção da empilhadeira dois", text)
        self.assertIn("rodízio da empilhadeira dois", text)


if __name__ == "__main__":
    unittest.main()
