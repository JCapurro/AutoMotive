"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Script from "next/script";
import { useEffect, useRef, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { CONSENT_COOKIE, metaPixelId, pixel, PIXEL_QUEUE_COOKIE, type QueuedPixel } from "@/lib/meta-pixel";

/** "Ver publicación": the web button and the alert redirect both leave the site through these. */
const OUTBOUND = /^\/(app\/listings\/\d+\/out|r\/\d+)(\?|$)/;
const CONSENT_EVENT = "ads-consent";

type Consent = "granted" | "denied" | null;

function readConsent(): Consent {
  const value = document.cookie.split("; ").find((c) => c.startsWith(`${CONSENT_COOKIE}=`))?.split("=")[1];
  return value === "granted" || value === "denied" ? value : null;
}

function subscribe(onChange: () => void) {
  window.addEventListener(CONSENT_EVENT, onChange);
  return () => window.removeEventListener(CONSENT_EVENT, onChange);
}

function setConsent(value: Consent) {
  document.cookie = value
    ? `${CONSENT_COOKIE}=${value}; path=/; max-age=${365 * 86_400}; samesite=lax`
    : `${CONSENT_COOKIE}=; path=/; max-age=0`;
  if (value !== "granted") document.cookie = `${PIXEL_QUEUE_COOKIE}=; path=/; max-age=0`;
  // Already loaded on this page: the snippet doesn't run twice, so switch it directly.
  (window as unknown as { fbq?: (...a: unknown[]) => void }).fbq?.("consent", value === "granted" ? "grant" : "revoke");
  window.dispatchEvent(new Event(CONSENT_EVENT));
}

/** "Cambiar preferencias de cookies" in /privacidad: shows the banner again. */
export function ConsentSettings() {
  if (!metaPixelId) return null;
  return (
    <Button variant="outline" size="sm" onClick={() => setConsent(null)}>
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
 * Meta Pixel base code, loaded only after the visitor accepts the banner. The
 * snippet's PageView covers the load; client navigations fire their own, since
 * the App Router never reloads the page.
 */
export function MetaPixel() {
  const consent = useSyncExternalStore(subscribe, readConsent, () => "denied" as Consent);
  const granted = Boolean(metaPixelId) && consent === "granted";
  const pathname = usePathname();
  const first = useRef(true);

  useEffect(() => {
    if (!granted) return;
    if (first.current) first.current = false;
    else pixel("PageView");
    flushQueue();
  }, [pathname, granted]);

  useEffect(() => {
    if (!granted) return;
    // Server Actions that don't navigate (e.g. saving several searches on one page) still set the cookie.
    const timer = window.setInterval(flushQueue, 2000);
    const onClick = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a");
      if (!a) return;
      const url = new URL(a.href, window.location.href);
      if (url.origin === window.location.origin && OUTBOUND.test(url.pathname + url.search)) {
        pixel("ListingClick", { content_ids: [url.pathname.split("/")[url.pathname.startsWith("/r/") ? 2 : 3]] });
      }
    };
    document.addEventListener("click", onClick, { capture: true });
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("click", onClick, { capture: true });
    };
  }, [granted]);

  if (!metaPixelId) return null;
  if (consent === null) return <ConsentBanner />;
  if (!granted) return null;
  return (
    <Script id="meta-pixel" strategy="afterInteractive">
      {`!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('consent','grant');fbq('init','${metaPixelId}');fbq('track','PageView');`}
    </Script>
  );
}

function ConsentBanner() {
  return (
    <section
      aria-label="Cookies"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-xl rounded-xl border bg-background p-4 text-sm shadow-lg"
    >
      <p>
        Usamos cookies de Meta para saber si nuestros anuncios funcionan. No le pasamos tu email ni tus búsquedas.{" "}
        <Link href="/privacidad" className="underline underline-offset-2">
          Más info
        </Link>
      </p>
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => setConsent("denied")}>
          Rechazar
        </Button>
        <Button size="sm" onClick={() => setConsent("granted")}>
          Aceptar
        </Button>
      </div>
    </section>
  );
}
