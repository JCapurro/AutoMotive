import { trackingAllowed } from "@/lib/meta-pixel";

/** Google Analytics 4 measurement ID. Empty outside explicitly configured environments. */
export const googleAnalyticsId = process.env.NEXT_PUBLIC_GA4_ID ?? "";

export type AnalyticsValue =
  | string
  | number
  | boolean
  | undefined
  | AnalyticsValue[]
  | { [key: string]: AnalyticsValue };

export type AnalyticsParams = Record<string, AnalyticsValue>;

/** Send a GA4 event without allowing analytics failures to affect the product. */
export function analyticsEvent(name: string, params?: AnalyticsParams): void {
  if (typeof window === "undefined" || !googleAnalyticsId || !hasAnalyticsConsent()) return;
  const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
  gtag?.("event", name, params ?? {});
}

export function analyticsAllowed(): boolean {
  return Boolean(googleAnalyticsId && hasAnalyticsConsent());
}

/** Same banner as the pixel: on unless the visitor rejected it. */
export function hasAnalyticsConsent(): boolean {
  if (typeof document === "undefined") return false;
  return trackingAllowed(document.cookie);
}
