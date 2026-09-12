"""
Exemplo ponta a ponta da simulação de Slack, sem subir backend nem dashboard.

    python -m backend.scripts.slack_mock_demo
    python -m backend.scripts.slack_mock_demo --transcricao completa_padrao
    python -m backend.scripts.slack_mock_demo --offline

Percorre o mesmo caminho do sistema real: lê a transcrição de P1, monta o turno
como P2 monta, roda o motor de P3, e entrega o estado final a
`backend.slack_mock.simulate_send` — que grava o Block Kit em vez de fazer o
POST ao webhook.

Sobre o modo: por padrão chama o motor REAL (`backend.validacao.analisar`) e
deixa a exceção estourar. `--offline` chama `_fallback_response` diretamente —
e não `validation_client.analisar`, que tentaria o motor real primeiro e só
cairia no mock em caso de exceção. Os dois casos são rotulados na saída de
propósito: no sistema em execução, sucesso do motor e queda no fallback são
visualmente idênticos, e esse é o maior risco silencioso do projeto.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.slack_mock import DEFAULT_OUTPUT_DIR, simulate_send  # noqa: E402
from backend.state import StationTurn  # noqa: E402
from shared.schemas import AnalyzeResponse, SlackCardMessagePayload  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TRANSCRICOES_DIR = ROOT_DIR / "mocks" / "transcricoes"
CONFIG = ROOT_DIR / "mocks" / "config_request.json"

# As duas que o time considera confiáveis hoje. incompleta_sem_refrigerada é a
# que expõe o falso positivo do gpt-4o-mini — não entra como default.
DEFAULT_TRANSCRICAO = "empilhadeira2_problema"


def _carregar_turno(nome: str) -> StationTurn:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    turn = StationTurn.start(config["station_id"], config["items"])

    arquivo = TRANSCRICOES_DIR / f"{nome}.txt"
    if not arquivo.exists():
        disponiveis = ", ".join(sorted(p.stem for p in TRANSCRICOES_DIR.glob("*.txt")))
        raise SystemExit(f"Transcrição '{nome}' não existe. Disponíveis: {disponiveis}")

    ts = datetime.now(timezone.utc)
    for seq, linha in enumerate(l for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()):
        locutor, _, fala = linha.partition(":")
        if fala.strip():
            turn.upsert_line(seq, locutor.strip(), fala.strip(), ts)
        else:
            turn.upsert_line(seq, None, linha.strip(), ts)
    return turn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera um card simulado de Slack a partir de uma transcrição real.")
    parser.add_argument("--transcricao", default=DEFAULT_TRANSCRICAO, help="Nome do .txt em mocks/transcricoes, sem extensão.")
    parser.add_argument("--offline", action="store_true", help="Usa o fallback de mock em vez do motor real (garantidamente sem rede).")
    parser.add_argument("--out", type=Path, default=None, help=f"Diretório de saída (default: {DEFAULT_OUTPUT_DIR}).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    turn = _carregar_turno(args.transcricao)

    if args.offline:
        from backend import validation_client

        print("motor: FALLBACK DE MOCK (--offline) — o conteúdo abaixo não veio de um LLM")
        bruto = validation_client._fallback_response(turn.transcript_text(), turn.items)
    else:
        from backend.validacao import _get_client, analisar

        client, modelo = _get_client()
        print(f"motor: REAL — {client.base_url} | {modelo}")
        bruto = analisar(turn.transcript_text(), turn.items)

    turn.apply_analysis(AnalyzeResponse.model_validate(bruto))

    mensagem = SlackCardMessagePayload(station_id=turn.station_id, turn_id=turn.turn_id, card=turn.to_slack_card())
    entrega = simulate_send(mensagem, turn.to_state(), out_dir=args.out)

    print(f"transcrição: {args.transcricao} ({len(turn.transcript_log)} falas)")
    print(f"cobertura: {turn.coverage_pct()}%  is_complete={turn.is_complete}")
    print(f"webhook configurado no ambiente: {entrega.webhook_configured}")
    print(f"arquivo: {entrega.path}")
    print("\n--- corpo que teria sido enviado ao Incoming Webhook ---")
    print(json.dumps(entrega.body, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
