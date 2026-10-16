"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Script from "next/script";
import { useEffect, useRef, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { googleAnalyticsId } from "@/lib/google-analytics";
import { clarityProjectId } from "@/lib/microsoft-clarity";
import { CONSENT_COOKIE, metaPixelId, pixel, PIXEL_QUEUE_COOKIE, trackingAllowed, untrackedPath, type QueuedPixel } from "@/lib/meta-pixel";

/** "Ver publicación": the web button and the alert redirect both leave the site through these. */
const OUTBOUND = /^\/(app\/listings\/\d+\/out|r\/\d+)(\?|$)/;
const CONSENT_EVENT = "ads-consent";

type Choice = "granted" | "denied";

/** "Cambiar preferencias de cookies" was clicked: the banner is back, the current choice stays until a new one. */
let reopened = false;

function readAllowed(): boolean {
  return trackingAllowed(document.cookie);
}

/** Until the visitor picks, the banner stays up (and tracking runs, see trackingAllowed). */
function readBanner(): boolean {
  return reopened || !document.cookie.split("; ").some((c) => c.startsWith(`${CONSENT_COOKIE}=`));
}

function subscribe(onChange: () => void) {
  window.addEventListener(CONSENT_EVENT, onChange);
  return () => window.removeEventListener(CONSENT_EVENT, onChange);
}

function setConsent(value: Choice) {
  reopened = false;
  document.cookie = `${CONSENT_COOKIE}=${value}; path=/; max-age=${365 * 86_400}; samesite=lax`;
  if (value === "denied") document.cookie = `${PIXEL_QUEUE_COOKIE}=; path=/; max-age=0`;
  // Already loaded on this page: the snippet doesn't run twice, so switch it directly.
  (window as unknown as { fbq?: (...a: unknown[]) => void }).fbq?.("consent", value === "granted" ? "grant" : "revoke");
  window.dispatchEvent(new Event(CONSENT_EVENT));
}

/** "Cambiar preferencias de cookies" in /privacidad: shows the banner again. */
export function ConsentSettings() {
  if (!metaPixelId && !googleAnalyticsId && !clarityProjectId) return null;
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        reopened = true;
        window.dispatchEvent(new Event(CONSENT_EVENT));
      }}
    >
      Cambiar preferencias de cookies
    </Button>
  );
}

/** Fires (and clears) the events queued by the server in the px_q cookie. */
function flushQueue() {
  const raw = document.cookie.split("; ").find((c) => c.startsWith(`${PIXEL_QUEUE_COOKIE}=`));
  // Before the snippet runs there's no fbq to queue on: keep the cookie for the next tick.
  if (!raw || !("fbq" in window)) return;
  document.cookie = `${PIXEL_QUEUE_COOKIE}=; path=/; max-age=0`;
  try {
    const queue: QueuedPixel[] = JSON.parse(decodeURIComponent(raw.slice(PIXEL_QUEUE_COOKIE.length + 1)));
    queue.forEach((q) => pixel(q.event, q.params, q.id));
  } catch {}
}

/**
 * Meta Pixel base code, on every page. Consent is granted by default; once the
 * visitor rejects the banner it runs with consent revoked (fbq('consent',
 * 'revoke')): installed, but sending nothing. The snippet's PageView covers the
 * load; client navigations fire their own, since the App Router never reloads the page.
 */
export function MetaPixel() {
  const granted = useSyncExternalStore(subscribe, readAllowed, () => false);
  const banner = useSyncExternalStore(subscribe, readBanner, () => false);
  const pathname = usePathname();
  const first = useRef(true);

  useEffect(() => {
    if (!metaPixelId || untrackedPath(pathname)) return;
    if (first.current) first.current = false;
    else pixel("PageView");
  }, [pathname]);

  useEffect(() => {
    if (!metaPixelId || untrackedPath(pathname)) return;
    const onClick = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a");
      if (!a) return;
      const url = new URL(a.href, window.location.href);
      if (url.origin === window.location.origin && OUTBOUND.test(url.pathname + url.search)) {
        pixel("ListingClick", { content_ids: [url.pathname.split("/")[url.pathname.startsWith("/r/") ? 2 : 3]] });
      }
    };
    document.addEventListener("click", onClick, { capture: true });
    return () => document.removeEventListener("click", onClick, { capture: true });
  }, [pathname]);

  useEffect(() => {
    // The server's queue waits for consent (the cookie lives 10 minutes).
    if (!metaPixelId || !granted || untrackedPath(pathname)) return;
    flushQueue();
    // Server Actions that don't navigate (e.g. saving several searches on one page) still set the cookie.
    const timer = window.setInterval(flushQueue, 2000);
    return () => window.clearInterval(timer);
  }, [granted, pathname]);

  if (untrackedPath(pathname) || (!metaPixelId && !googleAnalyticsId && !clarityProjectId)) return null;
  return (
    <>
      {metaPixelId ? <Script id="meta-pixel" strategy="afterInteractive">
        {`!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('consent',/(^|; )${CONSENT_COOKIE}=denied/.test(document.cookie)?'revoke':'grant');
fbq('init','${metaPixelId}');fbq('track','PageView');`}
      </Script> : null}
      {banner ? <ConsentBanner /> : null}
    </>
  );
}

function ConsentBanner() {
  return (
    <section
      aria-labelledby="cookie-banner-title"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-xl rounded-xl border bg-background p-4 text-sm shadow-lg"
    >
      <h2 id="cookie-banner-title" className="font-semibold">
        Uso de cookies
      </h2>
      <p className="mt-1 text-muted-foreground">
        Utilizamos cookies propias y de terceros para el funcionamiento del sitio, analizar su uso y medir la
        efectividad de nuestras campañas publicitarias. Podés aceptar todas las cookies o rechazar las que no son
        necesarias. Para más información, consultá nuestra{" "}
        <Link href="/privacidad#cookies" className="text-foreground underline underline-offset-2">
          Política de privacidad
        </Link>
        .
      </p>
      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => setConsent("denied")}>
          Rechazar
        </Button>
        <Button size="sm" onClick={() => setConsent("granted")}>
          Aceptar todas
        </Button>
      </div>
    </section>
  );
}
