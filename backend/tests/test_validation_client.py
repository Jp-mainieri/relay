"""
Fallback de mock do motor de validação (enquanto P3 não entrega
backend/validacao.py) e a camada RNF04 dentro dele.

Aqui NÃO usamos o dublê do conftest: o alvo é o fallback real.
"""

from __future__ import annotations

import pytest

from backend import validation_client
from shared.schemas import AnalyzeResponse

ITENS_DOCA_04 = [
    "status da carga refrigerada",
    "liberacao da doca",
    "nivel de bateria das empilhadeiras",
    "avarias ou pendencias de manutencao",
]


@pytest.fixture(autouse=True)
def usa_fallback_real(monkeypatch):
    # garante que estamos testando o fallback, e não um backend/validacao.py
    # que P3 possa ter entregue no meio do caminho
    monkeypatch.setattr(validation_client, "_analisar_real", None)


def test_fallback_produz_analyze_response_valido_para_o_mock_de_referencia():
    raw = validation_client.analisar("OPERADOR A: qualquer coisa", ITENS_DOCA_04)
    resp = AnalyzeResponse(**raw)
    assert [c.item for c in resp.checklist_status] == ITENS_DOCA_04
    assert resp.summary
    assert resp.summary_bullets
    assert resp.is_complete is False
    assert resp.intervention_prompt


def test_fallback_usa_heuristica_de_palavra_chave_para_itens_fora_do_mock():
    raw = validation_client.analisar("OPERADOR A: o portao ficou aberto", ["portao aberto", "gerador ligado"])
    by_item = {c["item"]: c for c in raw["checklist_status"]}
    assert by_item["portao aberto"]["covered"] is True
    assert by_item["gerador ligado"]["covered"] is False
    assert raw["is_complete"] is False
    assert raw["intervention_prompt"] is not None


def test_fallback_na_duvida_marca_false():
    raw = validation_client.analisar("OPERADOR A: nada a ver", ["item xyz"])
    assert raw["checklist_status"] == [{"item": "item xyz", "covered": False, "evidence": None}]


def test_ambiguous_alert_so_com_entidade_critica():
    sem = validation_client.analisar("OPERADOR A: doca liberada", ["x"])
    com = validation_client.analisar("OPERADOR A: a empilhadeira 2 falhou de novo", ["x"])
    assert sem["ambiguous_alert"] is None
    assert com["ambiguous_alert"]


def test_rnf04_falha_na_consulta_ambiguous_vira_none_e_nao_propaga(monkeypatch):
    def load_quebrado(*a, **k):
        raise ConnectionError("ambiguous fora do ar")

    # só a consulta de reincidência usa `load` por dentro de _mock_ambiguous_alert;
    # simulamos a falha lá e conferimos que o restante da análise segue de pé
    original = validation_client.load

    def load_seletivo(*args, **kwargs):
        import inspect
        caller = inspect.stack()[1].function
        if caller == "_mock_ambiguous_alert":
            raise ConnectionError("ambiguous fora do ar")
        return original(*args, **kwargs)

    monkeypatch.setattr(validation_client, "load", load_seletivo)
    raw = validation_client.analisar("OPERADOR A: a empilhadeira 2 falhou", ITENS_DOCA_04)
    assert raw["ambiguous_alert"] is None
    AnalyzeResponse(**raw)  # resto continua válido


def test_motor_real_que_falha_cai_para_o_fallback(monkeypatch):
    def motor_quebrado(transcricao, itens):
        raise RuntimeError("openai fora do ar")

    monkeypatch.setattr(validation_client, "_analisar_real", motor_quebrado)
    raw = validation_client.analisar("OPERADOR A: x", ITENS_DOCA_04)
    AnalyzeResponse(**raw)
