# ingestion — Camada de entrada (P1)

Player de transcrição: lê `mocks/transcricoes/*.txt` e injeta as falas no
orquestrador (P2) uma por vez, com delay, simulando uma passagem de turno ao
vivo. Ao final, dispara `POST /api/turn/end` — o único gatilho de fim de
turno do sistema (`CONTRACTS.md` seção 2.6).

## Rodar

```bash
# a partir da raiz do repo, com o backend já rodando em outra aba:
#   uvicorn backend.main:app --reload --port 8000
python -m venv .venv && source .venv/bin/activate
pip install -r ingestion/requirements.txt

python -m ingestion.cli
```

Isso abre um REPL: `l` lista as transcrições em `mocks/transcricoes/`, `s`
escolhe uma e inicia, `r` reseta/para (para rodar de novo do zero), `q` sai.

Modo não-interativo (ensaio automatizado / CI):
```bash
python -m ingestion.cli --file mocks/transcricoes/completa_padrao.txt --auto
```

Flags: `--backend-url`, `--station-id`, `--delay` (segundos entre falas,
default 2.0), `--timeout`.

## Contrato

- `POST /api/transcript` por fala: `{station_id, seq, speaker, text, ts}`.
  `seq` começa em 0 e incrementa uma unidade por fala — nunca pula, nunca
  repete. `ts` é gerado no momento do envio, ISO 8601 UTC.
- `POST /api/turn/end`: `{station_id}`, enviado uma vez, só ao alcançar o
  fim natural da transcrição.
- `player.stop()`/`reset()` (comando `r` no REPL) cancela uma reprodução em
  andamento **sem** enviar `turn/end` — parar no meio não é um fim de turno
  de verdade, é o operador abortando. Rodar uma transcrição inteira até o
  fim é o único jeito de o `turn/end` sair.
- Cada `start()` reinicia `seq` do zero e descarta qualquer estado da rodada
  anterior — rodar duas transcrições em sequência sem chamar reset
  explicitamente não vaza nada, porque começar uma rodada nova já cancela
  a anterior (se ainda estiver rodando) e zera o contador.

Ver `CONTRACTS.md` seções 2.5 e 2.6 para o contrato completo.

## Parser (`ingestion/parser.py`)

Formato esperado, uma fala por linha:
```
OPERADOR A: texto da fala
OPERADOR B: outra fala
```
- Linhas vazias são ignoradas.
- Uma linha sem o prefixo `LOCUTOR:` vira uma fala com `speaker=null` (o
  contrato permite — RF: sem diarização no MVP).

## Testado contra

Backend stub em `localhost:8000` (`uvicorn backend.main:app --reload --port
8000`) — `/api/transcript` e `/api/turn/end` respondem 200 de verdade contra
os payloads gerados por este player.

## STT por microfone — adiado, não implementado nesta rodada

O plano A e único caminho testado é o player de texto acima. Captura por
microfone com STT real **não foi implementada**: este ambiente de
desenvolvimento não tem dispositivo de áudio de entrada para testar contra
(não é um "pode dar certo, não tentei" — é "não há como validar aqui"), e
qualquer integração de STT não testada é pior que não ter — quebra ao vivo
sem aviso. Como o item 7 do escopo desta fronteira instrui a abandonar se o
STT der qualquer trabalho e avisar em vez de insistir, a decisão foi não
começar: sem hardware de teste, "qualquer trabalho" é garantido.

Se sobrar tempo e alguém tiver um microfone físico disponível pra testar ao
vivo, a integração ficaria em `ingestion/mic.py` (não criado), plugando no
mesmo `TranscriptPlayer` — a interface (`start`/`stop`/`reset`, POST por
fala, POST de turn/end no fim) não muda, só a fonte das falas deixa de ser o
parser de `.txt` e passa a ser o resultado do STT.
