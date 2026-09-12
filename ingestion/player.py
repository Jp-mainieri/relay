"""
Relay — P1 · player de transcrição.

Injeta as falas de um arquivo `mocks/transcricoes/*.txt` no orquestrador
(P2), fala por fala, com delay entre elas — simulando uma passagem de turno
acontecendo ao vivo. Ao final, dispara POST /api/turn/end (CONTRACTS.md
seção 2.6): o ÚNICO gatilho de fim de turno do sistema.

Nenhuma lógica de negócio aqui: só ingestão e sequenciamento. Contratos
(TranscriptPostRequest, TurnEndRequest) em `shared/schemas.py`.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # habilita `import shared`

from ingestion.parser import ParsedLine, parse_transcript
from shared.schemas import TranscriptPostRequest, TurnEndRequest


class PlayerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"  # chegou ao fim natural e enviou turn/end
    STOPPED = "stopped"    # cancelado no meio (reset/stop) — turn/end NÃO foi enviado
    ERROR = "error"        # uma chamada HTTP falhou — playback abortado, turn/end NÃO foi enviado


def _now_iso_utc() -> str:
    """ISO 8601 em UTC, sufixo 'Z' (formato usado em todo o CONTRACTS.md)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TranscriptPlayer:
    """
    Um player por estação. Reentrante: `start()` sempre reinicia `seq` do
    zero e descarta qualquer estado da rodada anterior — rodar duas
    transcrições em sequência sem chamar `stop()`/`reset()` explicitamente
    não vaza nada, porque cada `start()` já é uma reinicialização completa.
    """

    def __init__(self, base_url: str, station_id: str, delay_seconds: float = 2.0, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.station_id = station_id
        self.delay_seconds = delay_seconds
        self.timeout = timeout

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._state = PlayerState.IDLE
        self._last_error: Optional[str] = None
        self._current_file: Optional[str] = None
        self._sent_count = 0

    # -- API pública ---------------------------------------------------

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        transcript_path: str | Path,
        on_line: Optional[Callable[[int, ParsedLine], None]] = None,
        on_finish: Optional[Callable[[PlayerState], None]] = None,
    ) -> None:
        """
        Inicia a reprodução em background (não bloqueia). Se já houver uma
        reprodução em andamento, cancela-a primeiro (auto-reset) — nunca
        deixa duas rodadas postando `seq` concorrentemente para a mesma
        estação.
        """
        with self._lock:
            if self.is_running():
                self._stop_locked()

            lines = parse_transcript(transcript_path)
            self._stop_event = threading.Event()
            self._state = PlayerState.RUNNING
            self._last_error = None
            self._current_file = str(transcript_path)
            self._sent_count = 0

            self._thread = threading.Thread(
                target=self._run, args=(lines, on_line, on_finish), daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """
        Cancela a reprodução em andamento, se houver. NÃO envia
        POST /api/turn/end — parar no meio não é um fim de turno de verdade,
        é o operador abortando a demo/ensaio.
        """
        with self._lock:
            self._stop_locked()

    def reset(self) -> None:
        """Alias de `stop()` — deixa o player pronto para um `start()` limpo."""
        self.stop()

    # -- Internals -------------------------------------------------------

    def _stop_locked(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.delay_seconds + self.timeout + 1)
        if self._state == PlayerState.RUNNING:
            self._state = PlayerState.STOPPED
        self._thread = None

    def _run(
        self,
        lines: list[ParsedLine],
        on_line: Optional[Callable[[int, ParsedLine], None]],
        on_finish: Optional[Callable[[PlayerState], None]],
    ) -> None:
        try:
            for seq, parsed in enumerate(lines):
                if self._stop_event.is_set():
                    self._state = PlayerState.STOPPED
                    return

                body = TranscriptPostRequest(
                    station_id=self.station_id,
                    seq=seq,
                    speaker=parsed.speaker,
                    text=parsed.text,
                    ts=_now_iso_utc(),
                )
                self._post("/api/transcript", body.model_dump(mode="json"))
                self._sent_count = seq + 1
                if on_line:
                    on_line(seq, parsed)

                is_last = seq == len(lines) - 1
                if not is_last:
                    # sleep interrompível: se pararem no meio da espera, sai já
                    if self._stop_event.wait(self.delay_seconds):
                        self._state = PlayerState.STOPPED
                        return

            # Fim natural da transcrição — ÚNICO ponto que dispara turn/end.
            end_body = TurnEndRequest(station_id=self.station_id)
            self._post("/api/turn/end", end_body.model_dump(mode="json"))
            self._state = PlayerState.FINISHED

        except requests.RequestException as exc:
            self._state = PlayerState.ERROR
            self._last_error = str(exc)
        finally:
            if on_finish:
                on_finish(self._state)

    def _post(self, path: str, json_body: dict) -> dict:
        resp = requests.post(f"{self.base_url}{path}", json=json_body, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
