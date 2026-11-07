import "server-only";

import { cookies, headers } from "next/headers";
import { after } from "next/server";

import { CONSENT_COOKIE } from "@/lib/meta-pixel";
import { TWCLID_COOKIE, X_EVENTS, type XConversion, xPixelId } from "@/lib/x-pixel";

/**
 * X Conversion API: conversions confirmed on the server (signup, first search,
 * approved payment) reported straight to X. The browser pixel only loads the
 * base code, so nothing here needs deduplicating against it; `conversion_id`
 * (e.g. `purchase:<checkout>:<payment>`) makes X count a repeated send once.
 *
 * X_PIXEL_TOKEN empty = off. Identifiers are the ad click (twclid) and the IP
 * and browser, the same Meta receives: never the email or the phone.
 */
const ENDPOINT = "https://ads-api.x.com/12/measurement/conversions";

export type XAttribution = { consent: boolean; twclid?: string; ip?: string; ua?: string; url?: string };

export function xCapiEnabled(): boolean {
  return Boolean(xPixelId && process.env.X_PIXEL_TOKEN);
}

/** From a Server Action or Route Handler. Granted unless the visitor rejected the banner. */
export async function readXAttribution(): Promise<XAttribution> {
  const [store, h] = await Promise.all([cookies(), headers()]);
  if (store.get(CONSENT_COOKIE)?.value === "denied") return { consent: false };
  const ip = (h.get("x-forwarded-for") ?? "").split(",")[0].trim() || h.get("x-real-ip") || undefined;
  return {
    consent: true,
    twclid: store.get(TWCLID_COOKIE)?.value,
    ip,
    ua: h.get("user-agent")?.slice(0, 512) ?? undefined,
    url: h.get("referer") ?? undefined,
  };
}

type Send = { conversion: XConversion; conversionId: string; at: string | Date; attribution: XAttribution | null | undefined };

/** Sends one conversion. Never throws: ads attribution must not fail a signup or a payment. */
export async function sendXConversion({ conversion, conversionId, at, attribution }: Send): Promise<void> {
  const eventId = X_EVENTS[conversion];
  if (!eventId || !xCapiEnabled() || !attribution?.consent) return;
  const identifier = {
    ...(attribution.twclid ? { twclid: attribution.twclid } : {}),
    // X only takes the IP together with the user agent.
    ...(attribution.ip && attribution.ua ? { ip_address: attribution.ip, user_agent: attribution.ua } : {}),
  };
  if (!Object.keys(identifier).length) return;
  const time = new Date(at);
  // A late reconciliation shouldn't report week-old payments.
  if (Date.now() - time.getTime() > 7 * 86_400_000) return;
  try {
    const response = await fetch(`${ENDPOINT}/${xPixelId}`, {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
      headers: { "Content-Type": "application/json", "X-Pixel-Token": process.env.X_PIXEL_TOKEN ?? "" },
      body: JSON.stringify({
        conversions: [
          {
            conversion_time: time.toISOString(),
            event_id: eventId,
            conversion_id: conversionId,
            ...(attribution.url ? { event_source_url: attribution.url } : {}),
            identifiers: [identifier],
          },
        ],
      }),
    });
    if (!response.ok) throw new Error(`x_capi_http_${response.status}`);
  } catch (error) {
    // Never log the token or the body.
    console.error(`x ${conversion} not sent:`, error instanceof Error ? error.message : "unknown");
  }
}

/**
 * For a conversion confirmed in a Server Action or Route Handler: reads the
 * visitor's attribution now and sends after the response, so X never slows
 * the page. Off (no request APIs touched) while X or the event isn't set up.
 */
export async function reportXConversion(conversion: XConversion, conversionId: string): Promise<void> {
  if (!X_EVENTS[conversion] || !xCapiEnabled()) return;
  try {
    const attribution = await readXAttribution();
    const at = new Date();
    after(() => sendXConversion({ conversion, conversionId, at, attribution }));
  } catch {
    // Ads attribution never breaks the action.
  }
}
