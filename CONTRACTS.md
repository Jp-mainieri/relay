# Relay — Contratos de Dados (CONGELADOS)

> **Status: CONGELADO.** Estes contratos são a interface entre as 4 fronteiras
> (P1 ingestão, P2 orquestrador, P3 validação, P4 dashboard) desenvolvidas em
> paralelo. **Nenhuma mudança de campo, tipo, nome ou formato entra sem avisar
> as outras 3 pessoas antes.** Se você acha que um contrato precisa mudar,
> PARE e avise no canal do time — não mude e siga.
>
> Fonte da verdade em código: `shared/schemas.py` (Pydantic, backend) e
> `shared/types.ts` (TypeScript, dashboard). Os dois devem ficar idênticos
> campo a campo — não há gerador automático no escopo das 4h, então quem
> mudar um muda o outro no mesmo commit.
>
> Exemplos completos de cada payload: `/mocks/*.json`.
>
> **Revisão 2 (aditiva):** fecha três lacunas achadas na revisão do contrato —
> (1) o stream P1→P2 nunca tinha formato definido, (2) não havia gatilho
> explícito de fim de turno (TTS e Slack nunca disparavam), (3) dono do POST
> ao Slack e nome do evento `slack_sent` eram ambíguos/circulares, e (4)
> `summary_bullets` exigia trabalho extra de quem não devia fazê-lo. Nenhum
> campo existente mudou de nome, tipo ou formato — quem já integrou contra a
> Revisão 1 não refaz nada, só soma o que falta.

---

## 1. `POST /api/config`

Configura o checklist de uma estação em linguagem natural (RF01).

**Request** (`ChecklistConfig`) — `mocks/config_request.json`
```json
{
  "station_id": "doca-04",
  "items": ["status da carga refrigerada", "liberacao da doca", "..."]
}
```

**Response** (`ChecklistConfigResponse`) — `mocks/config_response.json`
```json
{ "status": "ok", "station_id": "doca-04", "items": ["..."] }
```

- `items` é texto livre — quem interpreta contextualmente é P3, não este endpoint.
- Dono: P2 (persistência em memória, sem banco no MVP).

---

## 2. `POST /api/analyze`

Compara a transcrição acumulada com o checklist configurado (RF04). Chamado
internamente pelo orquestrador (P2) — a cada novo trecho relevante de
transcrição, e obrigatoriamente uma última vez ao receber `POST /api/turn/end`
(seção 2.6). Não é tipicamente chamado direto pelo dashboard.

**Request** (`AnalyzeRequest`) — `mocks/analyze_request.json`. **Este request
não estava explícito em `05-arquitetura.md`** (só a resposta aparecia) — foi
definido na Revisão 1 para fechar o contrato, espelhando a assinatura que P3
expõe em `backend/validacao.py`: `analisar(transcricao: str, itens: list[str])`.
```json
{
  "station_id": "doca-04",
  "items": ["status da carga refrigerada", "..."],
  "transcript": "OPERADOR A: ...\nOPERADOR B: ..."
}
```
- `transcript`: texto único, falas separadas por quebra de linha, prefixadas
  por locutor quando disponível (`"OPERADOR A: ..."`). Montar essa string a
  partir das falas recebidas em `POST /api/transcript` é responsabilidade de
  P2 — ver seção 2.5 para o algoritmo exato.

**Response** (`AnalyzeResponse`) — `mocks/analyze_response.json`
```json
{
  "checklist_status": [
    { "item": "status da carga refrigerada", "covered": true, "evidence": "..." },
    { "item": "nivel de bateria das empilhadeiras", "covered": false, "evidence": null }
  ],
  "is_complete": false,
  "intervention_prompt": "Atencao: ...",
  "ambiguous_alert": "Historico: ...",
  "summary": "Doca liberada e carga refrigerada conectada. ...",
  "summary_bullets": ["Carga da Swift conectada e refrigerada no plug 3.", "..."]
}
```

**`summary_bullets` (NOVO — Revisão 2).** O mesmo resumo de `summary`, já
quebrado em bullet points, prontos para `SlackCardPayload.summary_bullets`
(seção 5). Preenchido por **P3**, na mesma chamada de LLM que gera `summary` —
não uma segunda chamada de LLM nem um split ingênuo em ponto final feito por
quem monta o card depois.

**Por quê:** o contrato anterior mandava "quem monta o card do Slack" quebrar
`summary` em bullets. Isso significava ou (a) uma segunda chamada de LLM no
caminho da demo — latência extra bem no momento em que o card sobe no telão —
ou (b) um `summary.split(". ")` ingênuo, arriscando bullets cortados no meio.
P3 já tem uma chamada de LLM em voo para gerar `summary`; pedir os bullets na
mesma chamada é custo marginal zero. P4/P2 passam a apenas repassar a lista.

**Quem preenche o quê** (pergunta óbvia entre P2 e P3 — resolvida aqui):
| Campo | Preenchido por | Regra |
|---|---|---|
| `checklist_status[].covered/evidence` | P3 | `covered=true` só com evidência explícita na fala; na dúvida, `false` (falso positivo é o pior erro possível na demo) |
| `is_complete` | P3 | `true` sse todos os itens `covered=true` |
| `intervention_prompt` | P3 | só não-null quando `is_complete=false`; frase curta em pt-BR pronta pro TTS |
| `ambiguous_alert` | P3 | null se nenhuma entidade crítica mencionada, **ou se a consulta à Ambiguous falhar** (RNF04 — nunca propagar exceção) |
| `summary` | P3 | sempre preenchido, mesmo se `is_complete=true` |
| `summary_bullets` | P3 | mesma chamada de LLM que gera `summary`; sempre preenchido |
| Disparo do TTS / card do Slack | P2 dispara os eventos; **P4 executa** (TTS e o POST ao webhook) | Ver seção 4 — gatilho é `POST /api/turn/end` (seção 2.6), eventos distintos das atualizações de estado |

---

## 2.5 `POST /api/transcript` — ingestão de fala (NOVO — Revisão 2)

Fecha o contrato **P1 → P2** que faltava: a Revisão 1 dizia que P2 monta
`AnalyzeRequest.transcript` "a partir do stream de P1" sem nunca definir o
formato desse stream. Sem isso, cada fronteira ia inventar um formato
diferente.

P1 chama este endpoint **uma vez por fala**, na ordem em que a fala ocorreu.

**Request** (`TranscriptPostRequest`) — `mocks/transcript_post.json`
```json
{
  "station_id": "doca-04",
  "seq": 1,
  "speaker": "OPERADOR B",
  "text": "Tranquilo. A carga da Swift ja ta no plug 3, refrigerada certinha.",
  "ts": "2026-09-12T12:00:05Z"
}
```

**Response** (`TranscriptPostResponse` = `AckResponse`)
```json
{ "status": "ok" }
```

- `seq`: inteiro, começando em 0, incrementando uma unidade por fala — **é P1
  quem numera**. P2 ordena as falas recebidas por `seq` antes de anexar ao
  `transcript_log` do turno; `seq` é a fonte da verdade de ordem, não a ordem
  de chegada da requisição HTTP (que pode variar com retry/latência de rede).
- **O formato é idêntico, campo a campo (`seq`, `speaker`, `text`, `ts`), ao
  de um item de `TurnState.transcript_log`** (seção 3) — de propósito: P2
  anexa a fala recebida direto no log do turno, sem nenhuma conversão de
  schema. `station_id` existe só neste request, para rotear ao turno certo;
  não é replicado dentro de cada `TranscriptLine`.
- **Algoritmo de P2 para montar `AnalyzeRequest.transcript`:** ordenar as
  linhas do `transcript_log` por `seq` e concatenar
  `f"{speaker}: {text}"` (ou só `text` se `speaker` for `null`) separadas por
  `\n`, na ordem de `seq`.
- Dono: P1 chama; P2 implementa o handler.

---

## 2.6 `POST /api/turn/end` — fim de turno (NOVO — Revisão 2)

Fecha o gatilho que faltava para os eventos `intervention` e `slack_card`
(seção 4) — sem ele, esses dois momentos de payoff da demo nunca disparavam,
porque nada definia de onde vinha o sinal de "turno acabou".

**Request** (`TurnEndRequest`) — `mocks/turn_end.json`
```json
{ "station_id": "doca-04" }
```

**Response** (`TurnEndResponse` = `AckResponse`)
```json
{ "status": "ok" }
```

- **Enviado por P1**, logo após a última fala do turno.
- **Este é o ÚNICO gatilho de fim de turno reconhecido pelo sistema.** P2
  **não** infere fim de turno por timeout de silêncio, nem por qualquer outra
  heurística — só por esta chamada. (Se P1 não tiver um sinal humano/de UI
  claro de "acabou o turno" a tempo, isso é um risco a levantar cedo, não algo
  para resolver com um timeout adivinhado no orquestrador.)
- **Ao receber, P2:**
  1. roda a análise (equivalente a `POST /api/analyze`) uma última vez, com o
     `transcript_log` acumulado até agora;
  2. emite `intervention` pelo WebSocket **se `is_complete=false`**;
  3. emite `slack_card` pelo WebSocket **sempre**, independente de `is_complete`.
- Dono: P1 chama; P2 implementa o handler e orquestra os dois eventos.

---

## 3. Canal WebSocket — `WS /ws/{station_id}`

### Pendência (a) resolvida: formato incremental vs. snapshot completo

**Opções consideradas:**
1. **Incremental por item** — cada mensagem carrega só o item que mudou (`{item, covered, evidence}`).
2. **Payload completo a cada atualização** — cada mensagem `state` carrega o snapshot inteiro do turno (checklist completo + transcrição completa até o momento).

**Decisão: opção 2 — snapshot completo.**

**Justificativa:** o requisito que mais importa aqui é *"reconexão no meio da
demo não pode quebrar a tela"* (RNF01 + risco explícito em
`04-planejamento.md`). Com deltas incrementais, um cliente que conecta ou
reconecta no meio do turno não tem como saber o estado anterior sem um
mecanismo extra de "pedir snapshot atual" — mais uma coisa para sincronizar
sob pressão de tempo, e mais uma forma de a tela ficar inconsistente bem no
meio de uma demo de 5 minutos. Com snapshot completo, a regra do cliente é
uma linha: **ao receber uma mensagem `state`, substitua todo o estado local
por `payload`** — nunca faça merge campo a campo. Conectar 5 segundos antes
do fim do turno já renderiza a tela certa.

O custo (reenviar o checklist inteiro e o log de transcrição inteiro a cada
mudança) é irrelevante na escala desta demo (poucos itens, um turno, minutos
de duração) — o ganho em simplicidade e robustez de reconexão compensa de
sobra.

**Consequência prática para P2:** ao conectar, o servidor deve empurrar
imediatamente uma mensagem `state` com o estado atual (ou o estado inicial
vazio, se o turno ainda não começou) — nunca deixar o cliente sem nada até a
próxima mudança.

**Consequência prática para P4:** o handler do WebSocket faz um switch em
`type` e, no caso `state`, substitui a árvore de estado inteira (React:
`setState(payload)`, não merges parciais).

### Envelope de mensagem

Toda mensagem no canal é `{ "type": "...", "payload": {...} }`. Quatro tipos:

| `type` | Payload | Quando é enviado | Quantas vezes por turno |
|---|---|---|---|
| `state` | `TurnState` (snapshot completo) | ao conectar, e a cada mudança de checklist ou nova fala transcrita | N vezes |
| `intervention` | `InterventionPayload` | ao receber `POST /api/turn/end`, só se `is_complete=false` | 0 ou 1 |
| `slack_card` | `SlackCardMessagePayload` | ao receber `POST /api/turn/end`, sempre | 1 |
| `error` | `ErrorPayload` | falha não-fatal (ex: Ambiguous fora do ar) | 0+, nunca derruba a conexão |

`intervention` e `slack_card` são **eventos distintos das atualizações de
`state`**, disparados exclusivamente por `POST /api/turn/end` (seção 2.6) — P4
não deve inferir "fim de turno" olhando o conteúdo de um `state`; o backend
sinaliza explicitamente.

**`TurnState`** (payload de `state`) — ver exemplos em ordem em
`mocks/ws_sequence/01_state_initial.json` → `03_state_final.json`:
```json
{
  "station_id": "doca-04",
  "turn_id": "mock-turn-0001",
  "checklist_status": [{ "item": "...", "covered": false, "evidence": null }],
  "is_complete": false,
  "ambiguous_alert": null,
  "summary": "",
  "transcript_log": [{ "seq": 0, "speaker": "OPERADOR A", "text": "...", "ts": "2026-09-12T12:00:01Z" }],
  "updated_at": "2026-09-12T12:00:01Z"
}
```
- `turn_id`: muda a cada novo turno na mesma estação — usado por P4 para
  detectar "começou um turno novo" e limpar a UI, se necessário.
- `transcript_log`: lista **completa e ordenada** por `seq` (mesmo shape do
  `TranscriptPostRequest` de P1, menos `station_id` — seção 2.5), não só a
  fala nova.

**`intervention`** — `mocks/ws_sequence/04_intervention.json`. P4 dispara o
TTS falando `payload.intervention_prompt`, no máximo uma vez por turno.

**`slack_card`** (renomeado de `slack_sent` — Revisão 2, ver justificativa na
seção 5) — `mocks/ws_sequence/05_slack_card.json`. Carrega o
`SlackCardPayload` **completo e pronto** em `payload.card`; P4 faz o `POST`
desse objeto ao Incoming Webhook, uma vez por turno.

**`error`** — `mocks/ws_error.json`. Nunca fecha a conexão nem quebra a UI;
é só um aviso (ex.: RNF04 — Ambiguous fora do ar).

---

## 4. Ambiguous

### Leitura (reincidência)
Consulta interna de P3 ao mencionar entidade crítica (equipamento, número de
doca) — resultado vira `AnalyzeResponse.ambiguous_alert` (texto pronto,
seção 2). Não é exposto como endpoint próprio; contrato interno de P3
(`AmbiguousQueryResult` em `shared/schemas.py`, referência apenas).

### Gravação — pendência (b) resolvida

**Opções consideradas** para o schema do objeto gravado ao fim do turno:
1. Objeto mínimo: só `{ station_id, timestamp, is_complete }`.
2. Objeto espelhando `AnalyzeResponse` inteiro mais os dois campos citados em
   `01-requisitos.md` (RF08): pendências resolvidas e novos incidentes.

**Decisão: opção 2**, formalizada como `AmbiguousTurnRecord`:
```json
{
  "station_id": "doca-04",
  "turn_id": "mock-turn-0001",
  "timestamp": "2026-09-12T12:00:22Z",
  "checklist_status": [{ "item": "...", "covered": true, "evidence": "..." }],
  "is_complete": false,
  "resolved_pending_items": ["liberacao da doca"],
  "new_incidents": [
    { "entity": "empilhadeira 2", "description": "...", "severity": "media" }
  ],
  "summary": "..."
}
```
Ver `mocks/ambiguous_turn_record.json`.

**Justificativa:** RF08 pede explicitamente timestamp + pendências resolvidas
+ novos incidentes; incluir também o `checklist_status` completo (em vez de só
um resumo textual) é o que permite a uma consulta de reincidência futura
(RF06) reconstruir "isso já apareceu antes e como" sem reprocessar a
transcrição original — que não é gravada na Ambiguous (fora de escopo: só o
resultado estruturado é gravado, não o áudio/transcrição bruta).

- `resolved_pending_items`: itens que vieram como alerta de reincidência
  (`ambiguous_alert`) em turnos anteriores e foram confirmados resolvidos
  neste.
- `new_incidents`: problemas novos mencionados neste turno, candidatos a
  aparecer como `ambiguous_alert` em turnos futuros. Campo livre — P3 decide
  a granularidade de `entity`/`description`/`severity`.
- Dono: P3 grava; RNF04 se aplica aqui também — falha na escrita não trava o
  fim do turno (log + segue).

---

## 5. Notificação Slack — `SlackCardPayload`

Corpo do POST ao Incoming Webhook (RF09).

**Dono do POST HTTP ao webhook: P4** (decidido na Revisão 2 — ver abaixo).
P2 monta o payload e entrega **pronto** pelo evento WebSocket `slack_card`
(seção 3); P4 só faz o `POST` para a URL do webhook, sem reprocessar nada.

**Por quê essa mudança (Revisão 2):** o contrato anterior dizia "fica com
quem implementar" — o resultado provável de uma responsabilidade não
atribuída em código feito em paralelo é zero implementações (cada um assume
que é o outro) ou duas (retrabalho, e risco de o card ir duas vezes ao
Slack). Além disso, o evento anterior se chamava `slack_sent` e era **P4
mandando o servidor "confirmar" a P4 que P4 mesmo tinha enviado** — circular
e sem uso real. A solução simétrica com `intervention` (P2 dispara o evento
com o conteúdo pronto, P4 executa a ação externa) resolve as duas coisas:
`slack_card` carrega o card pronto, e só existe um dono do `POST` real.

`mocks/slack_card_payload.json`:
```json
{
  "station_id": "doca-04",
  "timestamp": "2026-09-12T12:00:22Z",
  "coverage_pct": 50,
  "ambiguous_alert": "Historico: ...",
  "summary_bullets": ["Carga da Swift conectada...", "Doca 4 liberada.", "..."]
}
```
- `coverage_pct`: inteiro 0–100, calculado por P2 como `covered=true` / total de itens.
- `summary_bullets`: copiado direto de `AnalyzeResponse.summary_bullets`
  (seção 2) — **quem quebra o resumo em bullets é P3**, não quem monta este
  payload nem quem faz o POST.

---

## Convenções gerais

- Datas/horas: sempre ISO 8601 em UTC (`...Z`), tanto em JSON quanto em campos `datetime` do Pydantic.
- `turn_id`: string opaca (uuid hex), gerada pelo orquestrador (P2) ao iniciar um turno — usar `shared.schemas.new_turn_id()`.
- Nenhum contrato aqui assume autenticação (RNF03 — sem login no MVP).
- Falha em serviço externo (Ambiguous, TTS, Slack) nunca deve derrubar o
  processo nem a conexão WebSocket — vira `ambiguous_alert=null`, evento
  `error`, ou log, conforme a seção acima (RNF04).

## Processo de mudança

1. Proponha a mudança descrevendo o campo/tipo antes e depois.
2. Avise as 4 pessoas (canal do time) e espere confirmação — não precisa ser
   unânime, mas ninguém pode ser pego de surpresa por um schema que mudou.
3. Atualize `shared/schemas.py` **e** `shared/types.ts` **e** o mock afetado
   em `/mocks` no mesmo commit.
4. Atualize este arquivo.
