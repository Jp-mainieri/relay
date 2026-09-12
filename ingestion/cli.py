"""
Relay — P1 · controle ao vivo do player de transcrição.

REPL simples para rodar durante a demo/ensaio: escolher qual transcrição
tocar, iniciar, parar/resetar para rodar de novo do zero. Pensado para ser
operado por uma pessoa olhando o terminal enquanto o dashboard (P4) está
projetado — sem frescura de UI, só confiabilidade.

Uso:
    python -m ingestion.cli
    python -m ingestion.cli --station-id doca-04 --delay 1.5
    python -m ingestion.cli --backend-url http://localhost:8000 --file mocks/transcricoes/x.txt --auto
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.parser import ParsedLine, list_transcripts
from ingestion.player import PlayerState, TranscriptPlayer

MOCKS_TRANSCRICOES_DIR = Path(__file__).resolve().parent.parent / "mocks" / "transcricoes"


def _print_line(seq: int, parsed: ParsedLine) -> None:
    speaker = parsed.speaker or "(sem locutor)"
    print(f"  [{seq:02d}] {speaker}: {parsed.text}")


def _print_finish(player: TranscriptPlayer, state: PlayerState) -> None:
    if state == PlayerState.FINISHED:
        print("-- turno encerrado: POST /api/turn/end enviado --\n")
    elif state == PlayerState.STOPPED:
        print("-- reprodução interrompida (sem turn/end) --\n")
    elif state == PlayerState.ERROR:
        detail = player.last_error or "(sem detalhe capturado)"
        hint = ""
        if "404" in detail:
            hint = " Provável causa: estação sem checklist configurado — chame POST /api/config antes de iniciar a reprodução."
        print(f"-- ERRO durante a reprodução: {detail}{hint} --\n")


def _choose_file(files: list[Path]) -> Path | None:
    if not files:
        print(f"Nenhum .txt encontrado em {MOCKS_TRANSCRICOES_DIR}")
        return None
    print("\nTranscrições disponíveis:")
    for i, f in enumerate(files, start=1):
        print(f"  [{i}] {f.name}")
    raw = input("Escolha o número: ").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(files)):
        print("Escolha inválida.")
        return None
    return files[int(raw) - 1]


def run_repl(player: TranscriptPlayer) -> None:
    print(f"Relay · player de transcrição — estação '{player.station_id}', backend {player.base_url}")
    print("Comandos: [l]istar  [s]elecionar+iniciar  [r]eset/parar  [q]uit\n")
    selected: Path | None = None

    while True:
        status = "RODANDO" if player.is_running() else player.state.value.upper()
        cmd = input(f"[{status}]> ").strip().lower()

        if cmd in ("q", "quit", "sair"):
            player.stop()
            print("Até mais.")
            return

        if cmd in ("l", "listar"):
            files = list_transcripts(MOCKS_TRANSCRICOES_DIR)
            for i, f in enumerate(files, start=1):
                marker = " <-- selecionado" if f == selected else ""
                print(f"  [{i}] {f.name}{marker}")
            continue

        if cmd in ("s", "selecionar", "iniciar", "start"):
            files = list_transcripts(MOCKS_TRANSCRICOES_DIR)
            chosen = _choose_file(files)
            if chosen is None:
                continue
            selected = chosen
            print(f"Iniciando '{chosen.name}'...")
            player.start(chosen, on_line=_print_line, on_finish=lambda state: _print_finish(player, state))
            continue

        if cmd in ("r", "reset", "parar", "stop"):
            player.stop()
            print("Player resetado — pronto para rodar de novo do zero.")
            continue

        print("Comando não reconhecido. Use l / s / r / q.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Player de transcrição — P1 (Relay)")
    parser.add_argument("--backend-url", default="http://localhost:8000", help="Base URL do orquestrador (P2).")
    parser.add_argument("--station-id", default="doca-04", help="station_id a usar em todas as chamadas.")
    parser.add_argument("--delay", type=float, default=2.0, help="Segundos entre falas (default 2.0).")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout HTTP por chamada, em segundos.")
    parser.add_argument("--file", type=Path, default=None, help="Rodar direto este arquivo (modo não-interativo).")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Com --file: roda e sai ao final, sem abrir o REPL (útil em ensaio automatizado/CI).",
    )
    args = parser.parse_args()

    player = TranscriptPlayer(
        base_url=args.backend_url,
        station_id=args.station_id,
        delay_seconds=args.delay,
        timeout=args.timeout,
    )

    if args.file:
        print(f"Rodando '{args.file}' contra {args.backend_url} (estação '{args.station_id}')...")
        done = {"finished": False}

        def _on_finish(state: PlayerState) -> None:
            _print_finish(player, state)
            done["finished"] = True

        player.start(args.file, on_line=_print_line, on_finish=_on_finish)

        if args.auto:
            import time

            while not done["finished"]:
                time.sleep(0.2)
            sys.exit(0 if player.state == PlayerState.FINISHED else 1)

    run_repl(player)


if __name__ == "__main__":
    main()
