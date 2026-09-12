import { NextResponse } from "next/server";
import type { SlackCardPayload } from "@shared/types";

/**
 * RF09 — POST do card ao Incoming Webhook.
 *
 * Por que server-side e não direto do browser, dois motivos independentes:
 *   1. O webhook do Slack não devolve cabeçalho CORS para origem arbitrária.
 *   2. SLACK_WEBHOOK_URL como NEXT_PUBLIC_* vazaria o segredo para qualquer um
 *      que abrisse o DevTools — o próprio .env.example avisa isso.
 *
 * O CONTRACTS.md diz "P4 faz o POST desse objeto". Ao pé da letra não funciona:
 * o Slack espera {text} ou {blocks} e devolve invalid_payload para qualquer
 * outra coisa. O mapeamento domínio -> Block Kit é implementação da fronteira
 * de P4, não mudança de contrato — o SlackCardPayload continua igual.
 */

export const runtime = "nodejs";

export async function POST(request: Request) {
  const webhook = process.env.SLACK_WEBHOOK_URL;
  if (!webhook) {
    return NextResponse.json(
      { error: "SLACK_WEBHOOK_URL não configurada no ambiente do servidor." },
      { status: 503 },
    );
  }

  let card: SlackCardPayload;
  try {
    card = (await request.json()) as SlackCardPayload;
  } catch {
    return NextResponse.json({ error: "Corpo da requisição não é JSON válido." }, { status: 400 });
  }

  const slackRes = await fetch(webhook, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toBlockKit(card)),
  });

  if (!slackRes.ok) {
    return NextResponse.json(
      { error: `Slack recusou: ${slackRes.status} ${await slackRes.text()}` },
      { status: 502 },
    );
  }

  return NextResponse.json({ status: "ok" });
}

function toBlockKit(card: SlackCardPayload) {
  const when = formatWhen(card.timestamp);
  const blocks: unknown[] = [
    {
      type: "header",
      text: { type: "plain_text", text: `Passagem de turno — ${card.station_id}`, emoji: false },
    },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: `*Checklist coberto*\n${card.coverage_pct}%` },
        { type: "mrkdwn", text: `*Encerrado*\n${when}` },
      ],
    },
  ];

  if (card.ambiguous_alert) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `:rotating_light: *Reincidência*\n${card.ambiguous_alert}` },
    });
  }

  if (card.summary_bullets.length > 0) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: card.summary_bullets.map((b) => `• ${b}`).join("\n") },
    });
  }

  return {
    // Fallback para notificação push e clientes sem Block Kit.
    text: `Passagem de turno ${card.station_id} — ${card.coverage_pct}% do checklist coberto`,
    blocks,
  };
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
