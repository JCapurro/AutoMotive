"use client";

import Script from "next/script";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useSyncExternalStore } from "react";

import { googleAnalyticsId, hasAnalyticsConsent } from "@/lib/google-analytics";
import { CONSENT_COOKIE, untrackedPath } from "@/lib/meta-pixel";

const CONSENT_EVENT = "ads-consent";

function subscribe(onChange: () => void) {
  window.addEventListener(CONSENT_EVENT, onChange);
  return () => window.removeEventListener(CONSENT_EVENT, onChange);
}

/** Client navigations only: the landing page_view comes from gtag('config') in the snippet below. */
function RouteTracking() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const last = useRef<string | null>(null);

  useEffect(() => {
    const path = `${pathname}${searchParams.size ? `?${searchParams}` : ""}`;
    // Skip the landing, and a rerun on the same URL (StrictMode runs effects twice in dev).
    const previous = last.current;
    last.current = path;
    if (previous === null || previous === path) return;
    const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
    if (untrackedPath(pathname) || !gtag || !hasAnalyticsConsent()) return;
    gtag("event", "page_view", { page_location: `${window.location.origin}${path}`, page_path: path });
  }, [pathname, searchParams]);

  return null;
}

/** GA4 follows the cookie banner: on by default, off once the visitor rejects it. */
export function GoogleAnalytics() {
  const granted = useSyncExternalStore(subscribe, hasAnalyticsConsent, () => false);
  const pathname = usePathname();

  useEffect(() => {
    if (!googleAnalyticsId || untrackedPath(pathname)) return;
    const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
    // The live cookie, not the hydration snapshot (false on the server): a default grant isn't briefly revoked.
    const state = hasAnalyticsConsent() ? "granted" : "denied";
    gtag?.("consent", "update", { analytics_storage: state, ad_storage: state, ad_user_data: state, ad_personalization: state });
  }, [granted, pathname]);

  if (!googleAnalyticsId || untrackedPath(pathname)) return null;
  // The landing page_view rides on config, after the consent default; a visitor who rejected sends none.
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${googleAnalyticsId}`} strategy="afterInteractive" />
      <Script id="google-analytics" strategy="afterInteractive">
        {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}window.gtag=gtag;
{const c=/(^|; )${CONSENT_COOKIE}=denied/.test(document.cookie)?'denied':'granted';
gtag('consent','default',{analytics_storage:c,ad_storage:c,ad_user_data:c,ad_personalization:c});
gtag('js',new Date());gtag('config','${googleAnalyticsId}',{send_page_view:c==='granted'});}`}
      </Script>
      <Suspense fallback={null}><RouteTracking /></Suspense>
    </>
  );
}
