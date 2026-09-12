# Relay

**Agente de áudio ambiental para passagem de turno.** Relay escuta a troca de
turno entre operadores em ambientes logísticos e industriais, confere se o
checklist crítico da estação foi verbalmente coberto e, só ao final da
conversa, avisa por voz — uma única vez — se algo ficou faltando. Depois
publica um resumo estruturado no Slack do gestor.

> Relay = corrida de revezamento: a prova não se ganha correndo mais rápido,
> ganha-se passando o bastão sem deixar cair.

---

## O problema

Em operação logística, a passagem de turno é verbal, informal e não deixa
registro. O que não é dito, some — e reaparece horas depois como parada de
operação, carga perdida ou acidente. Ninguém erra por má-fé: o ambiente é
barulhento, a conversa é apressada, e não existe nada checando o que ficou
de fora.

## Por que isso não é um chatbot

O usuário principal — o operador de turno — nunca abre um app, nunca digita
uma pergunta, nunca inicia uma conversa com um agente. Ele apenas fala com o
colega, como já fazia antes do Relay existir. O agente vive dentro do momento
de trabalho real, não numa janela de chat que alguém precisa lembrar de abrir.
Isso muda o desenho do sistema por completo:

- **O agente escuta, não pergunta.** Não há prompt inicial, não há turno de
  conversa com o usuário — só validação passiva contra um checklist.
- **A única interação é uma interrupção condicional, no momento certo.** O
  agente fala uma única vez, só se algo faltou, só depois que a conversa
  humana terminou. Isso é uma decisão de produto, não uma limitação técnica —
  um sistema que interrompe no meio da fala é desligado no primeiro dia.
- **O valor não existiria fora desse ambiente.** Um chatbot de checklist exige
  que alguém o alimente manualmente; aqui a fonte de verdade é a própria
  conversa de trabalho, e o ambiente (chão de fábrica, doca, câmara fria) é
  parte do desenho, não um wrapper.

## Como funciona, ponta a ponta

```
Operador fala normalmente
        │
        ▼
Ingestão (P1) — transcreve/injeta a fala, em sequência
        │
        ▼
Orquestrador (P2) — FastAPI, estado do turno em memória,
                     broadcast via WebSocket (snapshot completo)
        │
        ▼
Motor de validação (P3) — compara transcrição x checklist crítico
                           via LLM com Structured Outputs;
                           cada item coberto precisa apontar o
                           trecho literal da fala que prova
        │
        ├──► Ambiguous — consulta os últimos 7 dias da estação,
        │                sinaliza reincidência de falha
        │
        ▼
Fim do turno (POST /api/turn/end)
        │
        ├──► Se item crítico não coberto: intervenção por voz (uma vez)
        └──► Card estruturado publicado no Slack do gestor
```

Regra de ouro do motor: **falso positivo é o pior erro possível.** Marcar
como coberto algo que não foi dito cria confiança falsa — pior do que não ter
sistema nenhum. Por isso a arquitetura ancora cada item coberto num índice
literal da fala, não numa paráfrase gerada pelo modelo.

---

## Como testar você mesmo

Você precisa de **3 terminais** rodando ao mesmo tempo — o dashboard sozinho
mostra uma tela vazia, porque quem "fala" durante o teste é o player de
ingestão, não um microfone real.

### 1. Backend (orquestrador + motor de validação)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Endpoints ativos:
- `POST /api/config` — cria o turno
- `POST /api/transcript` — recebe fala, ordena por sequência, roda o motor
- `POST /api/turn/end` — fecha o turno, dispara intervenção e card do Slack
- `ws://localhost:8000/ws/{station_id}` — snapshot ao vivo do turno

### 2. Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

```
OPENAI_API_KEY=...
AMBIGUOUS_API_KEY=...
SLACK_WEBHOOK_URL=...
```

Sem `AMBIGUOUS_API_KEY`, o fluxo continua normalmente com
`ambiguous_alert=null` — a ausência da chave não quebra a demo (ver seção
Ambiguous abaixo).

### 3. Dashboard

```bash
cd dashboard
npm install
cp .env.local.example .env.local   # deixe a chave de TTS vazia
npm run dev
```

Deixando a chave de TTS vazia, a voz usa `speechSynthesis` nativo do
navegador — funciona sem custo de API.

### 4. Player de ingestão (simula a fala do turno)

```bash
python -m ingestion.cli --help
```

Use uma das transcrições de teste em `mocks/transcricoes/`:
- `completa_padrao.txt` — turno completo, todos os itens cobertos
- `empilhadeira2_problema.txt` — turno completo, com reincidência de falha
- `incompleta_sem_refrigerada.txt` — turno com item crítico faltando
  (⚠️ conhecido: hoje o motor pode não disparar o alerta nesse caso com
  modelos menores; ver seção de limitações)

### 5. Testes automatizados

```bash
python -m unittest backend.test_validacao   # 6 testes
python -m backend.harness_p3                # roda as 3 transcrições de exemplo
```

---

## Ambiguous AI — memória longitudinal

O que transforma o Relay de "checklist automatizado" em "inteligência
operacional" é a camada da Ambiguous. Ao final de cada turno:

- O motor consulta os documentos da própria estação dos **últimos 7 dias**.
- Se o mesmo equipamento ou doca aparece com falha recorrente, o sistema
  sinaliza isso explicitamente no card do gestor — ex: *"a empilhadeira 2 já
  falhou recarga 3 vezes esta semana"*. Isso transforma um evento isolado em
  um padrão acionável, algo que a passagem de turno verbal nunca conseguiria
  capturar sozinha.
- Um `AmbiguousTurnRecord` estruturado é gravado ao final do turno.
- **Nenhum áudio ou transcrição bruta é enviado** — só o registro estruturado
  do que foi validado.
- Se a chave não estiver configurada, ou o serviço falhar, o fluxo continua
  normalmente com `ambiguous_alert=null`. A ausência de recorrência não trava
  a demo nem o produto.

## CopilotKit

O dashboard ao vivo do gestor é construído em **Next.js 14 com CopilotKit**.
Sendo transparentes sobre o estado atual: no momento desta submissão, a
integração está num estágio de esqueleto — a base do dashboard usa o
framework, mas não estamos reivindicando o uso de recursos avançados de
generative UI do CopilotKit que não tivemos tempo de validar dentro das 4h.
Preferimos declarar isso com precisão a exagerar a integração.

---

## Limitações conhecidas (declaradas com intenção)

Não escondemos o que não deu tempo de resolver — achamos que isso é mais
útil para quem avalia do que uma demo que finge não ter arestas:

1. **Falha e sucesso do motor são visualmente idênticos hoje.** Se a
   validação cai em modo mock (falta de crédito, timeout), não há indicador
   na tela. É o maior risco sistêmico do projeto atualmente.
2. **Discernimento semântico depende do modelo escolhido.** Com
   `gpt-4o-mini`, a transcrição crítica desenhada para faltar apenas um item
   pode não disparar o alerta — o modelo confunde sentidos próximos da
   mesma palavra (ex: "carga" de bateria vs. carga refrigerada). A correção
   identificada é testar modelos com mais discernimento semântico
   (`gpt-4.1-mini`, `gpt-5-mini`) nas mesmas transcrições.
3. **Persistência é 100% em memória.** Reiniciar o backend perde os turnos
   em andamento — coerente com o escopo de demo, não para uso em produção.
4. **Sem autenticação, CORS aberto.** Fora de escopo declarado para o MVP.
5. **Validação de problem-solution fit não foi feita com usuários reais** —
   foi assumida como dado pelo enunciado do desafio, dentro do tempo do
   hackathon.

## Time e fronteiras

| Fronteira | Responsável | Escopo |
|---|---|---|
| P1 — Ingestão | João Pedro Panza Mainieri | Parser/player que injeta a transcrição do turno |
| P2 — Orquestrador | Lucas Leal Ibrahim | FastAPI, estado do turno, WebSocket |
| P3 — Motor de validação | Leonardo Miranda Nunciaroni (Lead) | LLM + Structured Outputs, invariantes anti-falso-positivo |
| P4 — Dashboard / voz / Slack | Lucas Leonel | Next.js + CopilotKit, TTS via `speechSynthesis`, card do Slack |
| Ambiguous | João Pedro Panza Mainieri | Memória longitudinal e detecção de reincidência |

Contratos de dados entre as fronteiras estão **congelados** em `shared/`
(`schemas.py` + `types.ts`) — ver `CONTRACTS.md` antes de qualquer mudança
estrutural.
