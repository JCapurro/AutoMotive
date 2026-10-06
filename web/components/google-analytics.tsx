"use client";

import Script from "next/script";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useSyncExternalStore } from "react";

import { GA_CONSENT_COOKIE, googleAnalyticsId, hasAnalyticsConsent } from "@/lib/google-analytics";
import { CONSENT_COOKIE } from "@/lib/meta-pixel";

const CONSENT_EVENT = "ads-consent";
type Consent = "granted" | "denied" | null;

function readConsent(): Consent {
  const value = document.cookie.split("; ").find((cookie) => cookie.startsWith(`${CONSENT_COOKIE}=`))?.split("=")[1];
  return value === "granted" || value === "denied" ? value : null;
}

function subscribe(onChange: () => void) {
  window.addEventListener(CONSENT_EVENT, onChange);
  return () => window.removeEventListener(CONSENT_EVENT, onChange);
}

function RouteTracking() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
    if (pathname.startsWith("/auth/") || !gtag || !hasAnalyticsConsent()) return;
    const pageLocation = `${window.location.origin}${pathname}${searchParams.size ? `?${searchParams}` : ""}`;
    gtag("event", "page_view", { page_location: pageLocation, page_path: `${pathname}${searchParams.size ? `?${searchParams}` : ""}` });
  }, [pathname, searchParams]);

  return null;
}

/** GA4 uses the same explicit cookie choice as the existing analytics consent banner. */
export function GoogleAnalytics() {
  const consent = useSyncExternalStore(subscribe, readConsent, () => "denied" as Consent);
  const pathname = usePathname();

  useEffect(() => {
    if (!googleAnalyticsId || pathname.startsWith("/auth/")) return;
    const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
    const granted = consent === "granted";
    if (gtag) gtag("consent", "update", {
      analytics_storage: granted ? "granted" : "denied",
      ad_storage: granted ? "granted" : "denied",
      ad_user_data: granted ? "granted" : "denied",
      ad_personalization: granted ? "granted" : "denied",
    });
    document.cookie = granted
      ? `${GA_CONSENT_COOKIE}=granted; path=/; max-age=${365 * 86_400}; samesite=lax`
      : `${GA_CONSENT_COOKIE}=; path=/; max-age=0; samesite=lax`;
  }, [consent, pathname]);

  if (!googleAnalyticsId || pathname.startsWith("/auth/")) return null;
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${googleAnalyticsId}`} strategy="afterInteractive" />
      <Script id="google-analytics" strategy="afterInteractive">
        {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}window.gtag=gtag;
gtag('consent','default',{analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});
gtag('js',new Date());gtag('config','${googleAnalyticsId}',{send_page_view:false});`}
      </Script>
      <Suspense fallback={null}><RouteTracking /></Suspense>
    </>
  );
}
