"use client";

import { usePathname } from "next/navigation";
import Script from "next/script";
import { useEffect, useSyncExternalStore } from "react";

import { trackingAllowed, untrackedPath } from "@/lib/meta-pixel";
import { TWCLID_COOKIE, xPixelId } from "@/lib/x-pixel";

function readConsent(): boolean {
  return trackingAllowed(document.cookie);
}

function subscribe(onChange: () => void) {
  window.addEventListener("ads-consent", onChange);
  return () => window.removeEventListener("ads-consent", onChange);
}

/**
 * X conversion tracking base code, once per page load, behind the same cookie
 * banner as Meta: on by default, never loaded once the visitor rejects it, and
 * never on the pages whose URL carries a secret. Conversions themselves go from
 * the server (lib/x-capi.ts), which also needs the ad click's twclid, kept here.
 */
export function XPixel() {
  const consent = useSyncExternalStore(subscribe, readConsent, () => false);
  const pathname = usePathname();
  const granted = Boolean(xPixelId) && consent && !untrackedPath(pathname);

  useEffect(() => {
    if (!granted) return;
    const twclid = new URLSearchParams(window.location.search).get("twclid");
    if (twclid && /^[\w-]{1,200}$/.test(twclid)) {
      document.cookie = `${TWCLID_COOKIE}=${twclid}; path=/; max-age=${30 * 86_400}; samesite=lax`;
    }
  }, [granted, pathname]);

  if (!granted) return null;
  return (
    <Script id="x-pixel" strategy="afterInteractive">
      {`!function(e,t,n,s,u,a){e.twq||(s=e.twq=function(){s.exe?s.exe.apply(s,arguments):s.queue.push(arguments);
},s.version='1.1',s.queue=[],u=t.createElement(n),u.async=!0,u.src='https://static.ads-twitter.com/uwt.js',
a=t.getElementsByTagName(n)[0],a.parentNode.insertBefore(u,a))}(window,document,'script');
twq('config','${xPixelId}');`}
    </Script>
  );
}
