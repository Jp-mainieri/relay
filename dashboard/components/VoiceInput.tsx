"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Indicador oficial de "turno sendo escutado" no dashboard do gestor.
 *
 * NÃO captura áudio. Nada aqui toca `getUserMedia` nem o microfone: a captura
 * é do agente de áudio ambiental, e o dashboard só reflete o estado do turno
 * que chega pelo WebSocket. A peça é um indicador, não um controle.
 *
 * Por isso o estado de escuta é PROP, não `useState` interno: quem manda é o
 * snapshot do turno vindo do pai. Um toggle local poderia divergir do backend
 * e mostrar "escutando" com o turno parado — exatamente a confiança falsa que
 * o produto não pode criar.
 *
 * `debugMode` é a única exceção, e é explícita no nome: reativa o clique para
 * simular localmente sem o player de P1 rodando. Nesse modo a prop
 * `isListening` é ignorada de propósito, para os dois modos nunca se
 * misturarem numa fonte de verdade ambígua.
 */

interface Props {
  /** Fonte de verdade: o turno está sendo escutado agora. Vem do snapshot do WS. */
  isListening: boolean;
  /** Intensidade de fala, 0 a 1. Sem ela, as barras usam aleatório como fallback. */
  activityLevel?: number;
  /** Só para demo local: devolve o clique manual e ignora `isListening`. */
  debugMode?: boolean;
  onStart?: () => void;
  onStop?: () => void;
}

const BAR_COUNT = 5;
// Cada barra tem um peso fixo (centro mais alto) para a onda ter forma de voz
// em vez de ruído chapado. Com `activityLevel`, é este perfil que escala.
const BAR_WEIGHTS = [0.55, 0.8, 1, 0.8, 0.55];
const BAR_MIN_PCT = 18;
const BAR_MAX_PCT = 100;
// Reamostragem mais lenta que a transição CSS (240ms), senão as barras cortam
// o movimento no meio e o resultado treme em vez de ondular.
const BAR_RESAMPLE_MS = 320;

function randomBars(): number[] {
  return BAR_WEIGHTS.map((weight) => {
    const amplitude = BAR_MIN_PCT + Math.random() * (BAR_MAX_PCT - BAR_MIN_PCT);
    return Math.max(BAR_MIN_PCT, amplitude * weight);
  });
}

function barsFromActivity(level: number): number[] {
  const clamped = Math.min(1, Math.max(0, level));
  return BAR_WEIGHTS.map((weight) =>
    Math.max(BAR_MIN_PCT, BAR_MIN_PCT + clamped * (BAR_MAX_PCT - BAR_MIN_PCT) * weight),
  );
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function VoiceInput({ isListening, activityLevel, debugMode = false, onStart, onStop }: Props) {
  const [debugListening, setDebugListening] = useState(false);
  const listening = debugMode ? debugListening : isListening;

  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [bars, setBars] = useState<number[]>(() => barsFromActivity(0));

  const hasActivityLevel = typeof activityLevel === "number";

  // onStart/onStop seguem a MUDANÇA de estado, não o clique. Começa em `false`
  // para que montar já escutando conte como início; montar parado não dispara
  // um onStop fantasma.
  const previousListening = useRef(false);
  useEffect(() => {
    if (previousListening.current === listening) return;
    previousListening.current = listening;
    if (listening) onStart?.();
    else onStop?.();
  }, [listening, onStart, onStop]);

  useEffect(() => {
    if (!listening) {
      setElapsedSeconds(0);
      return;
    }
    setElapsedSeconds(0);
    const id = window.setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [listening]);

  useEffect(() => {
    // Com nível real do backend, nada de aleatório: as barras têm que
    // corresponder ao que está sendo dito.
    if (hasActivityLevel) {
      setBars(barsFromActivity(activityLevel as number));
      return;
    }
    if (!listening) {
      setBars(barsFromActivity(0));
      return;
    }
    // Reamostra a cada ciclo. Um array sorteado uma vez e repetido em loop
    // lê como animação mecânica depois da primeira volta.
    setBars(randomBars());
    const id = window.setInterval(() => setBars(randomBars()), BAR_RESAMPLE_MS);
    return () => window.clearInterval(id);
  }, [listening, hasActivityLevel, activityLevel]);

  const label = listening ? "Escutando o turno" : "Turno parado";

  const indicator = (
    <span className="voice-indicator" data-on={listening}>
      <span className="voice-ring" aria-hidden="true" />
      <span className="voice-ring voice-ring--delayed" aria-hidden="true" />
      <MicGlyph />
    </span>
  );

  return (
    <div className="voice-input" data-on={listening} aria-live="polite">
      {debugMode ? (
        <button
          type="button"
          className="voice-trigger"
          onClick={() => setDebugListening((on) => !on)}
          aria-pressed={listening}
          aria-label={`${label}. Clique para alternar (modo debug).`}
        >
          {indicator}
        </button>
      ) : (
        indicator
      )}

      <span className="voice-bars" aria-hidden="true">
        {bars.slice(0, BAR_COUNT).map((height, index) => (
          <span key={index} className="voice-bar" style={{ height: `${height}%` }} />
        ))}
      </span>

      <span className="voice-clock" aria-hidden="true">
        {formatElapsed(elapsedSeconds)}
      </span>

      <span className="sr-only">
        {label}
        {listening ? ` há ${formatElapsed(elapsedSeconds)}` : ""}
      </span>
    </div>
  );
}

/** Microfone estático. Só o anel anima — o ícone girando lia como spinner de loading. */
function MicGlyph() {
  return (
    <svg
      className="voice-mic"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10.5a7 7 0 0 0 14 0" />
      <path d="M12 17.5V21" />
    </svg>
  );
}
