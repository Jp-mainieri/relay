# P4 — decisões da fronteira do dashboard

Registro do que foi decidido e por quê. Nenhuma dessas decisões toca contrato:
`CONTRACTS.md`, `shared/` e `mocks/` seguem intactos.

## Visual

Base é o `DESIGN.md` do Linear ("midnight precision instrument"), com três
adaptações para o alvo real, que é um **vídeo de 2 minutos em 1920×1080**.

**Escala.** O Linear é calibrado para laptop a 60cm: corpo 13–15px, hairlines de
0.5px. Em vídeo, hairline de meio pixel some. Solução: `html { font-size:
clamp(13px, 0.833vw, 22px) }` e todo o resto em `rem` — uma linha controla a
tela inteira, sem media query. A 1920 a raiz fica em 16px. `Shift+D` multiplica
por 1.25 se algo ficar pequeno na hora da gravação.

**Espessuras.** Bordas de status em 3px e barra lateral em 6px, não hairline. O
subsampling 4:2:0 do H.264 destrói detalhe colorido fino — a barra sobrevive à
compressão, a borda de 1px vira mancha cinza.

**Semáforo.** O `DESIGN.md` diz que Pulse Green e Coral Red são acentos de
apoio, *não* cores de status. Mas o produto inteiro é um sistema de status.
Resolução: os três status usam cores que já existem no sistema, com lift de
brilho para sobreviver à compressão.

| Status | Cor | Aplicação |
|---|---|---|
| Coberto | `#3ecf62` | barra 6px + borda 3px + wash 10% |
| Intervenção | `#e4f222` (acid lime, sem ajuste) | borda 3px do overlay |
| Alerta Ambiguous | `#ff6b6b` | barra 6px + wash 12% |
| Pendente | `#0f1011` / borda `#23252a` | superfície neutra |

`#27a644` puro tem ~4.3:1 contra `#08090a` e fica barrento em vídeo; `#3ecf62`
sobe para ~9:1 sem sair da família.

Regra mantida do sistema: **status nunca preenche um card inteiro**. Sempre
barra, borda e wash a 10–12% sobre superfície escura. É isso que impede a tela
de virar painel de alarme de fábrica.

O acid lime segue sendo a única cor cromática de ação, e há exatamente um botão
que a usa por vez ("Armar áudio" antes do turno, overlay de intervenção no fim
— nunca coexistem).

**Layout.** Descartados o `max-width: 1200px`, o section-gap de 96px e a regra
de foco único: aquilo descreve a *homepage* do Linear, não um dashboard.
Mantidos a progressão de superfícies, elevação por borda em vez de sombra, os
três raios e zero gradiente decorativo.

## Técnicas

**CSS puro, não Tailwind.** Uma tela só, design já baseado em tokens. O setup do
PostCSS do Tailwind v4 é risco de build que não paga nada aqui, e CSS direto é
editável ao vivo durante a gravação.

**JetBrains Mono.** Berkeley Mono é paga; o `DESIGN.md` lista JetBrains como
substituto oficial.

**Quatro fatias de estado, não uma.** `state` carrega snapshot completo e
substitui `turn` inteiro. Mas `intervention`, `slack_card` e `error` são
eventos: se ficassem na mesma fatia, o próximo `state` apagaria o overlay bem no
clímax.

**Dedupe por `turn_id`, nunca zerado.** `active_turn` no backend abre um turno
novo se uma fala chegar depois de `POST /api/turn/end`. Os refs `spokenFor` e
`sentFor` só são sobrescritos quando a ação acontece — assim um turno reaberto
por acidente não reenvia o card ao Slack.

**`reactStrictMode: false`.** StrictMode monta efeitos duas vezes em dev, o que
abriria dois WebSockets. O dedupe cobriria, mas em hackathon é ruído
desnecessário.

**Evidência sempre visível.** O runbook sugeria hover. Num vídeo ninguém vê o
mouse parado.

**Indicador "analisando".** `VALIDATION_TIMEOUT_SECONDS = 8.0` no P2 significa
que uma fala pode levar 8s até virar `state`. Silêncio prolongado vira feedback
em vez de tela travada. Não é sinal do contrato — é heurística local de 3s.

**Toast de `error` em cinza, nunca coral.** Coral pertence ao alerta da
Ambiguous; confundir os dois no vídeo seria ruim.

## Voz

Interface única `speakIntervention()` com três camadas degradando:

1. Texto no overlay — sempre presente, custo zero. É o item 4 do plano de corte
   de emergência do runbook, de graça.
2. `gpt-4o-mini-tts` via `/api/tts` — **inativo**, exige conta OpenAI em tier
   pago.
3. Web Speech API — padrão atual. Sem chave, sem rede, sem custo.

Trocar entre 2 e 3 é uma constante em `lib/speak.ts`.

`gpt-live-1` foi avaliado e descartado: exige Tier 1+ (Free não é suportado), é
sessão WebRTC em vez de request/response, e full-duplex briga com o RNF02. Fica
como roadmap no fim do vídeo — é o motor natural do passo 4 da jornada do
operador (`03-produto.md`), que hoje não existe no sistema.

**Autoplay.** O Chrome bloqueia áudio sem gesto do usuário e a tela é passiva.
Sem o botão "Armar áudio", a primeira intervenção seria rejeitada em silêncio.

## Slack

O `POST` ao webhook é server-side por dois motivos independentes: o Slack não
devolve CORS para origem arbitrária, e `SLACK_WEBHOOK_URL` como `NEXT_PUBLIC_*`
vazaria o segredo.

`SlackCardPayload` postado cru retorna `invalid_payload` — o Slack espera
`{text}` ou `{blocks}`. O mapeamento domínio → Block Kit vive em
`app/api/slack/route.ts`. **Isso não é mudança de contrato**: o payload que
trafega no WebSocket continua exatamente o do `CONTRACTS.md`.

## Pendente

- CopilotKit (`CopilotPopup` fechado por padrão + `useCopilotReadable` +
  ações `reenviarCardSlack` e `lerEmVozAlta`), runtime no OpenRouter.
- Webhook do Slack: em criação pelo time.
- Chave de LLM: conta OpenAI fora de tier pago. Caminho provável é OpenRouter
  com modelos `:free`.
