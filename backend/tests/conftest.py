"""
Fixtures da suite do orquestrador (P2).

Os testes exercitam a LÓGICA DE ORQUESTRAÇÃO (estado do turno, ordenação por
seq, eventos WS, fim de turno, RNF04) — não a qualidade do motor de validação.
Por isso test_orquestrador.py substitui o motor por um dublê determinístico
(`fake_analisar`): um item conta como coberto se o texto dele aparece
literalmente em alguma fala. Isso mantém a suite independente de P3
(backend/validacao.py) e do conteúdo de mocks/analyze_response.json.

O fallback real de mock tem testes próprios em test_validation_client.py —
por isso o dublê NÃO é autouse aqui.
"""

from __future__ import annotations

import warnings

import pytest
from fastapi.testclient import TestClient

warnings.filterwarnings("ignore", message=".*httpx.*starlette.testclient.*")

import backend.main as main  # noqa: E402  (rootdir do pytest = raiz do repo, via backend/__init__.py)
from backend import validation_client  # noqa: E402
from backend.state import store  # noqa: E402


def fake_analisar(transcricao: str, itens: list[str]) -> dict:
    lines = transcricao.splitlines()
    status = []
    for item in itens:
        hit = next((l for l in lines if item.lower() in l.lower()), None)
        status.append({"item": item, "covered": hit is not None, "evidence": hit})
    complete = bool(status) and all(s["covered"] for s in status)
    pending = [s["item"] for s in status if not s["covered"]]
    return {
        "checklist_status": status,
        "is_complete": complete,
        "intervention_prompt": None if complete else f"Faltou confirmar: {', '.join(pending)}",
        "ambiguous_alert": "Historico: empilhadeira 2 reincidente." if "empilhadeira" in transcricao.lower() else None,
        "summary": "resumo de teste",
        "summary_bullets": ["bullet 1", "bullet 2"],
    }


@pytest.fixture(autouse=True)
def clean_store():
    """Estado em memória é um singleton de módulo — zera entre testes."""
    store._items.clear()
    store._turns.clear()
    store._sockets.clear()
    store._locks.clear()
    yield
    store._items.clear()
    store._turns.clear()
    store._sockets.clear()
    store._locks.clear()


@pytest.fixture
def fake_engine(monkeypatch):
    """Substitui o motor pelo dublê. Ativado por módulo (ver test_orquestrador.py), não globalmente."""
    monkeypatch.setattr(validation_client, "analisar", fake_analisar)


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def post_line(client):
    def _post(station_id: str, seq: int, text: str, speaker: str | None = "OPERADOR A"):
        r = client.post(
            "/api/transcript",
            json={"station_id": station_id, "seq": seq, "speaker": speaker, "text": text, "ts": "2026-09-12T12:00:00Z"},
        )
        assert r.status_code == 200, r.text
        return r

    return _post


@pytest.fixture
def configure(client):
    def _configure(station_id: str, items: list[str]):
        r = client.post("/api/config", json={"station_id": station_id, "items": items})
        assert r.status_code == 200, r.text
        return r

    return _configure


def drain_until(ws, wanted_type: str, limit: int = 50) -> list[dict]:
    """Lê mensagens do WS até (inclusive) a primeira do tipo pedido."""
    received = []
    for _ in range(limit):
        msg = ws.receive_json()
        received.append(msg)
        if msg["type"] == wanted_type:
            return received
    raise AssertionError(f"nao chegou mensagem '{wanted_type}' em {limit} leituras: {[m['type'] for m in received]}")
