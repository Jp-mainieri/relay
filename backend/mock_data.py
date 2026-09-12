"""
Carrega os payloads fixos de /mocks para alimentar os stubs de endpoint na
Fase 0. Nenhuma lógica de negócio aqui — só leitura de arquivo.

P2 substitui os `return` dos stubs em main.py pela lógica real; este módulo
some (ou vira fixture de teste) quando isso acontecer.
"""

import json
from pathlib import Path

MOCKS_DIR = Path(__file__).resolve().parent.parent / "mocks"


def load(*relative_path: str) -> dict:
    path = MOCKS_DIR.joinpath(*relative_path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_ws_sequence() -> list[dict]:
    """Mensagens WS na ordem em que o stub deve emiti-las (nomes 01_.. a 05_..)."""
    seq_dir = MOCKS_DIR / "ws_sequence"
    files = sorted(seq_dir.glob("*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]
