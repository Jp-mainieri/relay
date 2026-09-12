import { NextResponse } from "next/server";

/**
 * Síntese da intervenção. Server-side porque a chave nunca pode ir ao browser.
 *
 * Não está no caminho ativo enquanto VOICE_PROVIDER em lib/speak.ts for
 * "webspeech" — a conta OpenAI precisa estar em tier pago. Quando estiver,
 * troque a constante lá; nada aqui muda.
 *
 * `instructions` só existe nos modelos novos de TTS e é o que dá o tom certo:
 * uma intervenção operacional deve soar calma e factual, não alarmada.
 * `wav` é o formato mais rápido de primeira resposta.
 */

export const runtime = "nodejs";

const MODEL = "gpt-4o-mini-tts";
const VOICE = "sage";
const TONE =
  "Fale em português do Brasil com tom calmo e objetivo, ritmo pausado, " +
  "sem urgência nem alarme — como um operador de rádio passando um aviso de rotina.";

export async function POST(request: Request) {
  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY não configurada no ambiente do servidor." },
      { status: 503 },
    );
  }

  let text: string;
  try {
    ({ text } = (await request.json()) as { text: string });
  } catch {
    return NextResponse.json({ error: "Corpo da requisição não é JSON válido." }, { status: 400 });
  }

  if (!text?.trim()) {
    return NextResponse.json({ error: "Campo `text` vazio." }, { status: 400 });
  }

  const upstream = await fetch("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      voice: VOICE,
      input: text,
      instructions: TONE,
      response_format: "wav",
    }),
  });

  if (!upstream.ok) {
    return NextResponse.json(
      { error: `OpenAI recusou: ${upstream.status} ${await upstream.text()}` },
      { status: 502 },
    );
  }

  return new NextResponse(upstream.body, {
    headers: { "Content-Type": "audio/wav", "Cache-Control": "no-store" },
  });
}
