/**
 * Meta Pixel (ads attribution). Empty id = no pixel: local and e2e runs stay
 * out of the ads data. Shared by the browser component and the server queue.
 */
export const metaPixelId = process.env.NEXT_PUBLIC_META_PIXEL_ID ?? "";

/** Cookie the server fills with events the browser fires on its next tick (see queuePixel). */
export const PIXEL_QUEUE_COOKIE = "px_q";

/**
 * The visitor's answer to the cookie banner: "granted" or "denied". A cookie,
 * not localStorage, so the server can respect it (Conversions API, see
 * lib/meta-capi.ts). Meta, GA4 and Clarity all read it.
 */
export const CONSENT_COOKIE = "ads_consent";

/**
 * Consent is granted by default: no answer yet counts as "granted", and only
 * "Rechazar" (ads_consent=denied) turns Meta, GA4 and Clarity off. Takes
 * document.cookie (the server side, lib/meta-capi.ts, checks the same value).
 */
export function trackingAllowed(cookie: string): boolean {
  return !cookie.split(";").some((c) => c.trim() === `${CONSENT_COOKIE}=denied`);
}

/** Standard events Meta optimizes on, plus our own (trackCustom). */
export type PixelEvent =
  | "PageView"
  | "Lead"
  | "CompleteRegistration"
  | "StartTrial"
  | "ViewContent"
  | "AddToWishlist"
  | "InitiateCheckout"
  | "Purchase"
  | "SearchCreated"
  | "ListingClick";

const STANDARD = new Set<PixelEvent>([
  "PageView",
  "Lead",
  "CompleteRegistration",
  "StartTrial",
  "ViewContent",
  "AddToWishlist",
  "InitiateCheckout",
  "Purchase",
]);

export type PixelParams = Record<string, string | number | string[] | undefined>;
export type QueuedPixel = { event: PixelEvent; params?: PixelParams; id?: string };

type Fbq = (...args: unknown[]) => void;

/**
 * Fires one event from the browser. `id` is the eventID Meta dedupes on, kept
 * stable (e.g. `purchase:<checkout id>`) so a later Conversions API copy of the
 * same event isn't counted twice.
 */
export function pixel(event: PixelEvent, params?: PixelParams, id?: string, tries = 10): void {
  if (typeof window === "undefined" || !metaPixelId) return;
  const fbq = (window as unknown as { fbq?: Fbq }).fbq;
  // Effects can run before the afterInteractive snippet defines fbq.
  if (!fbq) {
    if (tries > 0) window.setTimeout(() => pixel(event, params, id, tries - 1), 500);
    return;
  }
  fbq(STANDARD.has(event) ? "track" : "trackCustom", event, params ?? {}, id ? { eventID: id } : undefined);
}
