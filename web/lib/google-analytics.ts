/** Google Analytics 4 measurement ID. Empty outside explicitly configured environments. */
export const googleAnalyticsId = process.env.NEXT_PUBLIC_GA4_ID ?? "";

export const GA_CONSENT_COOKIE = "analytics_consent";

export type AnalyticsParams = Record<string, string | number | boolean | undefined>;

/** Send a GA4 event without allowing analytics failures to affect the product. */
export function analyticsEvent(name: string, params?: AnalyticsParams): void {
  if (typeof window === "undefined" || !googleAnalyticsId || !hasAnalyticsConsent()) return;
  const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
  gtag?.("event", name, params ?? {});
}

export function analyticsAllowed(): boolean {
  return Boolean(googleAnalyticsId && hasAnalyticsConsent());
}

export function hasAnalyticsConsent(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split("; ").some((cookie) => cookie === `${GA_CONSENT_COOKIE}=granted`);
}
