"""Harness P3 — roda o motor de validação contra as transcrições reais de P1.

Uso (a partir da raiz do repositório):

    python -m backend.harness_p3
    python -m backend.harness_p3 --dir scratch/transcricoes
    python -m backend.harness_p3 --json

Lê os .txt no formato "LOCUTOR: fala" (um por linha) produzido por P1 e os
entrega ao motor exatamente como o orquestrador (P2) monta
``AnalyzeRequest.transcript``: o texto do arquivo, sem reformatação. Os itens
do checklist vêm de ``mocks/config_request.json`` (estação doca-04).

Exige OPENAI_API_KEY — é o único ponto do P3 que faz chamada de rede real.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.validacao import ValidationEngineError, analisar

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TRANSCRIPTS_DIR = ROOT_DIR / "mocks" / "transcricoes"
DEFAULT_CONFIG = ROOT_DIR / "mocks" / "config_request.json"

_OK = "COBERTO"
_MISSING = "FALTA  "


def _carregar_itens(config_path: Path) -> list[str]:
    return json.loads(config_path.read_text(encoding="utf-8"))["items"]


def _imprimir(nome: str, resultado: dict) -> None:
    completo = "COMPLETO" if resultado["is_complete"] else "INCOMPLETO"
    print(f"\n=== {nome} — {completo} ===")
    for status in resultado["checklist_status"]:
        marca = _OK if status["covered"] else _MISSING
        print(f"  [{marca}] {status['item']}")
        if status["evidence"]:
            print(f"            evidência: “{status['evidence']}”")
    print(f"  intervention_prompt: {resultado['intervention_prompt']!r}")
    print(f"  ambiguous_alert:     {resultado['ambiguous_alert']!r}  (RF06/RF08 cortado)")
    print(f"  summary: {resultado['summary']}")
    for bullet in resultado["summary_bullets"]:
        print(f"    • {bullet}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roda o motor P3 contra as transcrições de teste.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_TRANSCRIPTS_DIR, help="Diretório com os .txt.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="JSON com os itens do checklist.")
    parser.add_argument("--json", action="store_true", help="Imprime o AnalyzeResponse cru de cada transcrição.")
    args = parser.parse_args(argv)

    arquivos = sorted(args.dir.glob("*.txt"))
    if not arquivos:
        print(f"Nenhuma transcrição .txt em {args.dir}", file=sys.stderr)
        return 2

    itens = _carregar_itens(args.config)
    # Qual provedor respondeu importa tanto quanto o resultado: OpenAI direta e
    # contingência OpenRouter podem divergir em Structured Outputs.
    from backend.validacao import _get_client

    try:
        client, modelo = _get_client()
        print(f"provedor: {client.base_url} | modelo: {modelo}")
    except Exception as exc:
        print(f"provedor indisponível: {exc}", file=sys.stderr)
        return 2

    falhas = 0
    for arquivo in arquivos:
        transcricao = arquivo.read_text(encoding="utf-8").strip()
        try:
            resultado = analisar(transcricao, itens)
        except ValidationEngineError as exc:
            falhas += 1
            print(f"\n=== {arquivo.name} — ERRO ===\n  {exc}")
            continue
        except Exception as exc:  # rede/quota: falha numa transcrição não aborta as outras
            falhas += 1
            print(f"\n=== {arquivo.name} — ERRO DE INFRA ===\n  {type(exc).__name__}: {exc}")
            continue
        if args.json:
            print(f"\n=== {arquivo.name} ===")
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
        else:
            _imprimir(arquivo.name, resultado)

    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
