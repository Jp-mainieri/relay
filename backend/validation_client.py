"""
Relay — Orquestrador (P2): ponte para o motor de validação (P3).

`backend/validacao.py` é entregue por P3 (branch feat/validacao) expondo
`analisar(transcricao: str, itens: list[str]) -> dict` (ver CONTRACTS.md e
runbook-execucao.md). Enquanto esse arquivo não existir (ou se ele falhar em
tempo de execução), caímos para um fallback local baseado nos payloads fixos
de /mocks — é o que o item 3 da tarefa de P2 pede explicitamente.

RNF04 se aplica em dois níveis aqui:
  1. Este módulo nunca deixa uma exceção do motor real escapar — cai pro
     fallback.
  2. Mesmo dentro do fallback, a "consulta à Ambiguous" (aqui, simulada) é
     isolada em try/except própria — nunca derruba a análise inteira por
     causa dela; na dúvida vira `ambiguous_alert=None`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.mock_data import load

logger = logging.getLogger("relay.validation_client")

try:
    from backend.validacao import analisar as _analisar_real  # motor real de P3, quando existir
except ImportError:
    _analisar_real = None


_CRITICAL_ENTITY_HINTS = ("empilhadeira",)  # heurística mínima do fallback; P3 decide a real


def _mock_ambiguous_alert(transcript: str) -> Optional[str]:
    """
    Placeholder da leitura de reincidência na Ambiguous. P3 é quem integra de
    fato (contrato interno, ver CONTRACTS.md secao 4); aqui só reproduzimos o
    padrão de isolamento de falha exigido pelo RNF04 para qualquer chamada
    externa, com o mock como fonte de dado.
    """
    try:
        if not any(hint in transcript.lower() for hint in _CRITICAL_ENTITY_HINTS):
            return None
        mock = load("analyze_response.json")
        return mock.get("ambiguous_alert")
    except Exception:
        logger.exception("Falha ao consultar Ambiguous (mock) — seguindo sem alerta (RNF04).")
        return None


def _fallback_response(transcript: str, items: list[str]) -> dict[str, Any]:
    """
    Fallback enquanto o motor real de P3 não está disponível. Remapeia o
    mock de referência (mocks/analyze_response.json) por item configurado —
    quando o item bate com o mock, herda covered/evidence; quando não bate
    (checklist diferente do doca-04 de exemplo), aplica uma heurística de
    palavra-chave mínima só para o fallback não ficar cego ao transcript real.
    Na dúvida, `covered=False` — falso positivo é o pior erro possível (ver
    CONTRACTS.md).
    """
    mock = load("analyze_response.json")
    mock_by_item = {c["item"]: c for c in mock["checklist_status"]}
    transcript_lower = transcript.lower()

    checklist_status = []
    for item in items:
        hit = mock_by_item.get(item)
        if hit:
            checklist_status.append({"item": item, "covered": hit["covered"], "evidence": hit["evidence"]})
            continue
        keywords = [w for w in item.lower().split() if len(w) > 4]
        covered = bool(keywords) and any(w in transcript_lower for w in keywords)
        checklist_status.append({"item": item, "covered": covered, "evidence": None})

    is_complete = bool(checklist_status) and all(c["covered"] for c in checklist_status)

    return {
        "checklist_status": checklist_status,
        "is_complete": is_complete,
        "intervention_prompt": None if is_complete else mock.get("intervention_prompt"),
        "ambiguous_alert": _mock_ambiguous_alert(transcript),
        "summary": mock.get("summary", ""),
    }


def analisar(transcricao: str, itens: list[str]) -> dict[str, Any]:
    """
    Ponto único de chamada ao motor de validação (RF04). Tenta o motor real
    de P3; cai pro fallback de mock se ele não existir ou lançar qualquer
    exceção. Nunca propaga — quem chama (backend/main.py) ainda envolve esta
    função em try/except própria por defesa em profundidade (RNF04).
    """
    if _analisar_real is not None:
        try:
            return _analisar_real(transcricao, itens)
        except Exception:
            logger.exception("Motor real de validacao (P3) falhou — usando fallback de mock.")
    return _fallback_response(transcricao, itens)
