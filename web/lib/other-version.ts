import type { SupabaseClient } from "@supabase/supabase-js";

/** The short tag a card shows when the car is another version than the one the search names (docs/TRIM_BLANDO.md). */
export const OTHER_VERSION = "Otra versión";

type CapRow = { id: number | null; capped: string | null };

/**
 * The matches the worker marked matches.score_breakdown.trim_cap (app_config.trim_soft_cap on, a non-strict
 * search that names a version, a car of another one). The same mark search_results orders them last by.
 * Never a reason to fail: without the rows (older database, error) no card carries the tag.
 */
export function otherVersionMatchIds(rows: readonly CapRow[] | null | undefined): Set<number> {
  const out = new Set<number>();
  for (const row of rows ?? []) {
    if (row.id != null && row.capped === "true") out.add(row.id);
  }
  return out;
}

export async function loadOtherVersionMatchIds(supabase: SupabaseClient, matchIds: readonly (number | null)[]): Promise<Set<number>> {
  const ids = matchIds.filter((id): id is number => id != null);
  if (!ids.length) return new Set();
  const { data } = await supabase.from("matches").select("id, capped:score_breakdown->>trim_cap").in("id", ids);
  return otherVersionMatchIds(data as CapRow[] | null);
}
