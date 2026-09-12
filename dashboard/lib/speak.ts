"use client";

/**
 * Camada de voz da intervenção (RF07).
 *
 * Uma interface, duas implementações trocáveis por constante. Espelha o padrão
 * que P2 já usa em backend/validation_client.py: tenta o caminho bom, cai para
 * o garantido, nunca propaga exceção.
 *
 *   "webspeech" — voz do navegador. Sem chave, sem rede, sem custo. Padrão
 *                 enquanto a conta OpenAI não estiver em tier pago.
 *   "openai"    — POST /api/tts (route handler server-side, chave nunca no
 *                 browser). Voz muito melhor. Trocar a constante quando houver
 *                 chave; o fallback continua ativo no catch.
 *
 * Terceira camada, sempre presente: o overlay já mostra o texto na tela. Se as
 * duas falharem, a intervenção continua legível — que é o item 4 do plano de
 * corte de emergência do runbook, de graça.
 */

export type VoiceProvider = "webspeech" | "openai";
export const VOICE_PROVIDER: VoiceProvider = "webspeech";

export type SpeakOutcome = "spoken" | "text-only";

let armed = false;
let current: HTMLAudioElement | null = null;

/**
 * O Chrome bloqueia áudio sem gesto do usuário. A tela é passiva — ninguém
 * clica em nada durante o turno — então a primeira intervenção seria rejeitada
 * em silêncio. Este destravamento precisa rodar dentro de um onClick real.
 */
export function armAudio(): void {
  if (armed) return;
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (Ctx) void new Ctx().resume();
  } catch {
    /* sem AudioContext: o <audio> ainda pode funcionar */
  }
  try {
    // Fala vazia dentro do gesto: é o que habilita speechSynthesis depois.
    const warmup = new SpeechSynthesisUtterance("");
    warmup.volume = 0;
    window.speechSynthesis?.speak(warmup);
  } catch {
    /* navegador sem Web Speech */
  }
  armed = true;
}

export function isArmed(): boolean {
  return armed;
}

export async function speakIntervention(
  text: string,
  onEnd?: () => void,
): Promise<SpeakOutcome> {
  if (VOICE_PROVIDER === "openai") {
    try {
      return await speakViaOpenAI(text, onEnd);
    } catch {
      /* cai para o navegador */
    }
  }
  try {
    return speakViaBrowser(text, onEnd);
  } catch {
    onEnd?.();
    return "text-only";
  }
}

export function stopSpeaking(): void {
  try {
    window.speechSynthesis?.cancel();
  } catch {
    /* noop */
  }
  current?.pause();
  current = null;
}

async function speakViaOpenAI(text: string, onEnd?: () => void): Promise<SpeakOutcome> {
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`tts ${res.status}`);

  const url = URL.createObjectURL(await res.blob());
  const audio = new Audio(url);
  current = audio;
  audio.onended = () => {
    URL.revokeObjectURL(url);
    onEnd?.();
  };
  await audio.play();
  return "spoken";
}

function speakViaBrowser(text: string, onEnd?: () => void): SpeakOutcome {
  const synth = window.speechSynthesis;
  if (!synth) {
    onEnd?.();
    return "text-only";
  }

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "pt-BR";
  utterance.rate = 0.98; // tom de operador de rádio: pausado, sem urgência
  utterance.pitch = 1;

  const ptVoice = synth.getVoices().find((v) => v.lang?.toLowerCase().startsWith("pt"));
  if (ptVoice) utterance.voice = ptVoice;

  utterance.onend = () => onEnd?.();
  utterance.onerror = () => onEnd?.();

  synth.cancel(); // garante uma fala por vez
  synth.speak(utterance);
  return "spoken";
}
