/** Public Clarity project ID. Empty keeps development and preview traffic out. */
export const clarityProjectId = process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID ?? "";

type Clarity = ((...args: unknown[]) => void) & { q?: unknown[][] };

declare global {
  interface Window {
    clarity?: Clarity;
  }
}

/** Denied consent alone allows cookieless recording, so also stop collection. */
export function syncClarityConsent(granted: boolean): void {
  if (!window.clarity) return;
  if (granted) window.clarity("start", { projectId: clarityProjectId });
  window.clarity("consentv2", {
    ad_Storage: granted ? "granted" : "denied",
    analytics_Storage: granted ? "granted" : "denied",
  });
  if (!granted) window.clarity("stop");
}
