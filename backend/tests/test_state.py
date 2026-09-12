"""Unidades do estado em memória (backend/state.py) que não precisam de HTTP."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.state import StationTurn
from shared.schemas import AnalyzeResponse, ChecklistItemStatus

TS = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def test_transcript_text_segue_o_formato_do_contrato_ordenado_por_seq():
    turn = StationTurn.start("doca-04", ["x"])
    turn.upsert_line(2, "OPERADOR B", "terceira", TS)
    turn.upsert_line(0, "OPERADOR A", "primeira", TS)
    turn.upsert_line(1, None, "segunda sem locutor", TS)
    assert turn.transcript_text() == "OPERADOR A: primeira\nsegunda sem locutor\nOPERADOR B: terceira"


def test_upsert_mesmo_seq_substitui():
    turn = StationTurn.start("doca-04", ["x"])
    turn.upsert_line(0, "A", "v1", TS)
    turn.upsert_line(0, "A", "v2", TS)
    assert [l.text for l in turn.transcript_log] == ["v2"]


def test_coverage_pct_arredonda():
    turn = StationTurn.start("doca-04", ["a", "b", "c"])
    turn.checklist_status = [
        ChecklistItemStatus(item="a", covered=True, evidence="ok"),
        ChecklistItemStatus(item="b", covered=False),
        ChecklistItemStatus(item="c", covered=False),
    ]
    assert turn.coverage_pct() == 33
    assert StationTurn.start("vazia", []).coverage_pct() == 0


def test_slack_card_usa_summary_bullets_do_motor_ou_cai_no_summary():
    turn = StationTurn.start("doca-04", ["a"])
    turn.apply_analysis(AnalyzeResponse(
        checklist_status=[ChecklistItemStatus(item="a", covered=True, evidence="ok")],
        is_complete=True, intervention_prompt=None, ambiguous_alert="alerta",
        summary="resumo em prosa", summary_bullets=["b1", "b2"],
    ))
    card = turn.to_slack_card()
    assert card.summary_bullets == ["b1", "b2"]
    assert card.ambiguous_alert == "alerta"
    assert card.coverage_pct == 100

    turn.summary_bullets = []
    assert turn.to_slack_card().summary_bullets == ["resumo em prosa"]


def test_intervention_prompt_e_mantido_quando_motor_devolve_null():
    turn = StationTurn.start("doca-04", ["a"])
    turn.apply_analysis(AnalyzeResponse(
        checklist_status=[ChecklistItemStatus(item="a", covered=False)],
        is_complete=False, intervention_prompt="confirma o a?", ambiguous_alert=None,
        summary="s", summary_bullets=["s"],
    ))
    turn.apply_analysis(AnalyzeResponse(
        checklist_status=[ChecklistItemStatus(item="a", covered=False)],
        is_complete=False, intervention_prompt=None, ambiguous_alert=None,
        summary="s", summary_bullets=["s"],
    ))
    assert turn.intervention_prompt == "confirma o a?"


def test_item_coberto_nao_regride_se_motor_mudar_de_ideia():
    """
    O motor reanalisa a transcrição inteira do zero a cada fala, sem lembrar
    respostas anteriores, e não é 100% determinístico — pode dizer
    covered=true numa chamada e covered=false na seguinte pro MESMO item,
    mesmo a evidência continuando na transcrição. Uma vez coberto no turno,
    tem que travar.
    """
    turn = StationTurn.start("doca-04", ["a", "b"])
    turn.apply_analysis(AnalyzeResponse(
        checklist_status=[
            ChecklistItemStatus(item="a", covered=True, evidence="fala que comprova a"),
            ChecklistItemStatus(item="b", covered=False),
        ],
        is_complete=False, intervention_prompt="falta b", ambiguous_alert=None,
        summary="s", summary_bullets=["s"],
    ))
    assert turn.checklist_status[0].covered is True

    # motor "esquece" o item 'a' na proxima chamada (mesma fala continua na transcricao)
    turn.apply_analysis(AnalyzeResponse(
        checklist_status=[
            ChecklistItemStatus(item="a", covered=False),
            ChecklistItemStatus(item="b", covered=False),
        ],
        is_complete=False, intervention_prompt="falta a e b", ambiguous_alert=None,
        summary="s2", summary_bullets=["s2"],
    ))
    assert turn.checklist_status[0].covered is True, "item nao pode regredir de coberto para nao-coberto"
    assert turn.checklist_status[0].evidence == "fala que comprova a", "evidencia original deve ser preservada"
    assert turn.is_complete is False, "is_complete deve refletir o checklist travado, nao o do motor"

    # quando o motor finalmente cobre 'b' tambem, is_complete precisa virar True
    turn.apply_analysis(AnalyzeResponse(
        checklist_status=[
            ChecklistItemStatus(item="a", covered=False),  # motor "esquece" de novo, mas fica travado
            ChecklistItemStatus(item="b", covered=True, evidence="fala que comprova b"),
        ],
        is_complete=False, intervention_prompt=None, ambiguous_alert=None,
        summary="s3", summary_bullets=["s3"],
    ))
    assert [c.covered for c in turn.checklist_status] == [True, True]
    assert turn.is_complete is True
