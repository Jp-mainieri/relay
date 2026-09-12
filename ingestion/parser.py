"""
Relay — P1 · parser de transcrição de teste.

Lê um .txt de `mocks/transcricoes/` e devolve a lista de falas na ordem em
que aparecem no arquivo. Nenhuma dependência externa, nenhuma lógica de
negócio — só parsing de texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# "OPERADOR A: texto" — locutor é tudo antes do primeiro ":", sem espaços
# internos problemáticos (nomes de locutor são curtos, ex: "OPERADOR A",
# "GESTOR"). Se a linha não casar, speaker fica None e o texto é a linha
# inteira (regra do CONTRACTS.md: "o contrato permite speaker=null").
_SPEAKER_LINE = re.compile(r"^([A-ZÀ-Ú][A-ZÀ-Ú0-9 ]{0,30}):\s*(.+)$")


@dataclass(frozen=True)
class ParsedLine:
    speaker: str | None
    text: str


def parse_transcript(path: str | Path) -> list[ParsedLine]:
    """
    Parseia um arquivo de transcrição no formato "LOCUTOR: fala", uma fala
    por linha. Linhas vazias (ou só espaço) são ignoradas. Uma linha sem o
    prefixo de locutor vira ParsedLine(speaker=None, text=<linha inteira>).
    """
    text = Path(path).read_text(encoding="utf-8")
    lines: list[ParsedLine] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SPEAKER_LINE.match(line)
        if match:
            speaker, fala = match.group(1).strip(), match.group(2).strip()
            lines.append(ParsedLine(speaker=speaker, text=fala))
        else:
            lines.append(ParsedLine(speaker=None, text=line))
    return lines


def list_transcripts(mocks_dir: str | Path) -> list[Path]:
    """Lista os .txt disponíveis em mocks/transcricoes/, ordenados por nome."""
    return sorted(Path(mocks_dir).glob("*.txt"))
