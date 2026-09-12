# Relay

Agente de áudio ambiental para passagem de turno — ver `01-requisitos.md` a
`05-arquitetura.md` para requisitos/produto/arquitetura, e
`runbook-execucao.md` para como as 4 pessoas executam em paralelo.

## Monorepo

```
backend/      FastAPI — orquestrador (P2). Stubs de todos os endpoints já rodam.
dashboard/    CopilotKit/Next.js — dashboard ao vivo (P4). Esqueleto mínimo.
shared/       Contratos CONGELADOS: schemas.py (Pydantic) + types.ts (TypeScript).
mocks/        Um .json por contrato — payloads de exemplo fixos.
scratch/      Trabalho lateral (Codex), no .gitignore, nunca vai pra main.
```

## Antes de escrever código

Leia `CONTRACTS.md` — documenta cada contrato de dados entre as 4 fronteiras
e por que as duas pendências de `05-arquitetura.md` foram resolvidas do jeito
que foram. **Contratos estão CONGELADOS**: mudar exige avisar as 4 pessoas.

## Subir o backend (stub, Fase 0)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Testado e respondendo de verdade:
- `POST http://localhost:8000/api/config`
- `POST http://localhost:8000/api/transcript`
- `POST http://localhost:8000/api/turn/end`
- `POST http://localhost:8000/api/analyze`
- `ws://localhost:8000/ws/{station_id}`

Ver `backend/README.md` para detalhes e o que muda na próxima fase.

## Setup de ambiente

Copie `.env.example` para `.env` e preencha as chaves reais (`OPENAI_API_KEY`,
`AMBIGUOUS_API_KEY`, `SLACK_WEBHOOK_URL`, chave de TTS).

A integração Ambiguous já está ativa quando `AMBIGUOUS_API_KEY` estiver
configurada: o Relay consulta documentos próprios dos últimos sete dias para
identificar reincidências e grava ao fim do turno um `AmbiguousTurnRecord`
estruturado. Não envia áudio nem transcrição bruta. Sem chave, ou se o serviço
falhar, o fluxo continua com `ambiguous_alert=null` (RNF04).

TTS e Slack ainda são responsabilidade de P4; as chaves só são necessárias ao
integrar essas saídas reais.
