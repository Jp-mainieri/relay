"use client";

import { useEffect, useRef } from "react";
import type { TranscriptLine } from "@shared/types";

interface Props {
  lines: TranscriptLine[];
  /** P2 pode levar até 8s numa fala (VALIDATION_TIMEOUT_SECONDS). Sem isto, a
   *  tela parece travada em vez de ocupada. */
  processing: boolean;
}

export function TranscriptPanel({ lines, processing }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length, processing]);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Transcrição</h2>
        <span className="panel-note">
          {lines.length === 0 ? "aguardando" : `${lines.length} falas`}
        </span>
      </div>

      <div className="panel-body" ref={bodyRef}>
        {lines.length === 0 && (
          <p className="empty">A passagem de turno ainda não começou.</p>
        )}

        {lines.map((line) => (
          <p key={line.seq} className="line" data-anon={line.speaker === null}>
            <span className="line-who">{line.speaker ?? "—"}</span>
            <span className="line-text">{line.text}</span>
          </p>
        ))}

        {processing && (
          <p className="thinking">
            <span className="thinking-dot" />
            analisando
          </p>
        )}
      </div>
    </section>
  );
}
