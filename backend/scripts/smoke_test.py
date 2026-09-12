"""
Smoke-test ponta a ponta do orquestrador (P2) com o player real de P1.

Sobe o backend, configura a estação, escuta o WebSocket como um dashboard
faria e injeta uma transcrição de /mocks/transcricoes fala por fala. No fim,
imprime a sequência de eventos e confere os invariantes do contrato
(CONTRACTS.md secoes 2.5, 2.6 e 3). Serve pro ensaio das 3:30 e pra qualquer
teste rápido depois de mexer no backend.

Uso (a partir da raiz do repo, com o venv ativo):

    python backend/scripts/smoke_test.py
    python backend/scripts/smoke_test.py --transcript mocks/transcricoes/completa_padrao.txt
    python backend/scripts/smoke_test.py --backend-url http://localhost:8000   # usa um backend já rodando

Sai com código 0 se PASSOU, 1 se FALHOU.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from websockets.sync.client import connect as ws_connect  # noqa: E402

from ingestion.parser import parse_transcript  # noqa: E402

DEFAULT_TRANSCRIPT = REPO_ROOT / "mocks" / "transcricoes" / "incompleta_sem_refrigerada.txt"
DEFAULT_CONFIG = REPO_ROOT / "mocks" / "config_request.json"


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _wait_health(base_url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.25)
    raise SystemExit(f"backend em {base_url} nao respondeu /health em {timeout}s")


def _listen(ws_url: str, received: list, done: threading.Event, idle_timeout: float) -> None:
    try:
        with ws_connect(ws_url) as ws:
            while not done.is_set():
                try:
                    raw = ws.recv(timeout=idle_timeout)
                except TimeoutError:
                    break
                msg = json.loads(raw)
                received.append(msg)
                if msg["type"] == "slack_card":
                    break
    except Exception as exc:  # o relatorio final mostra o que faltou
        received.append({"type": "_listener_error", "payload": {"message": str(exc)}})
    finally:
        done.set()


def _fmt_checklist(items: list[dict]) -> str:
    out = []
    for c in items:
        mark = "OK " if c["covered"] else "-- "
        ev = f'  <- "{c["evidence"]}"' if c.get("evidence") else ""
        out.append(f"      [{mark}] {c['item']}{ev}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", type=Path, default=DEFAULT_TRANSCRIPT)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="JSON de ChecklistConfig (station_id e sobrescrito por --station-id).")
    ap.add_argument("--station-id", default="doca-04")
    ap.add_argument("--delay", type=float, default=0.5, help="Segundos entre falas no player de P1.")
    ap.add_argument("--port", type=int, default=8765, help="Porta pra subir o backend (ignorado com --backend-url).")
    ap.add_argument("--backend-url", default=None, help="Usa um backend ja rodando em vez de subir um.")
    ap.add_argument("--idle-timeout", type=float, default=20.0, help="Segundos sem mensagem WS antes de desistir.")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # intercala certo com o stdout do player (subprocesso)

    lines = parse_transcript(args.transcript)
    n_lines = len(lines)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    config["station_id"] = args.station_id

    server = None
    base_url = args.backend_url
    if base_url is None:
        base_url = f"http://localhost:{args.port}"
        print(f"* subindo backend em {base_url} ...")
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(args.port), "--log-level", "warning"],
            cwd=REPO_ROOT,
        )
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/{args.station_id}"

    try:
        _wait_health(base_url)
        print(f"* backend ok. configurando '{args.station_id}' com {len(config['items'])} itens")
        _post(f"{base_url}/api/config", config)

        received: list[dict] = []
        done = threading.Event()
        listener = threading.Thread(target=_listen, args=(ws_url, received, done, args.idle_timeout), daemon=True)
        listener.start()
        time.sleep(0.5)  # garante que o snapshot de conexao chegou antes da 1a fala

        print(f"* rodando player de P1: {args.transcript.name} ({n_lines} falas, delay {args.delay}s)\n")
        player = subprocess.run(
            [sys.executable, "-m", "ingestion.cli", "--file", str(args.transcript), "--auto",
             "--station-id", args.station_id, "--delay", str(args.delay), "--backend-url", base_url],
            cwd=REPO_ROOT,
        )
        listener.join(timeout=args.idle_timeout + 5)
        done.set()
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    # ---- relatorio -------------------------------------------------------
    types = [m["type"] for m in received]
    states = [m for m in received if m["type"] == "state"]
    errors = [m for m in received if m["type"] in ("error", "_listener_error")]
    interventions = [m for m in received if m["type"] == "intervention"]
    cards = [m for m in received if m["type"] == "slack_card"]
    final = states[-1]["payload"] if states else None

    print("\n=== EVENTOS NO WEBSOCKET ===")
    print("  " + " -> ".join(types) if types else "  (nenhum)")
    if final:
        print(f"\n=== ESTADO FINAL (turno {final['turn_id'][:8]}) ===")
        print(f"  is_complete={final['is_complete']}  falas={len(final['transcript_log'])}  ambiguous_alert={final['ambiguous_alert']!r}")
        print(_fmt_checklist(final["checklist_status"]))
    for m in interventions:
        print(f"\n  [intervention] TTS falaria: \"{m['payload']['intervention_prompt']}\"")
    for m in cards:
        card = m["payload"]["card"]
        print(f"\n  [slack_card] coverage_pct={card['coverage_pct']}%  bullets={card['summary_bullets']}")
    for m in errors:
        print(f"\n  [{m['type']}] {m['payload']['message']}")

    checks = [
        ("player de P1 terminou sem erro", player.returncode == 0),
        ("exatamente 1 slack_card", len(cards) == 1),
        ("intervention so se is_complete=false (0 ou 1)",
         final is not None and len(interventions) == (0 if final["is_complete"] else 1)),
        (f"transcript_log com as {n_lines} falas em ordem de seq",
         final is not None and [l["seq"] for l in final["transcript_log"]] == list(range(n_lines))),
        (f"{n_lines + 2} mensagens state (snapshot + 1 por fala + final)", len(states) == n_lines + 2),
        ("nenhum evento error (motor nao degradou)", not errors),
    ]
    print("\n=== CHECKS ===")
    ok_all = True
    for label, ok in checks:
        ok_all &= ok
        print(f"  [{'PASSOU' if ok else 'FALHOU'}] {label}")
    print(f"\nRESULTADO: {'PASSOU' if ok_all else 'FALHOU'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
