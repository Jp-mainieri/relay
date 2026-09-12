"""
Relay — Contratos de dados compartilhados (Pydantic).

CONGELADO — ver /CONTRACTS.md. Qualquer mudança aqui exige avisar as 4 pessoas
do time (P1 ingestão, P2 orquestrador, P3 validação, P4 dashboard).

Fonte da verdade para o backend. O dashboard consome o equivalente em
`shared/types.ts` (mantido manualmente em sincronia — não há gerador
automático no escopo das 4h).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Configuração do checklist — POST /api/config
# ---------------------------------------------------------------------------

class ChecklistConfig(BaseModel):
    """Body de POST /api/config. Definido em 05-arquitetura.md."""

    station_id: str = Field(..., description="Identificador da estação, ex: 'doca-04'.")
    items: list[str] = Field(
        ...,
        min_length=1,
        description="Itens do checklist em texto livre, na ordem de prioridade da estação.",
    )


class ChecklistConfigResponse(BaseModel):
    """Resposta de POST /api/config."""

    status: Literal["ok"] = "ok"
    station_id: str
    items: list[str]


# ---------------------------------------------------------------------------
# 2. Análise — POST /api/analyze
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """
    Body de POST /api/analyze.

    Não estava explícito em 05-arquitetura.md (só a resposta aparecia) —
    definido agora para fechar o contrato. Espelha a assinatura que P3 expõe
    em backend/validacao.py: analisar(transcricao: str, itens: list[str]).
    """

    station_id: str
    items: list[str] = Field(..., description="Itens do checklist configurados para a estação.")
    transcript: str = Field(
        ...,
        description=(
            "Transcrição acumulada do turno até o momento, como texto único "
            "(falas separadas por quebra de linha, prefixadas por locutor "
            "quando disponível, ex: 'OPERADOR A: ...'). Quem monta essa string "
            "é o orquestrador (P2), a partir do stream de P1."
        ),
    )


class ChecklistItemStatus(BaseModel):
    """Um item do checklist e seu status de cobertura. Preenchido por P3."""

    item: str
    covered: bool
    evidence: Optional[str] = Field(
        None,
        description="Trecho literal da fala que comprova a cobertura, ou null se covered=false.",
    )


class AnalyzeResponse(BaseModel):
    """Resposta de POST /api/analyze. Definido em 05-arquitetura.md."""

    checklist_status: list[ChecklistItemStatus]
    is_complete: bool = Field(..., description="True apenas se todos os itens estiverem covered=true.")
    intervention_prompt: Optional[str] = Field(
        None,
        description=(
            "Frase curta em pt-BR para o TTS falar. Preenchido por P3 apenas "
            "quando is_complete=false; null caso contrário. Disparado pelo "
            "orquestrador só ao FIM do turno (RNF02), nunca durante."
        ),
    )
    ambiguous_alert: Optional[str] = Field(
        None,
        description=(
            "Alerta de reincidência vindo da consulta à Ambiguous. Null se "
            "nenhuma entidade crítica foi mencionada, ou se a consulta falhou "
            "(RNF04 — falha na Ambiguous nunca derruba o fluxo)."
        ),
    )
    summary: str = Field(..., description="Resumo operacional do turno em prosa curta, usado no card do Slack.")


# ---------------------------------------------------------------------------
# 3. WebSocket — canal /ws/{station_id}
#
# PENDÊNCIA (a) RESOLVIDA — ver CONTRACTS.md para a justificativa completa.
# Decisão: cada mensagem de estado carrega o SNAPSHOT COMPLETO do turno
# (checklist inteiro + transcript_log inteiro), não deltas por item.
# ---------------------------------------------------------------------------

class WSEventType(str, Enum):
    STATE = "state"
    INTERVENTION = "intervention"
    SLACK_SENT = "slack_sent"
    ERROR = "error"


class TranscriptLine(BaseModel):
    """Uma linha de fala transcrita, na ordem em que ocorreu."""

    seq: int = Field(..., description="Índice sequencial da fala no turno, começando em 0.")
    speaker: Optional[str] = Field(None, description="Ex: 'OPERADOR A'. Null se não identificado (RF: sem diarização).")
    text: str
    ts: datetime = Field(default_factory=datetime.utcnow)


class TurnState(BaseModel):
    """
    Payload da mensagem `state`: o snapshot COMPLETO e autossuficiente do
    turno em andamento. Um cliente que conecta (ou reconecta) no meio do turno
    renderiza a tela inteira a partir da última mensagem `state` recebida —
    nunca precisa de histórico de deltas.
    """

    station_id: str
    turn_id: str = Field(..., description="Identifica o turno atual; muda a cada novo turno na mesma estação.")
    checklist_status: list[ChecklistItemStatus]
    is_complete: bool
    ambiguous_alert: Optional[str] = None
    summary: str
    transcript_log: list[TranscriptLine] = Field(
        default_factory=list, description="Todas as falas do turno até agora, em ordem."
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InterventionPayload(BaseModel):
    """Payload da mensagem `intervention`. Evento único, disparado ao FIM do turno."""

    station_id: str
    turn_id: str
    intervention_prompt: str


class SlackSentPayload(BaseModel):
    """Payload da mensagem `slack_sent`. Evento único, disparado ao FIM do turno."""

    station_id: str
    turn_id: str
    summary: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)


class ErrorPayload(BaseModel):
    station_id: Optional[str] = None
    message: str


class WSStateMessage(BaseModel):
    type: Literal[WSEventType.STATE] = WSEventType.STATE
    payload: TurnState


class WSInterventionMessage(BaseModel):
    type: Literal[WSEventType.INTERVENTION] = WSEventType.INTERVENTION
    payload: InterventionPayload


class WSSlackSentMessage(BaseModel):
    type: Literal[WSEventType.SLACK_SENT] = WSEventType.SLACK_SENT
    payload: SlackSentPayload


class WSErrorMessage(BaseModel):
    type: Literal[WSEventType.ERROR] = WSEventType.ERROR
    payload: ErrorPayload


WSMessage = Union[WSStateMessage, WSInterventionMessage, WSSlackSentMessage, WSErrorMessage]
"""
Union discriminada pelo campo `type`. P4 deve fazer um switch em `msg.type`:
  - "state"        -> renderizar checklist + transcript inteiros (substituir, não mesclar)
  - "intervention" -> disparar TTS falando `payload.intervention_prompt` (uma vez)
  - "slack_sent"    -> feedback visual opcional de "resumo enviado ao Slack"
  - "error"        -> mostrar aviso não bloqueante (nunca deve derrubar a tela)
"""


# ---------------------------------------------------------------------------
# 4. Ambiguous
# ---------------------------------------------------------------------------

class AmbiguousQueryResult(BaseModel):
    """
    Resultado de uma consulta de leitura à Ambiguous (reincidência), usado
    internamente por P3 para montar `AnalyzeResponse.ambiguous_alert`. Não é
    exposto como está em nenhum endpoint — é um contrato interno de P3.
    """

    entity: str = Field(..., description="Ex: 'empilhadeira 2'.")
    found: bool
    alert_text: Optional[str] = Field(None, description="Texto pronto para ambiguous_alert, ou null se found=false.")


class IncidentReport(BaseModel):
    """Um incidente novo identificado neste turno, a ser gravado na Ambiguous."""

    entity: str = Field(..., description="Entidade crítica envolvida, ex: 'empilhadeira 2'.")
    description: str
    severity: Literal["baixa", "media", "alta"] = "media"


# PENDÊNCIA (b) RESOLVIDA — ver CONTRACTS.md para a justificativa completa.
class AmbiguousTurnRecord(BaseModel):
    """
    Objeto gravado na Ambiguous ao FIM do turno (RF08). Escrito por P3.

    timestamp + pendências resolvidas + novos incidentes, conforme
    05-arquitetura.md, mais os campos mínimos para a consulta de reincidência
    de um turno futuro conseguir reconstruir contexto sem reprocessar tudo.
    """

    station_id: str
    turn_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Fim do turno.")
    checklist_status: list[ChecklistItemStatus]
    is_complete: bool
    resolved_pending_items: list[str] = Field(
        default_factory=list,
        description=(
            "Itens que estavam pendentes/reincidentes em turnos anteriores "
            "(vieram como ambiguous_alert) e foram confirmados como resolvidos "
            "neste turno."
        ),
    )
    new_incidents: list[IncidentReport] = Field(
        default_factory=list,
        description="Problemas novos mencionados neste turno, candidatos a reincidência em turnos futuros.",
    )
    summary: str


def new_turn_id() -> str:
    """Helper compartilhado para gerar turn_id — mesma convenção em todas as fronteiras."""
    return uuid4().hex


# ---------------------------------------------------------------------------
# 5. Notificação Slack — payload do card
# ---------------------------------------------------------------------------

class SlackCardPayload(BaseModel):
    """Corpo enviado ao Incoming Webhook do Slack (RF09). Montado e enviado por P4."""

    station_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    coverage_pct: int = Field(..., ge=0, le=100, description="Percentual do checklist coberto, 0-100.")
    ambiguous_alert: Optional[str] = None
    summary_bullets: list[str] = Field(..., description="Resumo operacional em bullet points.")
