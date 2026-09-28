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
    const timer = setInterval(() => router.refresh(), every);
    return () => clearInterval(timer);
  }, [router, every]);
  return null;
}
