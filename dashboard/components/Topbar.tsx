"use client";

import type { ConnState } from "../lib/useRelaySocket";

interface Props {
  stationId: string;
  conn: ConnState;
  updatedAt: string | null;
  audioArmed: boolean;
  onArm: () => void;
}

const CONN_LABEL: Record<ConnState, string> = {
  connecting: "Conectando",
  open: "Ao vivo",
  closed: "Sem conexão",
};

export function Topbar({ stationId, conn, updatedAt, audioArmed, onArm }: Props) {
  return (
    <header className="topbar">
      <span className="wordmark">Relay</span>
      <span className="station">{stationId}</span>

      <span className="spacer" />

      {!audioArmed && (
        <button className="arm" onClick={onArm}>
          Armar áudio
        </button>
      )}

      <span className="live" data-on={conn === "open"}>
        <span className="live-dot" />
        {CONN_LABEL[conn]}
      </span>

      <span className="clock">{formatClock(updatedAt)}</span>
    </header>
  );
}

function formatClock(iso: string | null): string {
  if (!iso) return "--:--:--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--:--:--" : d.toLocaleTimeString("pt-BR", { hour12: false });
}
