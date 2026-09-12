/**
 * Relay — Contratos de dados compartilhados (TypeScript).
 *
 * CONGELADO — ver /CONTRACTS.md. Qualquer mudança aqui exige avisar as 4
 * pessoas do time (P1 ingestão, P2 orquestrador, P3 validação, P4 dashboard).
 *
 * Espelha shared/schemas.py campo a campo. Mantido manualmente em sincronia —
 * não há gerador automático no escopo das 4h. Se os dois arquivos divergirem,
 * schemas.py (Pydantic) é a fonte da verdade.
 */

// ---------------------------------------------------------------------------
// 1. Configuração do checklist — POST /api/config
// ---------------------------------------------------------------------------

export interface ChecklistConfig {
  station_id: string;
  items: string[];
}

export interface ChecklistConfigResponse {
  status: "ok";
  station_id: string;
  items: string[];
}

/** Resposta mínima de confirmação, usada pelos endpoints de ingestão (seção 2.5/2.6). */
export interface AckResponse {
  status: "ok";
}

// ---------------------------------------------------------------------------
// 2. Análise — POST /api/analyze
// ---------------------------------------------------------------------------

export interface AnalyzeRequest {
  station_id: string;
  items: string[];
  /** Transcrição acumulada do turno até o momento, como texto único. */
  transcript: string;
}

export interface ChecklistItemStatus {
  item: string;
  covered: boolean;
  /** Trecho literal da fala que comprova a cobertura, ou null se covered=false. */
  evidence: string | null;
}

export interface AnalyzeResponse {
  checklist_status: ChecklistItemStatus[];
  is_complete: boolean;
  /** Frase curta em pt-BR para o TTS. Null quando is_complete=true. */
  intervention_prompt: string | null;
  /** Alerta de reincidência da Ambiguous. Null se ausente ou se a consulta falhou (RNF04). */
  ambiguous_alert: string | null;
  summary: string;
  /**
   * O mesmo resumo já quebrado em bullet points, prontos para o card do
   * Slack (SlackCardPayload.summary_bullets). Preenchido por P3 na mesma
   * chamada de LLM que gera `summary` — não reprocesse `summary` para
   * gerar bullets no dashboard/orquestrador.
   */
  summary_bullets: string[];
}

// ---------------------------------------------------------------------------
// 2.5 Ingestão de transcrição — POST /api/transcript
//
// NOVO — fecha o contrato P1 -> P2. Uma chamada por fala, na ordem em que
// a fala ocorreu. Campos idênticos em nome e tipo a `TranscriptLine`
// (item de `TurnState.transcript_log`) mais `station_id`.
// ---------------------------------------------------------------------------

export interface TranscriptPostRequest {
  station_id: string;
  /** Índice sequencial da fala no turno, começando em 0. P2 ordena por `seq`, não por ordem de chegada HTTP. */
  seq: number;
  /** Ex: "OPERADOR A". Null se não identificado (sem diarização no MVP). */
  speaker: string | null;
  text: string;
  /** ISO 8601 */
  ts: string;
}

export type TranscriptPostResponse = AckResponse;

// ---------------------------------------------------------------------------
// 2.6 Fim de turno — POST /api/turn/end
//
// NOVO — único gatilho de fim de turno. Enviado por P1 após a última fala.
// P2 nunca infere fim de turno por timeout/silêncio.
// ---------------------------------------------------------------------------

export interface TurnEndRequest {
  station_id: string;
}

export type TurnEndResponse = AckResponse;

// ---------------------------------------------------------------------------
// 3. Ambiguous (referência — não consumido diretamente pelo dashboard)
// ---------------------------------------------------------------------------

export interface IncidentReport {
  entity: string;
  description: string;
  severity: "baixa" | "media" | "alta";
}

// PENDÊNCIA (b) RESOLVIDA — ver CONTRACTS.md.
export interface AmbiguousTurnRecord {
  station_id: string;
  turn_id: string;
  /** ISO 8601. Fim do turno. */
  timestamp: string;
  checklist_status: ChecklistItemStatus[];
  is_complete: boolean;
  resolved_pending_items: string[];
  new_incidents: IncidentReport[];
  summary: string;
}

// ---------------------------------------------------------------------------
// 4. Notificação Slack — payload do card
//
// Dono do POST HTTP ao webhook: P4. P2 entrega este payload pronto pelo
// WebSocket (evento `slack_card`, seção 5); P4 só faz o POST.
// ---------------------------------------------------------------------------

export interface SlackCardPayload {
  station_id: string;
  /** ISO 8601 */
  timestamp: string;
  coverage_pct: number;
  ambiguous_alert: string | null;
  /** Copiado direto de AnalyzeResponse.summary_bullets — já vem quebrado por P3. */
  summary_bullets: string[];
}

// ---------------------------------------------------------------------------
// 5. WebSocket — canal /ws/{station_id}
//
// PENDÊNCIA (a) RESOLVIDA — ver CONTRACTS.md. Cada mensagem `state` carrega o
// snapshot COMPLETO do turno (checklist inteiro + transcript_log inteiro).
// Ao renderizar `state`, SUBSTITUA o estado local inteiro — nunca faça merge
// campo a campo. Isso é o que torna a reconexão no meio da demo segura: a
// tela sempre reflete exatamente a última mensagem `state` recebida.
// ---------------------------------------------------------------------------

export type WSEventType = "state" | "intervention" | "slack_card" | "error";

export interface TranscriptLine {
  /** Índice sequencial da fala no turno, começando em 0. */
  seq: number;
  /** Ex: "OPERADOR A". Null se não identificado (sem diarização no MVP). */
  speaker: string | null;
  text: string;
  /** ISO 8601 */
  ts: string;
}

export interface TurnState {
  station_id: string;
  /** Muda a cada novo turno na mesma estação. */
  turn_id: string;
  checklist_status: ChecklistItemStatus[];
  is_complete: boolean;
  ambiguous_alert: string | null;
  summary: string;
  /** Todas as falas do turno até agora, em ordem de `seq`. */
  transcript_log: TranscriptLine[];
  /** ISO 8601 */
  updated_at: string;
}

export interface InterventionPayload {
  station_id: string;
  turn_id: string;
  intervention_prompt: string;
}

/**
 * Payload da mensagem `slack_card` (renomeado de `slack_sent` — era
 * circular: P4 não precisa que o servidor confirme que P4 enviou). Semântica
 * nova, simétrica com `intervention`: P2 entrega o card PRONTO; P4 faz o
 * POST ao Incoming Webhook.
 */
export interface SlackCardMessagePayload {
  station_id: string;
  turn_id: string;
  card: SlackCardPayload;
}

export interface ErrorPayload {
  station_id: string | null;
  message: string;
}

export type WSMessage =
  | { type: "state"; payload: TurnState }
  | { type: "intervention"; payload: InterventionPayload }
  | { type: "slack_card"; payload: SlackCardMessagePayload }
  | { type: "error"; payload: ErrorPayload };

/**
 * Handler de referência — faça um switch exaustivo em `msg.type`:
 *
 * switch (msg.type) {
 *   case "state":        // substituir TODO o estado local por msg.payload
 *   case "intervention": // disparar TTS falando msg.payload.intervention_prompt (uma vez por turno)
 *   case "slack_card":   // fazer o POST de msg.payload.card ao Incoming Webhook (uma vez por turno)
 *   case "error":        // aviso não bloqueante, nunca derruba a tela
 * }
 */
