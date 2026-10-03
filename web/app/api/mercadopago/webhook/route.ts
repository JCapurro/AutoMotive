import { validWebhook } from "@/lib/mercadopago";
import { handleNotification, paymentsConfigured } from "@/lib/mercadopago-server";

export const runtime = "nodejs";
export const maxDuration = 60;
export async function POST(request: Request) {
  if (!paymentsConfigured()) return new Response(null, { status: 503 });
  const id = new URL(request.url).searchParams.get("data.id") ?? "";
  if (!validWebhook(id, request.headers.get("x-request-id") ?? "", request.headers.get("x-signature") ?? "", process.env.MERCADOPAGO_WEBHOOK_SECRET!)) return new Response(null, { status: 401 });
  let body: { type?: string; data?: { id?: string | number } };
  try { body = await request.json(); } catch { return new Response(null, { status: 400 }); }
  if (String(body?.data?.id).toLowerCase() !== id.toLowerCase()) return new Response(null, { status: 400 });
  if (!["payment", "subscription_preapproval", "subscription_authorized_payment"].includes(body.type ?? "")) return new Response(null, { status: 200 });
  try { await handleNotification(body.type!, id); return new Response(null, { status: 200 }); }
  catch { return new Response(null, { status: 503 }); } // Provider retries; never acknowledge a lost update.
}
