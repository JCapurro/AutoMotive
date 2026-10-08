"use client";

import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

import { CONSENT_COOKIE } from "@/lib/meta-pixel";
import { clarityProjectId, syncClarityConsent } from "@/lib/microsoft-clarity";

function readConsent(): boolean {
  return document.cookie.split(";").some((cookie) => cookie.trim() === `${CONSENT_COOKIE}=granted`);
}

function subscribe(onChange: () => void) {
  window.addEventListener("ads-consent", onChange);
  return () => window.removeEventListener("ads-consent", onChange);
}

/** Load the supplied Clarity tag only after the visitor accepts analytics. */
export function MicrosoftClarity() {
  const consent = useSyncExternalStore(subscribe, readConsent, () => false);
  const pathname = usePathname();

  useEffect(() => {
    if (!clarityProjectId) return;
    const granted = consent && !pathname.startsWith("/auth/");
    if (window.clarity) {
      syncClarityConsent(granted);
      return;
    }
    if (!granted) return;

    // The official snippet's queue, installed once for the lifetime of the root layout.
    const clarity: NonNullable<Window["clarity"]> = (...args: unknown[]) => {
      (clarity.q ??= []).push(args);
    };
    window.clarity = clarity;
    clarity("consentv2", { ad_Storage: "granted", analytics_Storage: "granted" });

    const script = document.createElement("script");
    script.id = "microsoft-clarity";
    script.async = true;
    script.src = `https://www.clarity.ms/tag/${clarityProjectId}`;
    // Recheck the live choice if consent or the route changed during the download.
    script.addEventListener("load", () => {
      syncClarityConsent(readConsent() && !window.location.pathname.startsWith("/auth/"));
    }, { once: true });
    document.head.appendChild(script);
  }, [consent, pathname]);

  return null;
}
