import { validWebhook } from "@/lib/mercadopago";
import { handleNotification, paymentsConfigured } from "@/lib/mercadopago-server";

export const runtime = "nodejs";
export const maxDuration = 60;
function reply(status: number, outcome: string, id = "") {
  if (process.env.MERCADOPAGO_TEST_MODE === "true") {
    // Rehearsal evidence only. Never log signatures, credentials or provider bodies.
    console.info(JSON.stringify({ event: "mercadopago_test_webhook", status, outcome, id: /^[a-z0-9-]{1,64}$/i.test(id) ? id : null }));
  }
  return new Response(null, { status });
}
export async function POST(request: Request) {
  if (!paymentsConfigured()) return reply(503, "not_configured");
  const id = new URL(request.url).searchParams.get("data.id") ?? "";
  if (!validWebhook(id, request.headers.get("x-request-id") ?? "", request.headers.get("x-signature") ?? "", process.env.MERCADOPAGO_WEBHOOK_SECRET!)) return reply(401, "invalid_signature", id);
  let body: { type?: string; data?: { id?: string | number } };
  try { body = await request.json(); } catch { return reply(400, "invalid_body", id); }
  if (String(body?.data?.id).toLowerCase() !== id.toLowerCase()) return reply(400, "id_mismatch", id);
  if (!["payment", "subscription_preapproval", "subscription_authorized_payment"].includes(body.type ?? "")) return reply(200, "ignored_topic", id);
  try { await handleNotification(body.type!, id); return reply(200, "processed", id); }
  catch { return reply(503, "verification_failed", id); } // Provider retries; never acknowledge a lost update.
}
