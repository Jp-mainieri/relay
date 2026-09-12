"""Cliente resiliente para a memória longitudinal na Ambiguous.

O contrato do Relay guarda cada turno como um documento Markdown contendo o
``AmbiguousTurnRecord`` em JSON. Isso usa apenas os endpoints públicos e
estáveis da Ambiguous: ``POST /api/search`` para leitura e
``POST /api/documents`` para escrita.

Falhar na memória nunca é motivo para falhar a passagem de turno: os métodos
públicos retornam ``None``/``False`` e registram o motivo sem incluir tokens
nem corpos de resposta possivelmente sensíveis no log.
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv

from shared.schemas import AmbiguousTurnRecord, ChecklistItemStatus, IncidentReport


logger = logging.getLogger("relay.ambiguous")

DEFAULT_BASE_URL = "https://app.ambiguous.ai"
# A leitura ocorre no caminho da validação; deve continuar curta para não
# atrasar a atualização do checklist. A escrita, por sua vez, ocorre depois do
# fim de turno em uma tarefa separada: pode receber um orçamento maior sem
# bloquear TTS, Slack ou a resposta HTTP de encerramento.
DEFAULT_READ_TIMEOUT_SECONDS = 1.5
DEFAULT_WRITE_TIMEOUT_SECONDS = 8.0
MAX_READ_TIMEOUT_SECONDS = 1.5
MAX_WRITE_TIMEOUT_SECONDS = 15.0
RECORD_TITLE_PREFIX = "Relay | Turno |"

_ENTITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("empilhadeira", re.compile(r"\bempilhadeira\s*(?:n[ºo.]?\s*)?(\d+)\b", re.IGNORECASE)),
    ("doca", re.compile(r"\bdoca\s*(?:n[ºo.]?\s*)?(\d+)\b", re.IGNORECASE)),
)
_INCIDENT_HINT = re.compile(
    r"\b(problema|falha|avaria|pend[eê]ncia|manuten[cç][aã]o|recarga|solt[oa]|quebrad[oa]|vazamento)\b",
    re.IGNORECASE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_critical_entities(transcript: str) -> list[str]:
    """Extrai entidades estáveis, sem tentar inferir fatos não ditos."""
    found: list[str] = []
    for kind, pattern in _ENTITY_PATTERNS:
        for match in pattern.finditer(transcript):
            entity = f"{kind} {match.group(1)}"
            if entity not in found:
                found.append(entity)
    return found


def extract_new_incidents(transcript: str, entities: Iterable[str]) -> list[IncidentReport]:
    """Conservador: só registra incidente quando entidade e indício explícito coexistem."""
    incidents: list[IncidentReport] = []
    for sentence in filter(str.strip, re.split(r"(?<=[.!?])\s+|\n", transcript)):
        if not _INCIDENT_HINT.search(sentence):
            continue
        normalized_sentence = " ".join(sentence.split())
        for entity in entities:
            if entity.casefold() in sentence.casefold() and not any(i.entity == entity for i in incidents):
                incidents.append(
                    IncidentReport(entity=entity, description=normalized_sentence, severity="media")
                )
    return incidents


def _timeout_from_env(name: str, default: float, maximum: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return min(max(float(raw), 0.1), maximum)
    except ValueError:
        return default


def _read_timeout_from_env() -> float:
    # Mantém compatibilidade com a variável original, que sempre representou
    # somente a leitura no caminho crítico da análise.
    raw = os.getenv("AMBIGUOUS_READ_TIMEOUT_SECONDS") or os.getenv("AMBIGUOUS_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_READ_TIMEOUT_SECONDS
    try:
        return min(max(float(raw), 0.1), MAX_READ_TIMEOUT_SECONDS)
    except ValueError:
        return DEFAULT_READ_TIMEOUT_SECONDS


def _write_timeout_from_env() -> float:
    return _timeout_from_env(
        "AMBIGUOUS_WRITE_TIMEOUT_SECONDS",
        DEFAULT_WRITE_TIMEOUT_SECONDS,
        MAX_WRITE_TIMEOUT_SECONDS,
    )


@dataclass(frozen=True)
class AmbiguousClient:
    api_key: str
    base_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> Optional["AmbiguousClient"]:
        load_dotenv()
        api_key = os.getenv("AMBIGUOUS_API_KEY")
        if not api_key:
            return None
        base_url = os.getenv("AMBIGUOUS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        # Aceita as duas formas naturais de configuração, com ou sem /api.
        if base_url.endswith("/api"):
            base_url = base_url[:-4]
        return cls(api_key=api_key, base_url=base_url, timeout_seconds=_read_timeout_from_env())

    def with_timeout(self, timeout_seconds: float) -> "AmbiguousClient":
        """Cria uma visão do mesmo cliente com orçamento específico de operação."""
        return replace(self, timeout_seconds=timeout_seconds)

    def _request_json(self, method: str, path: str, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "API-Version": "1",
            },
        )
        try:
            # O Python do desktop pode não herdar a cadeia de CAs usada pelo
            # sistema/proxy local. Usamos o bundle atualizado do certifi, mas
            # mantemos a verificação TLS ativa (nunca ``_create_unverified_context``).
            tls_context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=self.timeout_seconds, context=tls_context) as response:  # nosec B310: base configurada pelo operador
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"Ambiguous respondeu HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("Não foi possível conectar à Ambiguous.") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ambiguous respondeu um JSON inválido.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Ambiguous respondeu um payload inesperado.")
        return payload

    def find_recurrence(self, entities: list[str], *, since: datetime) -> Optional[str]:
        """Busca documentos Relay recentes em uma única chamada, dentro do orçamento P2."""
        if not entities:
            return None
        payload = self._request_json(
            "POST",
            "/api/search",
            {
                "query": "Relay Turno",
                "modules": ["docs"],
                "limit": 50,
                "after": since.date().isoformat(),
            },
        )
        hits = payload.get("data", [])
        if not isinstance(hits, list):
            raise RuntimeError("Ambiguous retornou resultados de busca inválidos.")

        alerts: list[str] = []
        for entity in entities:
            occurrences = {
                str(hit.get("id"))
                for hit in hits
                if isinstance(hit, dict)
                and str(hit.get("module", "")).casefold() in {"docs", "documents"}
                and str(hit.get("title", "")).startswith(RECORD_TITLE_PREFIX)
                and entity.casefold() in str(hit.get("title", "")).casefold()
            }
            if occurrences:
                plural = "registro" if len(occurrences) == 1 else "registros"
                alerts.append(f"{entity} apareceu em {len(occurrences)} {plural} nos últimos 7 dias")

        return f"Histórico Ambiguous: {'; '.join(alerts)}." if alerts else None

    def create_turn_record(self, record: AmbiguousTurnRecord, entities: list[str]) -> None:
        entity_suffix = ", ".join(entities) if entities else "sem entidade crítica"
        title = f"{RECORD_TITLE_PREFIX} {record.station_id} | {record.timestamp.date().isoformat()} | {entity_suffix}"
        content = _record_markdown(record, entities)
        self._request_json("POST", "/api/documents", {"type": "doc", "title": title, "content": content})


def _record_markdown(record: AmbiguousTurnRecord, entities: list[str]) -> str:
    """Mantém o objeto contratual íntegro e adiciona somente metadados derivados, sem transcrição bruta."""
    entity_lines = "\n".join(f"- {entity}" for entity in entities) or "- Nenhuma entidade crítica detectada"
    record_json = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return (
        "# Registro Relay de passagem de turno\n\n"
        f"- Estação: {record.station_id}\n"
        f"- Turno: {record.turn_id}\n"
        f"- Encerrado em: {record.timestamp.isoformat()}\n\n"
        "## Entidades críticas observadas\n"
        f"{entity_lines}\n\n"
        "## Registro estruturado\n"
        "```json\n"
        f"{record_json}\n"
        "```\n"
    )


def recurrence_alert(transcript: str) -> Optional[str]:
    """Leitura RF06: ausência de configuração ou erro externo equivalem a sem alerta (RNF04)."""
    entities = extract_critical_entities(transcript)
    client = AmbiguousClient.from_env()
    if client is None or not entities:
        return None
    try:
        return client.find_recurrence(entities, since=_utcnow() - timedelta(days=7))
    except Exception:
        logger.warning("Falha não fatal ao consultar reincidência na Ambiguous (RNF04).", exc_info=True)
        return None


def persist_turn(
    *,
    station_id: str,
    turn_id: str,
    transcript: str,
    checklist_status: list[ChecklistItemStatus],
    is_complete: bool,
    summary: str,
) -> Optional[bool]:
    """Gravação RF08. ``None`` significa integração não configurada; ``False``, falha isolada."""
    client = AmbiguousClient.from_env()
    if client is None:
        return None
    entities = extract_critical_entities(transcript)
    record = AmbiguousTurnRecord(
        station_id=station_id,
        turn_id=turn_id,
        timestamp=_utcnow(),
        checklist_status=checklist_status,
        is_complete=is_complete,
        resolved_pending_items=[],
        new_incidents=extract_new_incidents(transcript, entities),
        summary=summary or "Resumo indisponível; turno registrado para auditoria.",
    )
    try:
        # RF08 é executado fora do caminho crítico; usa o orçamento de escrita
        # maior em vez do teto curto reservado à consulta RF06.
        client.with_timeout(_write_timeout_from_env()).create_turn_record(record, entities)
        return True
    except Exception:
        logger.warning("Falha não fatal ao gravar turno na Ambiguous (RNF04).", exc_info=True)
        return False
