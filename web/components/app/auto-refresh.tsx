"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Re-renders the page every few seconds while something the worker does is
 * pending (a search's backfill, sección 5.7). The worker talks to the web only
 * through tables (sección 2), so polling the server render is the simple way.
 */
export function AutoRefresh({ every = 3000 }: { every?: number }) {
  const router = useRouter();
  useEffect(() => {
    // Each refresh re-renders the whole page: on a phone's data plan, a hidden
    // tab doesn't poll, and the interval grows (up to 30 s) while nothing changes.
    let delay = every;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = () => {
      timer = setTimeout(() => {
        if (document.visibilityState === "visible") router.refresh();
        delay = Math.min(delay * 1.5, 30_000);
        tick();
      }, delay);
    };
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      clearTimeout(timer);
      delay = every;
      router.refresh();
      tick();
    };
    tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [router, every]);
  return null;
}
