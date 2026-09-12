# Relay — Runbook de Execução

**4 máquinas · 2 IAs por máquina · 4 horas**

> Cada pessoa lê APENAS a sua seção. A seção "Regras Globais" todo mundo lê.
> Prompts em bloco de código são para colar literalmente.

---

## Regras Globais (todos leem antes de começar)

**Divisão de papéis entre as IAs — não negocie isto durante a execução:**

| | Claude Code | Codex |
|---|---|---|
| Escreve código que vai pra `main` | SIM | NÃO |
| Onde trabalha | `/backend`, `/dashboard`, `/shared` | `/scratch`, `/mocks`, arquivos standalone |
| Papel | implementador | crítico, gerador de conteúdo, harness de teste |

**Regra do escritor único:** nenhum arquivo é editado por duas IAs. Se o Codex produzir algo que deve entrar na `main`, VOCÊ copia manualmente para o Claude Code integrar. Nunca deixe os dois editando o mesmo diretório.

**Branches:** `feat/ingestao` (P1), `feat/orquestrador` (P2), `feat/validacao` (P3), `feat/dashboard` (P4). `/scratch` está no `.gitignore`.

**Canal de time:** avise no Slack/grupo quando (a) seu branch estiver rodando com mocks, (b) você bloquear alguém, (c) você quiser mudar um contrato congelado.

---

## Linha do tempo geral

| Tempo | O que acontece |
|-------|----------------|
| 0:00–0:15 | **P2 sozinho** roda a Fase 0. P1, P3, P4 esperam (leem os docs, configuram ambiente, testam chaves de API) |
| 0:15–0:30 | P2 publica contratos. **Todos** rodam o Codex de crítica dos contratos em paralelo. Ajustes finais. `git pull` geral |
| 0:30–2:00 | Desenvolvimento paralelo. Claude Code implementa, Codex faz o trabalho lateral de cada um |
| 2:00–2:30 | **Marco de integração** (P2 conduz, os outros param e ficam disponíveis) |
| 2:30–3:30 | Correção de integração + substituição de mocks pela lógica real |
| 3:30–3:50 | Ensaio da demo, 3 execuções completas |
| 3:50–4:00 | Blindagem final / corte de escopo de emergência |

---

# MÁQUINA 1 — P1 · Ingestão

**Você é dono de:** camada de entrada (transcrição) e das transcrições de teste que o time inteiro vai usar.
**Você bloqueia:** P3 (precisa das suas transcrições para testar o motor de validação). **Entregue-as primeiro.**

### 0:15 — Codex · crítica dos contratos

```
Abaixo está o CONTRACTS.md de um sistema que 4 pessoas vão desenvolver em
paralelo, em máquinas separadas, nas próximas 4 horas.

Meu papel no projeto é a camada de ingestão: recebo áudio ou texto e entrego
transcrição contínua ao orquestrador.

Analise SOMENTE do meu ponto de vista: o contrato de entrega da transcrição está
sem ambiguidade? Falta algum campo que eu precisaria enviar (timestamp, ordem dos
turnos de fala, marcação de fim de turno)? Liste os problemas em bullets. Não
reescreva o contrato.

[cole o CONTRACTS.md]
```

### 0:30 — Codex · gerar transcrições de teste (FAÇA ISTO PRIMEIRO)

```
Gere 8 transcrições realistas de passagem de turno em um centro de distribuição
logístico brasileiro, em português do Brasil, entre dois operadores de doca.

Contexto: o checklist da estação cobre (1) status da carga refrigerada,
(2) liberação da doca, (3) nível de bateria das empilhadeiras, (4) avarias ou
pendências de manutenção.

Requisitos de realismo — isto é mais importante que clareza:
- Gíria de chão de operação, frases cortadas, interrupções, "né", "beleza"
- Os itens do checklist mencionados de forma INDIRETA, nunca com as palavras do
  checklist (ex: "a Swift já tá no plug 3" em vez de "carga refrigerada ok")
- Assunto paralelo no meio (futebol, troca de escala, almoço)

Distribua assim:
- 3 transcrições cobrindo TODOS os 4 itens
- 3 cobrindo 3 dos 4 (varie qual falta)
- 2 mencionando explicitamente a "empilhadeira 2" com problema de recarga

Formato: um bloco por transcrição, falas prefixadas por "OPERADOR A:" e
"OPERADOR B:", 15 a 25 falas cada. Sem comentários ou explicação.
```

**Você escolhe 3** (uma completa, uma incompleta, uma com a empilhadeira 2), salva em `/mocks/transcricoes/` e **avisa o P3 imediatamente**.

### 0:40 — Claude Code · implementação

```
Leia os documentos 01 a 05 em anexo e o CONTRACTS.md do repositório.

REGRAS DE PARALELISMO — obrigatórias:
- Os contratos em /shared e /mocks estão CONGELADOS. Se achar que um precisa
  mudar, PARE e me avise — outras 3 pessoas dependem dele.
- Trabalhe só dentro da sua fronteira. Não edite arquivos das outras.
- Consuma os mocks em /mocks para tudo que dependa de outra fronteira.
- Commits pequenos e frequentes no branch feat/ingestao.
- Prazo: 4 horas. Priorize o caminho feliz da demo. Se algo ameaçar estourar o
  tempo, proponha o corte antes de insistir.

Sua fronteira: a camada de entrada do Relay.

1. Implemente a ingestão por TEXTO: uma interface que injeta transcrição
   contínua, simulando uma conversa em andamento (fala por fala, com delay
   configurável, não tudo de uma vez). Este é o caminho de demo garantido —
   precisa funcionar 100%.
2. Consuma as transcrições de /mocks/transcricoes/ como fonte da simulação.
3. Entregue ao orquestrador no formato definido em CONTRACTS.md.
4. SÓ DEPOIS que tudo acima rodar, adicione captura por microfone com STT real.
   Se o STT der qualquer trabalho, abandone, documente e me avise.
```

### 1:30 — Codex · revisão (enquanto o Claude Code trabalha)

```
Revise este código de uma camada de ingestão de transcrição para um sistema
ao vivo. Foque em: o que quebra se a conexão cair no meio da demo? O que quebra
se duas transcrições forem injetadas em sequência sem reset de estado?
Liste os riscos, não reescreva.

[cole o código]
```

---

# MÁQUINA 2 — P2 · Orquestrador

**Você é dono de:** contratos, hub FastAPI, WebSocket, e da condução do marco de integração.
**Você bloqueia:** todo mundo, nos primeiros 15 minutos. Depois, P4.

### 0:00 — Claude Code · FASE 0 (o time inteiro está esperando você)

```
Você vai montar o esqueleto compartilhado de um projeto de hackathon chamado
Relay. Leia todos os documentos em anexo (01-requisitos, 02-especificacao,
03-produto, 04-planejamento, 05-arquitetura) antes de escrever qualquer código.

CONTEXTO CRÍTICO: quatro pessoas vão desenvolver EM PARALELO, em quatro máquinas
separadas, a partir do que você gerar agora. Tudo que você deixar ambíguo vai ser
resolvido de quatro formas incompatíveis. Seu único objetivo nesta rodada é
eliminar ambiguidade — NÃO implemente lógica de negócio.

Entregue, nesta ordem:

1. Estrutura de monorepo:
   /backend      (FastAPI)
   /dashboard    (CopilotKit / Next.js)
   /shared       (contratos: schemas Pydantic + equivalentes TypeScript)
   /mocks        (payloads de exemplo, um .json por contrato)
   /scratch      (no .gitignore)

2. Em /shared, os modelos Pydantic COMPLETOS dos contratos de 05-arquitetura.md:
   ChecklistConfig, ChecklistItemStatus, AnalyzeResponse. Gere os tipos
   TypeScript equivalentes.

3. RESOLVA as duas pendências declaradas em 05-arquitetura.md. Para cada uma:
   apresente as opções, recomende UMA com justificativa curta, implemente a
   recomendada.
   a) Formato das mensagens WebSocket (incremental por item vs. payload completo).
      Considere: cards mudando de cinza para verde ao vivo, e reconexão no meio
      da demo não pode quebrar a tela.
   b) Schema do objeto gravado na Ambiguous ao fim do turno.

4. Stubs de TODOS os endpoints retornando os mocks com dados fixos:
   POST /api/config, POST /api/analyze, canal WebSocket. Devem rodar e responder
   de verdade — é isso que desbloqueia P1, P3 e P4.

5. .env.example com OPENAI_API_KEY, AMBIGUOUS_API_KEY, SLACK_WEBHOOK_URL e a
   chave de TTS.

6. CONTRACTS.md na raiz documentando cada contrato e marcando-os como CONGELADOS.

Não implemente: chamada real à OpenAI, Ambiguous, TTS, ou webhook real do Slack.
```

**Commit + push na `main`. Avise o time.** Só então os outros rodam a crítica do Codex.

### 0:30 — Claude Code · implementação

```
[cole o mesmo bloco "REGRAS DE PARALELISMO" da Máquina 1]

Sua fronteira: o hub do sistema. Você criou os stubs na Fase 0; torne-os reais.

1. POST /api/config — persiste o checklist da estação em memória.
2. Recebe a transcrição contínua de P1 e mantém o estado do turno.
3. Chama o motor de validação de P3 (use o mock enquanto P3 não entrega) e
   empurra o estado atualizado pelo WebSocket a cada mudança.
4. Detecta o fim do turno e dispara os EVENTOS: se is_complete=false, evento de
   intervenção TTS; sempre, evento de envio Slack. Quem EXECUTA TTS e Slack é P4.
5. RNF04: falha na Ambiguous NÃO pode travar o fluxo. Isole em try/except e siga
   com ambiguous_alert=null.

Você é o ponto de integração de todo mundo. Se alguma fronteira atrasar, o sistema
tem que rodar ponta a ponta com o mock dela no lugar. Branch: feat/orquestrador.
```

### 2:00 — Claude Code · marco de integração (você conduz)

```
Todas as 4 fronteiras foram desenvolvidas em paralelo contra mocks. Faça o merge
dos branches feat/ingestao, feat/orquestrador, feat/validacao e feat/dashboard na
main e rode o fluxo ponta a ponta com a transcrição de teste que FALTA um item do
checklist.

Reporte, em ordem de gravidade:
1. Incompatibilidades de contrato entre as fronteiras (o erro mais provável)
2. Pontos onde o fluxo trava
3. O que ainda está consumindo mock em vez da implementação real

NÃO conserte nada ainda. Primeiro me dê o diagnóstico completo — eu decido o que
vale corrigir no tempo restante e o que a gente corta.
```

### 2:20 — Codex · segunda opinião sobre a integração

```
Este é o diff de um merge de 4 branches desenvolvidos em paralelo contra mocks,
num projeto com 4 horas de prazo. Faltam ~1h40.

Aponte apenas o que quebraria uma demo ao vivo: incompatibilidade de tipos entre
fronteiras, estado compartilhado mal isolado, chamadas externas sem timeout,
condições de corrida no WebSocket. Ordene por probabilidade de acontecer durante
uma apresentação de 5 minutos. Não sugira refatoração.

[cole o diff]
```

---

# MÁQUINA 3 — P3 · Validação + Ambiguous

**Você é dono de:** a inteligência do sistema. Sua saída determina se a demo é convincente ou constrangedora.
**Você depende de:** transcrições do P1 (peça já) e da doc da Ambiguous.

Seu trabalho tem dois arquivos que nunca se tocam: o **motor** (Claude Code) e o **harness de avaliação** (Codex). Rode os dois em paralelo o tempo todo.

### 0:15 — Codex · crítica dos contratos

```
Abaixo está o CONTRACTS.md de um sistema desenvolvido por 4 pessoas em paralelo.

Meu papel: motor de validação. Recebo transcrição + lista de itens de checklist e
devo produzir, por item, covered (bool) e evidence (trecho literal da fala ou
null), além de is_complete, intervention_prompt, summary e ambiguous_alert.

Analise SOMENTE do meu ponto de vista: o schema AnalyzeResponse comporta tudo que
preciso emitir? Há campo ambíguo sobre quem preenche (eu ou o orquestrador)?
Liste em bullets. Não reescreva.

[cole o CONTRACTS.md]
```

### 0:30 — Codex · harness de avaliação (arquivo standalone em `/scratch`)

```
Escreva um script Python standalone de avaliação, sem dependência do resto do
projeto, para medir a qualidade de um motor de extração baseado em LLM.

O motor tem a assinatura: analisar(transcricao: str, itens: list[str]) -> dict
retornando {"checklist_status": [{"item", "covered", "evidence"}], ...}

O script deve:
1. Ler transcrições de /mocks/transcricoes/*.txt
2. Ler o gabarito de /scratch/gabarito.json, no formato
   {"nome_arquivo": {"item": true/false}}
3. Rodar o motor contra cada transcrição
4. Imprimir uma tabela por transcrição: item | esperado | obtido | evidence
5. Destacar em vermelho os FALSOS POSITIVOS (esperado=false, obtido=true) —
   este é o erro mais grave, separe-o dos falsos negativos na contagem final
6. Imprimir um placar: total de acertos, falsos positivos, falsos negativos

Importe o motor de backend/validacao.py, mas não assuma nada sobre a implementação
interna dele. Se o import falhar, use um stub e avise.
```

Você preenche o `gabarito.json` **à mão** — é o único ponto do projeto onde um humano precisa decidir a verdade.

### 0:40 — Claude Code · motor de validação

```
[cole o bloco "REGRAS DE PARALELISMO" da Máquina 1]

Sua fronteira: a inteligência do sistema. Branch: feat/validacao.

1. Motor de validação: dada a transcrição e a lista de itens do checklist, use
   OpenAI com saída estruturada forçada por Pydantic (modelo AnalyzeResponse de
   /shared) para determinar, POR ITEM: covered (bool) e evidence (o trecho
   literal da fala que comprova, ou null).
   - Comparação CONTEXTUAL, não por palavra-chave. "Carga da Swift já tá no
     plug 3" cobre "status da carga refrigerada".
   - FALSO POSITIVO É O PIOR ERRO POSSÍVEL NA DEMO. Instrua o modelo a marcar
     covered=true apenas com evidência explícita na fala. Na dúvida, false.
2. Gere também: is_complete, intervention_prompt (a frase que o TTS vai falar,
   em português natural e curta) e summary.
3. Integração Ambiguous: ao detectar entidades críticas mencionadas (equipamentos,
   números de doca), consulte registros dos últimos 7 dias e produza o
   ambiguous_alert. Ao fim do turno, grave o objeto estruturado no schema do
   CONTRACTS.md.
4. Exponha o motor como analisar(transcricao: str, itens: list[str]) -> dict em
   backend/validacao.py — existe um harness de avaliação que importa essa
   assinatura exata. Não mude a assinatura.

Se a Ambiguous não responder ou a documentação dela divergir do que assumimos,
PARE e me avise imediatamente — não invente a integração.
```

### 1:00 em diante — o loop

Rode o harness → veja os falsos positivos → cole a tabela no Claude Code:

```
O harness de avaliação rodou contra as transcrições de teste. Resultado abaixo.

Os FALSOS POSITIVOS são o problema — o modelo marcou covered=true sem evidência
real na fala. Ajuste o prompt de extração para eliminá-los, sem transformá-los em
falsos negativos nos casos onde a evidência existe mas é indireta.

Me mostre o prompt novo e explique o que mudou e por quê, antes de eu rodar o
harness de novo.

[cole a tabela do harness]
```

Repita até zerar os falsos positivos. **Este loop é o trabalho mais valioso do projeto inteiro** — não o abandone para ajudar em outra fronteira.

---

# MÁQUINA 4 — P4 · Dashboard + Saídas

**Você é dono de:** tudo que o público vê e ouve. Impacto visual é critério de avaliação.
**Risco específico seu:** TTS e Slack dependem de serviço externo. Teste os dois **na primeira hora**.

### 0:15 — Codex · crítica dos contratos

```
Abaixo está o CONTRACTS.md de um sistema desenvolvido por 4 pessoas em paralelo.

Meu papel: dashboard em tempo real consumindo WebSocket, mais disparo de TTS e
envio de card ao Slack.

Analise SOMENTE do meu ponto de vista: com as mensagens WebSocket definidas,
consigo renderizar cards mudando de estado ao vivo sem estado local adivinhado? O
que acontece se eu conectar no meio de um turno já em andamento? Os eventos de
TTS e Slack estão distinguíveis das atualizações de estado? Liste em bullets.

[cole o CONTRACTS.md]
```

### 0:30 — Codex · spikes visuais (HTML standalone em `/scratch`)

```
Gere 3 layouts ALTERNATIVOS e visualmente distintos para um dashboard de
monitoramento operacional ao vivo, cada um como um arquivo HTML standalone com
CSS inline e dados fixos (sem backend).

Conteúdo a exibir em todos os 3:
- Painel de transcrição ao vivo de uma conversa entre dois operadores
- 4 cards de checklist, cada um em estado cinza (pendente) ou verde (coberto),
  com a evidência (trecho da fala) visível ao passar o mouse
- Um banner de alerta de histórico ("Empilhadeira 2 falhou nos últimos 2 turnos")
- Percentual do checklist coberto, em destaque

Contexto: será projetado num telão durante uma apresentação de 5 minutos, visto a
distância. Legibilidade a distância e clareza da mudança cinza→verde importam mais
que sofisticação. Faça os 3 seguirem direções estéticas realmente diferentes —
não 3 variações da mesma ideia.
```

Abra os 3, escolha um, **descreva em palavras** para o Claude Code. Não cole o HTML — ele implementa em CopilotKit do zero.

### 0:45 — Claude Code · implementação

```
[cole o bloco "REGRAS DE PARALELISMO" da Máquina 1]

Sua fronteira: tudo que o público vê e ouve na demo. Branch: feat/dashboard.
Impacto visual é critério de avaliação — trate como prioridade, não enfeite.

ANTES DE TUDO: implemente e teste isoladamente o TTS e o webhook do Slack, com
dados fixos, sem depender de nenhuma outra parte do sistema. Os dois dependem de
serviço externo e são a parte mais visível da demo. Me confirme que os dois
funcionam antes de seguir.

Depois:
1. Dashboard CopilotKit, tela única, consumindo o WebSocket (use os mocks de
   /mocks até o P2 entregar o canal real):
   - Transcrição aparecendo ao vivo conforme a conversa avança
   - Cards do checklist mudando de cinza para verde, com transição visível
   - Evidência (trecho da fala) acessível em cada card coberto
   - Alerta da Ambiguous em destaque quando presente
   - Percentual coberto em destaque
   Direção visual desejada: [DESCREVA AQUI o spike que você escolheu]
2. TTS: ao receber o evento de intervenção do P2, sintetizar e tocar o
   intervention_prompt. UMA vez só por turno.
3. Slack: card compacto via Incoming Webhook — station_id, data/hora, percentual
   coberto, ambiguous_alert, summary em bullets.
```

### 3:30 — Claude Code · ensaio (você conduz, time todo assiste)

```
Rode o caminho feliz completo três vezes seguidas, do zero, como se fosse a
apresentação. Anote qualquer passo que exija intervenção manual, qualquer latência
acima de 3 segundos, e qualquer coisa que tenha falhado em ao menos uma das três
execuções. Me entregue essa lista — é o roteiro do que blindar no tempo final.
```

---

## Plano de corte de emergência (se às 3:30 algo não fechar)

Corte nesta ordem, de cima para baixo:

1. **STT por microfone** → demo com transcrição injetada por texto (já era o plano A)
2. **Gravação na Ambiguous** → mantenha só a leitura/alerta de reincidência
3. **Leitura da Ambiguous** → `ambiguous_alert = null`, o RNF04 já cobre isso
4. **TTS** → mostre o `intervention_prompt` em destaque na tela e leia em voz alta

**Nunca corte:** cards mudando ao vivo, motor de validação, webhook do Slack. Esses três são a demo.
