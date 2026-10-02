import "server-only";

import { cache } from "react";

import { type ProOffer, proOffer } from "@/lib/pro";
import { createAdminClient } from "@/lib/supabase/admin";

/**
 * app_config is server-only (sección 4.4): read with the service role. Only
 * the few values the web shows are exposed, with the seed's defaults.
 */
export type WebConfig = {
  minComparables: number;
  /** public.comparables' pool (seed: ±1 año, ±25% km, últimos 30 días). */
  comparables: { yearTol: number; kmTolPct: number; maxAgeDays: number };
  watchlistStaleDays: number;
  proOffer: ProOffer;
  commercialPilot: boolean;
};

export const webConfig = cache(async (): Promise<WebConfig> => {
  const { data } = await createAdminClient()
    .from("app_config")
    .select("key, value")
    .in("key", ["comparables", "watchlist_stale_days", "pro_offer", "commercial_pilot"]);
  const values = Object.fromEntries((data ?? []).map((row) => [row.key, row.value]));
  const comparables = (values.comparables ?? {}) as { min_n?: number; year_tol?: number; km_tol_pct?: number; max_age_days?: number };
  return {
    minComparables: Number(comparables.min_n ?? 5),
    comparables: {
      yearTol: Number(comparables.year_tol ?? 1),
      kmTolPct: Number(comparables.km_tol_pct ?? 25),
      maxAgeDays: Number(comparables.max_age_days ?? 30),
    },
    watchlistStaleDays: Number(values.watchlist_stale_days ?? 30),
    proOffer: proOffer(values.pro_offer),
    commercialPilot: (values.commercial_pilot as { enabled?: boolean } | undefined)?.enabled === true,
  };
});
