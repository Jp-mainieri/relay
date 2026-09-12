"""
Teste de conectividade — caminho de contingência via OpenRouter (P3).

Isolado de propósito: só confere se as credenciais funcionam e se o modelo
devolve JSON válido. NÃO chama backend/validacao.py, não gera AnalyzeResponse,
não altera backend/tests/ nem shared/schemas.py — é só um "alô, funciona?"
antes de alguém decidir plugar isso de verdade no motor.

Uso (a partir da raiz do repo, com o venv ativo e OPENROUTER_API_KEY no .env):

    python backend/scripts/test_openrouter.py

Sai com código 0 se PASSOU, 1 se FALHOU.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

import os  # noqa: E402

# Mesmo teto que o orquestrador aplica ao motor de validação de verdade
# (backend/main.py::VALIDATION_TIMEOUT_SECONDS) — RNF04: nunca esperar sem limite.
TIMEOUT_SECONDS = 8.0


def _redact(key: str | None) -> str:
    """Nunca imprime a chave inteira — só confirma que ela existe e o formato."""
    if not key:
        return "(ausente)"
    if len(key) <= 12:
        return "***"
    return f"{key[:7]}...{key[-4:]} ({len(key)} chars)"


def main() -> int:
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

    print("=== teste de conectividade OpenRouter ===")
    print(f"  base_url = {base_url}")
    print(f"  model    = {model}")
    print(f"  api_key  = {_redact(api_key)}")
    print(f"  timeout  = {TIMEOUT_SECONDS}s (RNF04)")
    print()

    if not api_key:
        print("FALHOU: OPENROUTER_API_KEY não encontrada no .env.")
        return 1

    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
    except ImportError:
        print("FALHOU: pacote 'openai' não instalado. Rode: pip install -r backend/requirements.txt")
        return 1

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=TIMEOUT_SECONDS, max_retries=0)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        'Responda SOMENTE com este JSON exato, sem nenhum texto extra: '
                        '{"status": "ok", "provider": "openrouter"}'
                    ),
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except APITimeoutError:
        print(f"FALHOU: sem resposta em {TIMEOUT_SECONDS}s (timeout). Serviço lento ou fora do ar.")
        return 1
    except APIConnectionError as exc:
        print(f"FALHOU: não conseguiu conectar em {base_url}. Detalhe: {exc}")
        return 1
    except APIStatusError as exc:
        # Cobre 401 (chave inválida), 404 (modelo não encontrado no OpenRouter),
        # 429 (sem crédito/rate limit) — a mensagem da API já é específica.
        print(f"FALHOU: a API respondeu erro HTTP {exc.status_code}. Detalhe: {exc.message}")
        return 1
    except Exception as exc:  # RNF04: nunca deixar uma exceção crua sem contexto
        print(f"FALHOU: erro inesperado ({type(exc).__name__}): {exc}")
        return 1

    raw_content = response.choices[0].message.content
    print(f"resposta bruta do modelo: {raw_content!r}")

    try:
        parsed = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        print("FALHOU: a resposta não é um JSON válido.")
        return 1

    if parsed.get("status") == "ok" and parsed.get("provider") == "openrouter":
        print("\nPASSOU: OpenRouter respondeu com o JSON esperado.")
        return 0

    print(f"\nFALHOU: JSON válido, mas conteúdo inesperado: {parsed}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
