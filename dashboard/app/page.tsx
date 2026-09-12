"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertBand } from "../components/AlertBand";
import { ChecklistPanel } from "../components/ChecklistPanel";
import { DemoControls, type DemoId } from "../components/DemoControls";
import { ErrorToasts } from "../components/ErrorToasts";
import { InterventionOverlay } from "../components/InterventionOverlay";
import { Topbar } from "../components/Topbar";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { armAudio, isArmed, speakIntervention, stopSpeaking } from "../lib/speak";
import { useRelaySocket } from "../lib/useRelaySocket";
import type { ChecklistConfig, TranscriptPostRequest } from "@shared/types";

const STATION_ID = process.env.NEXT_PUBLIC_STATION_ID ?? "doca-04";
const STALE_AFTER_MS = 3000;
const DEMO_LINE_DELAY_MS = 650;
const DEMO_CHECKLIST: ChecklistConfig = {
  station_id: STATION_ID,
  items: [
    "status da carga refrigerada",
    "liberacao da doca",
    "nivel de bateria das empilhadeiras",
    "avarias ou pendencias de manutencao",
  ],
};

interface DemoPayload {
  title: string;
  description: string;
  lines: Array<{ speaker: string | null; text: string }>;
}

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function postJson(path: string, body: unknown): Promise<void> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Orquestrador respondeu HTTP ${response.status}.`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export default function Dashboard() {
  const { conn, turn, intervention, slackCard, errors, dismissError } =
    useRelaySocket(STATION_ID);

  const [audioArmed, setAudioArmed] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoStatus, setDemoStatus] = useState<string | null>(null);

  /**
   * Dedupe por turn_id. Estes refs NUNCA são zerados — só sobrescritos quando
   * a ação de fato acontece. Um turno reaberto por acidente (fala chegando
   * depois de POST /api/turn/end) traz turn_id novo e passa; uma mensagem
   * repetida do mesmo turno não passa. Zerar aqui reintroduziria o risco de
   * mandar o card duas vezes ao Slack.
   */
  const spokenFor = useRef<string | null>(null);
  const sentFor = useRef<string | null>(null);

  const handleArm = useCallback(() => {
    armAudio();
    setAudioArmed(isArmed());
  }, []);

  const runDemo = useCallback(async (id: DemoId) => {
    if (demoRunning) return;
    setDemoRunning(true);
    setDemoStatus("Carregando cenário…");

    try {
      const demoResponse = await fetch(`/api/demo/${id}`);
      if (!demoResponse.ok) throw new Error("Não foi possível carregar a transcrição de demonstração.");
      const demo = (await demoResponse.json()) as DemoPayload;

      setDemoStatus(`Configurando: ${demo.title}.`);
      await postJson("/api/config", DEMO_CHECKLIST);

      for (const [seq, line] of demo.lines.entries()) {
        const payload: TranscriptPostRequest = {
          station_id: STATION_ID,
          seq,
          speaker: line.speaker,
          text: line.text,
          ts: new Date(Date.now() + seq * 1000).toISOString(),
        };
        setDemoStatus(`${demo.title}: fala ${seq + 1} de ${demo.lines.length}.`);
        await postJson("/api/transcript", payload);
        if (seq < demo.lines.length - 1) await delay(DEMO_LINE_DELAY_MS);
      }

      await postJson("/api/turn/end", { station_id: STATION_ID });
      setDemoStatus(`${demo.title} concluído.`);
    } catch (error) {
      setDemoStatus(error instanceof Error ? error.message : "A demonstração falhou.");
    } finally {
      setDemoRunning(false);
    }
  }, [demoRunning]);

  // Válvula de escape na gravação: aumenta a escala inteira em 25%.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.shiftKey && e.key.toLowerCase() === "d") {
        const root = document.documentElement;
        root.dataset.scale = root.dataset.scale === "up" ? "" : "up";
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // RF07 — fala a intervenção, no máximo uma vez por turno.
  useEffect(() => {
    if (!intervention) return;
    if (spokenFor.current === intervention.turn_id) return;
    spokenFor.current = intervention.turn_id;

    setSpeaking(true);
    void speakIntervention(intervention.intervention_prompt, () => setSpeaking(false));
    return () => stopSpeaking();
  }, [intervention]);

  // RF09 — POST do card ao webhook, via route handler. Uma vez por turno.
  useEffect(() => {
    if (!slackCard) return;
    if (sentFor.current === slackCard.turn_id) return;
    sentFor.current = slackCard.turn_id;

    void fetch("/api/slack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(slackCard.card),
    }).catch(() => {
      /* RNF04: falha no Slack não pode quebrar a tela */
    });
  }, [slackCard]);

  const stale = useStale(turn?.updated_at ?? null, conn === "open");
  const started = (turn?.transcript_log.length ?? 0) > 0;

  return (
    <>
      <div className="shell">
        <Topbar
          stationId={turn?.station_id ?? STATION_ID}
          conn={conn}
          updatedAt={turn?.updated_at ?? null}
          audioArmed={audioArmed}
          onArm={handleArm}
        />

        <DemoControls onRun={runDemo} running={demoRunning} status={demoStatus} />

        {turn?.ambiguous_alert ? <AlertBand text={turn.ambiguous_alert} /> : <span />}

        <main className="stage">
          <TranscriptPanel
            lines={turn?.transcript_log ?? []}
            processing={started && stale && !turn?.is_complete}
          />
          <ChecklistPanel items={turn?.checklist_status ?? []} />
        </main>
      </div>

      {intervention && (
        <InterventionOverlay
          text={intervention.intervention_prompt}
          speaking={speaking}
        />
      )}

      <ErrorToasts errors={errors} onDismiss={dismissError} />
    </>
  );
}

/**
 * Não há sinal de "estou processando" no contrato — e não deveria haver, é
 * detalhe interno do P2. Mas o teto de validação é de 8s, e uma tela parada
 * por 8s no vídeo parece travada. Silêncio prolongado depois do último `state`
 * vira feedback em vez de congelamento.
 */
function useStale(updatedAt: string | null, connected: boolean): boolean {
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!updatedAt || !connected) {
      setStale(false);
      return;
    }
    setStale(false);
    const timer = setTimeout(() => setStale(true), STALE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [updatedAt, connected]);

  return stale;
}
