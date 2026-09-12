"""
Cenários de integração do orquestrador (P2), rodando in-process via TestClient.

Espelha a bateria manual rodada contra a main (cenários 1–7) e acrescenta as
bordas: fim de turno em duplicidade, requisição malformada e estação sem config.
"""

from __future__ import annotations

import time

import pytest

import backend.main as main
from backend import validation_client
from backend.tests.conftest import drain_until, fake_analisar


@pytest.fixture(autouse=True)
def _motor_deterministico(fake_engine):
    """Todo teste deste módulo roda contra o dublê do conftest, não contra P3/mock."""


def _types(msgs):
    return [m["type"] for m in msgs]


def _last_state(msgs):
    return [m for m in msgs if m["type"] == "state"][-1]["payload"]


# ---------------------------------------------------------------------------
# 1. Turno completo -> sem intervention, com slack_card
# ---------------------------------------------------------------------------


def test_turno_completo_nao_emite_intervention_mas_emite_slack_card(client, configure, post_line):
    configure("doca-04", ["carga refrigerada", "doca liberada"])
    with client.websocket_connect("/ws/doca-04") as ws:
        ws.receive_json()  # snapshot de conexão
        post_line("doca-04", 0, "a carga refrigerada ja ta no plug")
        post_line("doca-04", 1, "doca liberada faz dez minutos")
        client.post("/api/turn/end", json={"station_id": "doca-04"}).raise_for_status()
        msgs = drain_until(ws, "slack_card")

    assert "intervention" not in _types(msgs)
    assert _types(msgs).count("slack_card") == 1
    assert _last_state(msgs)["is_complete"] is True
    card = msgs[-1]["payload"]["card"]
    assert card["coverage_pct"] == 100
    assert card["summary_bullets"] == ["bullet 1", "bullet 2"]
    assert msgs[-1]["payload"]["turn_id"] == _last_state(msgs)["turn_id"]


def test_turno_incompleto_emite_intervention_uma_vez_e_depois_slack_card(client, configure, post_line):
    configure("doca-04", ["carga refrigerada", "bateria das empilhadeiras"])
    with client.websocket_connect("/ws/doca-04") as ws:
        ws.receive_json()
        post_line("doca-04", 0, "a carga refrigerada ja ta no plug")
        client.post("/api/turn/end", json={"station_id": "doca-04"}).raise_for_status()
        msgs = drain_until(ws, "slack_card")

    types = _types(msgs)
    assert types.count("intervention") == 1
    assert types.index("intervention") < types.index("slack_card")
    intervention = next(m for m in msgs if m["type"] == "intervention")["payload"]
    assert intervention["intervention_prompt"] == "Faltou confirmar: bateria das empilhadeiras"
    assert msgs[-1]["payload"]["card"]["coverage_pct"] == 50
    assert _last_state(msgs)["is_complete"] is False


# ---------------------------------------------------------------------------
# 2. Reconexão traz o estado acumulado
# ---------------------------------------------------------------------------


def test_reconexao_recebe_snapshot_com_estado_acumulado(client, configure, post_line):
    configure("doca-04", ["x"])
    with client.websocket_connect("/ws/doca-04") as ws1:
        first = ws1.receive_json()
        assert first["payload"]["transcript_log"] == []

    for i in range(5):
        post_line("doca-04", i, f"fala {i}")

    with client.websocket_connect("/ws/doca-04") as ws2:
        snap = ws2.receive_json()

    log = snap["payload"]["transcript_log"]
    assert [l["seq"] for l in log] == [0, 1, 2, 3, 4]
    assert [l["text"] for l in log] == [f"fala {i}" for i in range(5)]


# ---------------------------------------------------------------------------
# 3. Dois clientes na mesma estação recebem os mesmos eventos
# ---------------------------------------------------------------------------


def test_dois_clientes_recebem_os_mesmos_eventos(client, configure, post_line):
    configure("doca-04", ["x"])
    with client.websocket_connect("/ws/doca-04") as ws_a, client.websocket_connect("/ws/doca-04") as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()
        for i in range(3):
            post_line("doca-04", i, f"fala {i}")
        seen_a = [ws_a.receive_json() for _ in range(3)]
        seen_b = [ws_b.receive_json() for _ in range(3)]

    def fingerprint(m):
        p = m["payload"]
        return (m["type"], p["turn_id"], len(p["transcript_log"]), p["is_complete"])

    assert [fingerprint(m) for m in seen_a] == [fingerprint(m) for m in seen_b]
    assert [len(m["payload"]["transcript_log"]) for m in seen_a] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 4. Isolamento entre estações
# ---------------------------------------------------------------------------


def test_estacoes_sao_isoladas(client, configure, post_line):
    configure("doca-04", ["x"])
    configure("doca-07", ["y"])
    with client.websocket_connect("/ws/doca-07") as ws07, client.websocket_connect("/ws/doca-04") as ws04:
        ws07.receive_json()
        ws04.receive_json()
        for i in range(3):
            post_line("doca-04", i, f"fala da 04 numero {i}")
        for _ in range(3):
            assert ws04.receive_json()["payload"]["station_id"] == "doca-04"

        # A PRIMEIRA mensagem que a doca-07 vê depois disso tem que ser a fala
        # dela mesma — prova que nada da doca-04 vazou pra esse canal antes.
        post_line("doca-07", 0, "fala da 07")
        msg07 = ws07.receive_json()

    assert msg07["payload"]["station_id"] == "doca-07"
    assert [l["text"] for l in msg07["payload"]["transcript_log"]] == ["fala da 07"]


# ---------------------------------------------------------------------------
# 5. Reconfigurar a estação zera o estado
# ---------------------------------------------------------------------------


def test_reconfigurar_estacao_zera_turno(client, configure, post_line):
    configure("doca-04", ["carga refrigerada"])
    post_line("doca-04", 0, "carga refrigerada ok")
    client.post("/api/turn/end", json={"station_id": "doca-04"}).raise_for_status()
    with client.websocket_connect("/ws/doca-04") as ws:
        before = ws.receive_json()["payload"]
    assert before["is_complete"] is True

    configure("doca-04", ["carga refrigerada"])
    with client.websocket_connect("/ws/doca-04") as ws:
        after = ws.receive_json()["payload"]

    assert after["turn_id"] != before["turn_id"]
    assert after["transcript_log"] == []
    assert after["is_complete"] is False
    assert all(not c["covered"] for c in after["checklist_status"])


# ---------------------------------------------------------------------------
# 6. Fora de ordem e retry idempotente
# ---------------------------------------------------------------------------


def test_seq_e_a_fonte_da_ordem_e_retry_nao_duplica(client, configure, post_line, monkeypatch):
    transcripts_seen = []

    def spy(transcricao, itens):
        transcripts_seen.append(transcricao)
        return fake_analisar(transcricao, itens)

    monkeypatch.setattr(validation_client, "analisar", spy)

    configure("doca-04", ["x"])
    post_line("doca-04", 3, "seq tres primeira vez")
    post_line("doca-04", 1, "seq um chegando depois")
    post_line("doca-04", 3, "seq tres de novo (retry)")

    with client.websocket_connect("/ws/doca-04") as ws:
        log = ws.receive_json()["payload"]["transcript_log"]

    assert [l["seq"] for l in log] == [1, 3]
    assert log[1]["text"] == "seq tres de novo (retry)"
    # o motor sempre recebe o texto já ordenado por seq, não por ordem de chegada
    assert transcripts_seen[-1] == "OPERADOR A: seq um chegando depois\nOPERADOR A: seq tres de novo (retry)"


# ---------------------------------------------------------------------------
# 7. Motor lento estoura o teto sem pendurar quem chamou (RNF04)
# ---------------------------------------------------------------------------


def test_motor_lento_estoura_timeout_e_mantem_ultimo_estado(monkeypatch):
    """
    Usa `with TestClient(...)` (portal/event loop persistente entre requisições)
    de propósito: sem isso o TestClient cria e destrói um loop por requisição,
    e o teardown do loop espera a thread do motor lento terminar — o que faria
    o teste medir um atraso que não existe no uvicorn de verdade.
    """

    def motor_lento(transcricao, itens):
        time.sleep(1.5)
        return {"checklist_status": [], "is_complete": True, "intervention_prompt": None,
                "ambiguous_alert": None, "summary": "", "summary_bullets": []}

    monkeypatch.setattr(validation_client, "analisar", motor_lento)
    monkeypatch.setattr(main, "VALIDATION_TIMEOUT_SECONDS", 0.3)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        client.post("/api/config", json={"station_id": "doca-04", "items": ["x"]}).raise_for_status()
        with client.websocket_connect("/ws/doca-04") as ws:
            ws.receive_json()
            t0 = time.monotonic()
            r = client.post("/api/transcript", json={"station_id": "doca-04", "seq": 0, "text": "fala"})
            elapsed = time.monotonic() - t0
            assert r.status_code == 200
            err = ws.receive_json()
            state = ws.receive_json()

    assert elapsed < 1.2, f"requisicao pendurou {elapsed:.2f}s — o teto de 0.3s nao foi respeitado"
    assert err["type"] == "error"
    assert "demorou" in err["payload"]["message"]
    assert state["type"] == "state"
    assert state["payload"]["is_complete"] is False  # resultado tardio do motor lento NAO foi aplicado
    assert [l["text"] for l in state["payload"]["transcript_log"]] == ["fala"]  # mas a fala nao se perdeu


def test_motor_que_lanca_excecao_nao_derruba_ingestao(client, configure, post_line, monkeypatch):
    def motor_quebrado(transcricao, itens):
        raise RuntimeError("pane total")

    monkeypatch.setattr(validation_client, "analisar", motor_quebrado)

    configure("doca-04", ["x"])
    with client.websocket_connect("/ws/doca-04") as ws:
        ws.receive_json()
        post_line("doca-04", 0, "fala")
        err = ws.receive_json()
        state = ws.receive_json()

    assert err["type"] == "error"
    assert state["type"] == "state"
    assert [l["text"] for l in state["payload"]["transcript_log"]] == ["fala"]
    assert all(not c["covered"] for c in state["payload"]["checklist_status"])


# ---------------------------------------------------------------------------
# Bordas: fim de turno em duplicidade, malformado, sem config
# ---------------------------------------------------------------------------


def test_turn_end_duas_vezes_nao_duplica_eventos(client, configure, post_line):
    configure("doca-04", ["x", "y"])
    with client.websocket_connect("/ws/doca-04") as ws:
        ws.receive_json()
        post_line("doca-04", 0, "x confirmado")
        client.post("/api/turn/end", json={"station_id": "doca-04"}).raise_for_status()
        first_end = drain_until(ws, "slack_card")

        r = client.post("/api/turn/end", json={"station_id": "doca-04"})
        assert r.status_code == 200

        # Próxima fala abre turno novo; a PRIMEIRA mensagem depois do 2o /end
        # tem que ser esse state — prova que o 2o /end não emitiu nada.
        post_line("doca-04", 0, "fala do turno seguinte")
        nxt = ws.receive_json()

    assert _types(first_end).count("intervention") == 1
    assert _types(first_end).count("slack_card") == 1
    assert nxt["type"] == "state"
    assert nxt["payload"]["turn_id"] != first_end[-1]["payload"]["turn_id"]
    assert [l["text"] for l in nxt["payload"]["transcript_log"]] == ["fala do turno seguinte"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/transcript", {"station_id": "doca-04", "seq": 0}),  # sem text
        ("/api/transcript", {"station_id": "doca-04", "seq": "abc", "text": "x"}),  # seq nao-inteiro
        ("/api/config", {"station_id": "doca-04", "items": []}),  # min_length=1
        ("/api/turn/end", {}),  # sem station_id
        ("/api/analyze", {"station_id": "doca-04", "items": ["a"]}),  # sem transcript
    ],
)
def test_requisicao_malformada_retorna_422(client, configure, path, body):
    configure("doca-04", ["x"])
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text


def test_estacao_sem_config_retorna_404(client):
    r = client.post("/api/transcript", json={"station_id": "nao-existe", "seq": 0, "text": "x"})
    assert r.status_code == 404
    r = client.post("/api/turn/end", json={"station_id": "nao-existe"})
    assert r.status_code == 404


def test_ws_antes_do_config_recebe_estado_vazio(client):
    with client.websocket_connect("/ws/ainda-sem-config") as ws:
        snap = ws.receive_json()
    assert snap["type"] == "state"
    assert snap["payload"]["station_id"] == "ainda-sem-config"
    assert snap["payload"]["checklist_status"] == []
    assert snap["payload"]["transcript_log"] == []


def test_analyze_stateless_usa_o_motor_e_nao_toca_no_estado(client, configure):
    configure("doca-04", ["carga refrigerada"])
    r = client.post("/api/analyze", json={
        "station_id": "doca-04", "items": ["carga refrigerada"], "transcript": "OPERADOR A: carga refrigerada ok",
    })
    assert r.status_code == 200
    assert r.json()["is_complete"] is True
    with client.websocket_connect("/ws/doca-04") as ws:
        snap = ws.receive_json()["payload"]
    assert snap["transcript_log"] == []  # /api/analyze nao alimenta o turno
    assert snap["is_complete"] is False
