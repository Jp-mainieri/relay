"use client";

import { useEffect, useRef, useState } from "react";
import type {
  InterventionPayload,
  SlackCardMessagePayload,
  TurnState,
  WSMessage,
} from "@shared/types";

/**
 * Canal /ws/{station_id} — CONTRACTS.md seção 3.
 *
 * Regra central do contrato: mensagens `state` carregam o snapshot COMPLETO do
 * turno e devem SUBSTITUIR o estado local inteiro. É isso que torna reconexão
 * no meio da demo segura.
 *
 * Mas `intervention`, `slack_card` e `error` são eventos, não estado. Se
 * ficassem na mesma fatia, o próximo `state` apagaria o overlay de intervenção
 * bem no clímax. Por isso quatro fatias separadas: uma substituível, três
 * acumuláveis.
 *
 * Turno novo: `active_turn` no backend abre um turno novo (turn_id novo,
 * checklist zerado) se uma fala chegar depois de POST /api/turn/end. Ao detectar
 * turn_id diferente, limpamos os eventos — mas quem controla o disparo de TTS e
 * Slack são os refs de dedupe em page.tsx, que nunca são zerados, só
 * sobrescritos. Assim um turno reaberto por acidente não reenvia o card.
 */

export type ConnState = "connecting" | "open" | "closed";

export interface RelayFeed {
  conn: ConnState;
  turn: TurnState | null;
  intervention: InterventionPayload | null;
  slackCard: SlackCardMessagePayload | null;
  errors: { id: number; message: string }[];
  dismissError: (id: number) => void;
}

const RECONNECT_MIN = 600;
const RECONNECT_MAX = 5000;
const PING_EVERY = 20000;

export function useRelaySocket(stationId: string, enabled = true): RelayFeed {
  const [conn, setConn] = useState<ConnState>("connecting");
  const [turn, setTurn] = useState<TurnState | null>(null);
  const [intervention, setIntervention] = useState<InterventionPayload | null>(null);
  const [slackCard, setSlackCard] = useState<SlackCardMessagePayload | null>(null);
  const [errors, setErrors] = useState<{ id: number; message: string }[]>([]);

  const knownTurnId = useRef<string | null>(null);
  const errorSeq = useRef(0);

  useEffect(() => {
    if (!enabled) return;

    const base = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
    let socket: WebSocket | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let alive = true;

    const pushError = (message: string) =>
      setErrors((prev) => [...prev.slice(-2), { id: ++errorSeq.current, message }]);

    const handle = (msg: WSMessage) => {
      switch (msg.type) {
        case "state": {
          const next = msg.payload;
          // Turno novo: os eventos do turno anterior não valem mais.
          if (knownTurnId.current && knownTurnId.current !== next.turn_id) {
            setIntervention(null);
            setSlackCard(null);
          }
          knownTurnId.current = next.turn_id;
          setTurn(next); // substituição integral, nunca merge campo a campo
          break;
        }
        case "intervention":
          setIntervention(msg.payload);
          break;
        case "slack_card":
          setSlackCard(msg.payload);
          break;
        case "error":
          pushError(msg.payload.message);
          break;
      }
    };

    const connect = () => {
      if (!alive) return;
      setConn(attempt === 0 ? "connecting" : "connecting");

      socket = new WebSocket(`${base}/ws/${encodeURIComponent(stationId)}`);

      socket.onopen = () => {
        attempt = 0;
        setConn("open");
        // O servidor só drena o que o cliente manda, para detectar queda.
        ping = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), PING_EVERY);
      };

      socket.onmessage = (event) => {
        try {
          handle(JSON.parse(event.data) as WSMessage);
        } catch {
          pushError("Mensagem do orquestrador em formato inesperado.");
        }
      };

      socket.onclose = () => {
        if (ping) clearInterval(ping);
        if (!alive) return;
        setConn("closed");
        const wait = Math.min(RECONNECT_MIN * 2 ** attempt++, RECONNECT_MAX);
        retry = setTimeout(connect, wait);
      };

      // onerror sempre é seguido de onclose; o retry mora lá.
      socket.onerror = () => socket?.close();
    };

    connect();

    return () => {
      alive = false;
      if (ping) clearInterval(ping);
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [stationId, enabled]);

  const dismissError = (id: number) => setErrors((prev) => prev.filter((e) => e.id !== id));

  return { conn, turn, intervention, slackCard, errors, dismissError };
}
