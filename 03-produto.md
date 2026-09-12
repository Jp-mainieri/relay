# Relay — Produto e Validação

## Nome e conceito
**Relay** — referência à *relay race* (corrida de revezamento): a vitória depende de passar o bastão sem deixá-lo cair. O produto garante que nenhuma falha operacional passe despercebida na troca de equipes.

## Personas

**Operador de turno**
- Trabalha em doca/estação, faz a passagem verbal do turno para o colega seguinte.
- Não interage com telas durante a conversa — usuário passivo/ambiental.
- Dor: itens críticos (avarias, bateria, pendências) esquecidos verbalmente e só descobertos horas depois.

**Gestor de operação**
- Acompanha múltiplas estações, não está fisicamente presente em cada passagem de turno.
- Consome informação via Slack/Teams e, eventualmente, o dashboard ao vivo.
- Dor: falta de visibilidade e de histórico estruturado das passagens de turno.

## Jornada do usuário (operador)
1. Chega para a passagem de turno; o Relay já está "ouvindo" ambientalmente.
2. Conversa naturalmente com o colega, sem interagir com o sistema.
3. Ao final, se algo crítico não foi mencionado, o Relay intervém uma única vez por voz.
4. Operador responde/complementa verbalmente; turno se encerra.

## Jornada do usuário (gestor)
1. Configura o checklist da estação uma vez (texto livre).
2. Opcionalmente acompanha o dashboard ao vivo durante a passagem de turno.
3. Recebe o resumo estruturado no Slack ao final, com alerta de reincidência se houver.

## Validação do problema
Problem-solution fit assumido como dado pelo enunciado do desafio (falhas na passagem de turno é um problema operacional conhecido em ambientes logísticos/industriais). Não houve etapa de validação com usuários reais dentro do escopo do hackathon — ponto a declarar na apresentação, se perguntado.

## Escopo do MVP ("Caminho Feliz")
Fluxo ponta a ponta com foco em impacto visual e integração sólida com o parceiro Ambiguous:
1. Checklist configurado
2. Conversa simulada/real transcrita
3. Cards mudando de estado ao vivo
4. Consulta de reincidência na Ambiguous
5. Intervenção por voz se faltar item
6. Resumo publicado no Slack

Ver `01-requisitos.md` para o que está explicitamente fora do MVP.
