"""
Simulação de envio ao Slack (backend/slack_mock.py).

Offline e determinístico: não chama LLM, não chama rede. O que importa aqui é
(a) o payload ser Block Kit válido para um Incoming Webhook, (b) a evidência
sair literal, e (c) a ausência de dado ser mostrada como ausência, nunca
preenchida com valor fixo.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.slack_mock import build_block_kit, simulate_send
from shared.schemas import (
    ChecklistItemStatus,
    SlackCardMessagePayload,
    SlackCardPayload,
    TurnState,
)

TS = datetime(2026, 9, 12, 12, 0, 22, tzinfo=timezone.utc)
FALA = "OPERADOR A: A carga da Swift ta no plug tres, refrigerada."


def _message(**card_overrides) -> SlackCardMessagePayload:
    card = SlackCardPayload(
        station_id="doca-04",
        timestamp=TS,
        coverage_pct=50,
        ambiguous_alert=card_overrides.pop("ambiguous_alert", None),
        summary_bullets=card_overrides.pop("summary_bullets", ["Carga refrigerada no plug 3."]),
    )
    return SlackCardMessagePayload(station_id="doca-04", turn_id="turno-1", card=card)


def _state(status: list[ChecklistItemStatus]) -> TurnState:
    return TurnState(
        station_id="doca-04",
        turn_id="turno-1",
        checklist_status=status,
        is_complete=all(s.covered for s in status),
        ambiguous_alert=None,
        summary="resumo",
    )


def _flat(body: dict) -> str:
    return json.dumps(body, ensure_ascii=False)


def test_body_tem_o_shape_que_o_incoming_webhook_espera():
    body = build_block_kit(_message())
    # O Slack recusa com invalid_payload qualquer corpo sem `text` ou `blocks`.
    assert isinstance(body["text"], str) and body["text"]
    assert isinstance(body["blocks"], list) and body["blocks"]
    assert body["blocks"][0]["type"] == "header"
    for bloco in body["blocks"]:
        assert bloco["type"] in {"header", "section", "divider", "context"}


def test_evidencia_sai_literal_sem_parafrase():
    state = _state([ChecklistItemStatus(item="status da carga refrigerada", covered=True, evidence=FALA)])
    body = build_block_kit(_message(), state)
    assert FALA in _flat(body)


def test_item_nao_coberto_aparece_como_faltante_e_sem_evidencia():
    state = _state([ChecklistItemStatus(item="status da carga refrigerada", covered=False, evidence=None)])
    texto = _flat(build_block_kit(_message(), state))
    assert "status da carga refrigerada" in texto
    assert "não mencionado" in texto


def test_reincidencia_ausente_e_declarada_em_vez_de_inventada():
    texto = _flat(build_block_kit(_message(ambiguous_alert=None)))
    assert "Sem alerta de reincidência" in texto
    assert "Reincidência\n" not in texto


def test_reincidencia_presente_entra_no_card():
    alerta = "Historico: Empilhadeira 2 apresentou falha de recarga nos ultimos 2 turnos."
    assert alerta in _flat(build_block_kit(_message(ambiguous_alert=alerta)))


def test_sem_turn_state_o_card_omite_o_checklist_em_vez_de_fabricar():
    texto = _flat(build_block_kit(_message()))
    assert "não mencionado" not in texto
    assert "white_check_mark" not in texto


def test_covered_sem_evidencia_e_denunciado_nao_mascarado():
    # Invariante do motor impede; se vazar, o card mostra o buraco.
    state = _state([ChecklistItemStatus(item="liberacao da doca", covered=True, evidence=None)])
    assert "sem evidência registrada" in _flat(build_block_kit(_message(), state))


def test_simulate_send_grava_arquivo_e_nao_toca_a_rede(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    state = _state([ChecklistItemStatus(item="status da carga refrigerada", covered=True, evidence=FALA)])

    entrega = simulate_send(_message(), state, out_dir=tmp_path)

    assert entrega.path == tmp_path / "turno_turno-1.json"
    gravado = json.loads(entrega.path.read_text(encoding="utf-8"))
    assert gravado["simulated"] is True
    assert gravado["webhook_configured"] is False
    assert gravado["body"] == entrega.body
    # O card de origem vai junto para a troca pelo POST real não remontar nada.
    assert gravado["source_card"]["coverage_pct"] == 50


def test_arquivo_gravado_nunca_carrega_a_url_do_webhook(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/SEGREDO/NAO/VAZAR")
    entrega = simulate_send(_message(), None, out_dir=tmp_path)
    assert entrega.webhook_configured is True
    assert "SEGREDO" not in entrega.path.read_text(encoding="utf-8")
