"use client";

interface Props {
  text: string;
  speaking: boolean;
}

/**
 * Não é modal e não bloqueia: transcrição e checklist continuam visíveis atrás.
 * O texto na tela é a terceira camada da voz — se TTS e Web Speech falharem, a
 * intervenção continua legível.
 */
export function InterventionOverlay({ text, speaking }: Props) {
  return (
    <div className="intervention" role="alert">
      <svg className="speaker-icon" data-speaking={speaking} viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M4 9.5v5h3.5L12 19V5L7.5 9.5H4z"
          fill="currentColor"
        />
        <path
          d="M15.5 8.8a4.2 4.2 0 010 6.4M18 6.2a7.8 7.8 0 010 11.6"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
      <p className="intervention-text">{text}</p>
    </div>
  );
}
