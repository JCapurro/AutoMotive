import "server-only";

import { cache } from "react";

import { createAdminClient } from "@/lib/supabase/admin";

/**
 * app_config is server-only (sección 4.4): read with the service role. Only
 * the few values the web shows are exposed, with the seed's defaults.
 */
export type WebConfig = { minComparables: number; watchlistStaleDays: number };

export const webConfig = cache(async (): Promise<WebConfig> => {
  const { data } = await createAdminClient()
    .from("app_config")
    .select("key, value")
    .in("key", ["comparables", "watchlist_stale_days"]);
  const values = Object.fromEntries((data ?? []).map((row) => [row.key, row.value]));
  const comparables = (values.comparables ?? {}) as { min_n?: number };
  return {
    minComparables: Number(comparables.min_n ?? 5),
    watchlistStaleDays: Number(values.watchlist_stale_days ?? 30),
  };
});
