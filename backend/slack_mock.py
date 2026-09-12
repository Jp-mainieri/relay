"""
Simulação do envio do card ao Incoming Webhook do Slack (RF09).

Por que existe: o webhook real ainda não tem credencial. Sem ele, o último
passo do fluxo — `POST /api/turn/end` -> evento `slack_card` -> POST ao Slack —
não pode ser exercitado nem visto. Este módulo fecha essa lacuna gerando o
payload Block Kit EXATO que o Slack receberia e gravando-o em disco em vez de
fazer o POST.

O que este módulo NÃO é:
  - Não substitui `dashboard/app/api/slack/route.ts`. Aquele é o caminho de
    produção (fronteira de P4) e já monta Block Kit. Este aqui é uma
    implementação paralela, em Python, para exercitar o fluxo sem rede e sem
    segredo. Trocar a simulação pelo envio real é trocar `simulate_send` por
    um `httpx.post(webhook, json=body)` — o `body` é o mesmo objeto.
  - Não muda contrato. Consome `SlackCardMessagePayload` e `TurnState` de
    `shared/schemas.py` exatamente como estão congelados.

Sobre a evidência literal: `SlackCardPayload` (congelado) carrega apenas
station_id/timestamp/coverage_pct/ambiguous_alert/summary_bullets — NÃO carrega
o checklist nem a evidência. Por isso `build_block_kit` aceita o `TurnState`
final como fonte opcional do detalhe por item. Sem ele, o card sai sem a seção
de checklist; nada é inventado para preencher o buraco.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from shared.schemas import SlackCardMessagePayload, TurnState

logger = logging.getLogger("relay.slack_mock")

ROOT_DIR = Path(__file__).resolve().parent.parent

# NÃO grava em /mocks: aquele diretório é contrato congelado do time.
DEFAULT_OUTPUT_DIR = ROOT_DIR / "artifacts" / "slack"

_SIMULATION_BANNER = "SIMULAÇÃO — nenhum Slack real foi notificado."


@dataclass(frozen=True)
class SimulatedDelivery:
    """Resultado de um envio simulado."""

    path: Path
    body: dict[str, Any]
    webhook_configured: bool

    @property
    def fallback_text(self) -> str:
        return str(self.body.get("text", ""))


def _format_when(ts: datetime) -> str:
    """pt-BR, em UTC e rotulado como tal — o sistema não sabe o fuso da estação."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _mrkdwn(text: str) -> dict[str, str]:
    return {"type": "mrkdwn", "text": text}


def _checklist_lines(state: TurnState) -> list[str]:
    """
    Uma linha por item, com a evidência literal entre aspas quando coberto.

    A evidência é copiada como veio do motor (que desde 385dd91 devolve o
    índice da fala e o servidor materializa o texto literal). Aqui não há
    reformatação, truncamento nem paráfrase: o que o gestor lê no Slack é
    byte a byte o que o operador falou.
    """
    linhas: list[str] = []
    for status in state.checklist_status:
        if not status.covered:
            linhas.append(f":red_circle: *{status.item}* — não mencionado na passagem de turno")
        elif status.evidence:
            linhas.append(f':white_check_mark: *{status.item}*\n> "{status.evidence}"')
        else:
            # Invariante do motor impede isso; se acontecer, é bug — e o card
            # mostra o bug em vez de fabricar uma citação.
            linhas.append(f":white_check_mark: *{status.item}* — coberto, mas sem evidência registrada")
    return linhas


def build_block_kit(
    message: SlackCardMessagePayload,
    state: Optional[TurnState] = None,
) -> dict[str, Any]:
    """
    Monta o corpo que seria enviado ao Incoming Webhook.

    `message` é o payload do evento `slack_card` tal como P2 o entrega pelo
    WebSocket. `state` é o snapshot final do turno (evento `state`), usado só
    para a seção de checklist com evidência literal — informação que o
    `SlackCardPayload` não carrega.
    """
    card = message.card
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Passagem de turno — {card.station_id}",
                "emoji": False,
            },
        },
        {
            "type": "section",
            "fields": [
                _mrkdwn(f"*Checklist coberto*\n{card.coverage_pct}%"),
                _mrkdwn(f"*Encerrado*\n{_format_when(card.timestamp)}"),
            ],
        },
    ]

    if state is not None and state.checklist_status:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": _mrkdwn("\n\n".join(_checklist_lines(state)))})

    if card.ambiguous_alert:
        blocks.append({"type": "section", "text": _mrkdwn(f":rotating_light: *Reincidência*\n{card.ambiguous_alert}")})
    else:
        # Ausência de alerta é informação, não campo vazio: o gestor precisa
        # distinguir "sem histórico" de "a Ambiguous não respondeu".
        blocks.append({"type": "context", "elements": [_mrkdwn("_Sem alerta de reincidência para este turno._")]})

    if card.summary_bullets:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": _mrkdwn("\n".join(f"• {b}" for b in card.summary_bullets))})

    blocks.append({"type": "context", "elements": [_mrkdwn(f"_{_SIMULATION_BANNER}_  `turn_id={message.turn_id}`")]})

    return {
        # Fallback para notificação push e clientes sem Block Kit — mesmo
        # formato usado por P4 em app/api/slack/route.ts.
        "text": f"Passagem de turno {card.station_id} — {card.coverage_pct}% do checklist coberto",
        "blocks": blocks,
    }


def simulate_send(
    message: SlackCardMessagePayload,
    state: Optional[TurnState] = None,
    out_dir: Optional[Path] = None,
) -> SimulatedDelivery:
    """
    Grava em disco o que teria sido enviado ao Slack. Nenhuma rede é tocada.

    O arquivo guarda o corpo Block Kit (`body`) e o `SlackCardPayload` de
    origem, para que a troca pelo envio real seja um `post(webhook, json=body)`
    sem remontar nada.
    """
    destino = Path(out_dir) if out_dir is not None else DEFAULT_OUTPUT_DIR
    destino.mkdir(parents=True, exist_ok=True)

    body = build_block_kit(message, state)
    # Só o booleano: a URL do webhook é segredo e não entra em log nem em arquivo.
    webhook_configured = bool(os.getenv("SLACK_WEBHOOK_URL"))

    envelope = {
        "simulated": True,
        "note": _SIMULATION_BANNER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "webhook_configured": webhook_configured,
        "station_id": message.station_id,
        "turn_id": message.turn_id,
        "source_card": message.card.model_dump(mode="json"),
        "checklist_detail_available": state is not None and bool(state.checklist_status),
        "body": body,
    }

    arquivo = destino / f"turno_{message.turn_id or 'sem-id'}.json"
    arquivo.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    logger.warning("%s Card de %s gravado em %s", _SIMULATION_BANNER, message.station_id, arquivo)
    return SimulatedDelivery(path=arquivo, body=body, webhook_configured=webhook_configured)
