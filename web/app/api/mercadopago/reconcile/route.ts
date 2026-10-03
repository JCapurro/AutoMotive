import { sameSecret } from "@/lib/mercadopago";
import { paymentsConfigured, syncCheckout } from "@/lib/mercadopago-server";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";
export const maxDuration = 60;
export async function GET(request: Request) {
  if (!sameSecret(request.headers.get("authorization") ?? "", process.env.CRON_SECRET ? `Bearer ${process.env.CRON_SECRET}` : "")) return new Response(null, { status: 401 });
  if (!paymentsConfigured()) return new Response(null, { status: 503 });
  const { data, error } = await createAdminClient().from("billing_checkouts").select("*").neq("status", "failed")
    .order("last_synced_at", { ascending: true, nullsFirst: true }).limit(50);
  if (error) return new Response(null, { status: 503 });
  const deadline = Date.now() + 45000;
  let synced = 0, failed = 0;
  for (const checkout of data ?? []) {
    if (Date.now() > deadline) break;
    try { await syncCheckout(checkout, deadline); synced++; } catch { failed++; }
  }
  // ponytail: bounded batch/time for the pilot; increase schedule frequency as account volume grows.
  return Response.json({ synced, failed, deferred: (data?.length ?? 0) - synced - failed }, { status: failed ? 503 : 200 });
}
