import "server-only";

import { createHash } from "node:crypto";

import { cookies, headers } from "next/headers";

import { CONSENT_COOKIE, metaPixelId } from "@/lib/meta-pixel";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Json } from "@/types/database";

/**
 * Meta Conversions API: the server copy of Purchase. The payment is confirmed
 * by the Mercado Pago webhook, often with nobody on the page, so the browser
 * pixel alone misses it. Same event_id as the browser (`purchase:<checkout>`)
 * for the first payment: Meta counts it once.
 *
 * META_CAPI_TOKEN empty = off. META_CAPI_TEST_CODE sends to Events Manager's
 * "Test events" tab instead of the real data.
 */
const GRAPH = "https://graph.facebook.com/v23.0";

export type AdAttribution = { consent: boolean; fbp?: string; fbc?: string; ip?: string; ua?: string; url?: string };

export function capiEnabled(): boolean {
  return Boolean(metaPixelId && process.env.META_CAPI_TOKEN);
}

/** At checkout start (a Server Action): what Meta needs to match the later Purchase to the ad click. */
export async function readAttribution(): Promise<AdAttribution> {
  const [store, h] = await Promise.all([cookies(), headers()]);
  if (store.get(CONSENT_COOKIE)?.value !== "granted") return { consent: false };
  const ip = (h.get("x-forwarded-for") ?? "").split(",")[0].trim() || h.get("x-real-ip") || undefined;
  return {
    consent: true,
    fbp: store.get("_fbp")?.value,
    fbc: store.get("_fbc")?.value,
    ip,
    ua: h.get("user-agent")?.slice(0, 512) ?? undefined,
    url: h.get("referer") ?? undefined,
  };
}

function sha256(value: string): string {
  return createHash("sha256").update(value.trim().toLowerCase()).digest("hex");
}

type Purchase = {
  paymentId: number;
  checkout: { id: string; user_id: string; offer: string; amount: number; currency: string; ad_attribution: Json | null };
  paidAt: string;
};

/**
 * Sends one approved payment, at most once (commercial_payments.meta_sent_at
 * is claimed first). Never throws: ads attribution must not fail a payment.
 */
export async function sendPurchase({ paymentId, checkout, paidAt }: Purchase): Promise<void> {
  if (!capiEnabled()) return;
  const attribution = checkout.ad_attribution as AdAttribution | null;
  if (!attribution?.consent) return;
  // Meta rejects events older than 7 days; a late reconciliation shouldn't retry them forever.
  if (Date.now() - new Date(paidAt).getTime() > 6 * 86_400_000) return;
  const db = createAdminClient();
  try {
    const { data: claimed } = await db
      .from("commercial_payments")
      .update({ meta_sent_at: new Date().toISOString() })
      .eq("id", paymentId)
      .is("meta_sent_at", null)
      .select("id")
      .maybeSingle();
    if (!claimed) return;
    // Keep historical event IDs stable; each renewal has its own verified payment.
    const { count } = await db
      .from("commercial_payments")
      .select("id", { count: "exact", head: true })
      .eq("checkout_id", checkout.id)
      .lt("id", paymentId);
    const eventId = count ? `purchase:${checkout.id}:${paymentId}` : `purchase:${checkout.id}`;
    const body = {
      data: [
        {
          event_name: "Purchase",
          event_time: Math.floor(new Date(paidAt).getTime() / 1000),
          event_id: eventId,
          action_source: "website",
          event_source_url: attribution.url ?? `${process.env.SITE_URL}/app/pro`,
          user_data: {
            external_id: [sha256(checkout.user_id)],
            ...(attribution.fbp ? { fbp: attribution.fbp } : {}),
            ...(attribution.fbc ? { fbc: attribution.fbc } : {}),
            ...(attribution.ip ? { client_ip_address: attribution.ip } : {}),
            ...(attribution.ua ? { client_user_agent: attribution.ua } : {}),
          },
          custom_data: { value: checkout.amount, currency: checkout.currency, content_ids: [checkout.offer], content_type: "product" },
        },
      ],
      ...(process.env.META_CAPI_TEST_CODE ? { test_event_code: process.env.META_CAPI_TEST_CODE } : {}),
    };
    const response = await fetch(`${GRAPH}/${metaPixelId}/events`, {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.META_CAPI_TOKEN}` },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`meta_capi_http_${response.status}`);
  } catch (error) {
    // Release the claim: the next webhook or reconciliation retries. Never log the token or the body.
    await db.from("commercial_payments").update({ meta_sent_at: null }).eq("id", paymentId);
    console.error("meta purchase not sent:", error instanceof Error ? error.message : "unknown");
  }
}
