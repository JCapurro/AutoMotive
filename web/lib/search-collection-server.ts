import "server-only";

import { collectionState, type SearchSource } from "@/lib/search-collection";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Filters, SearchProfile } from "@/lib/types";

/** Only call with the profile read through the signed-in user's RLS client.
 * Private run logs stay on the server; the browser receives only a status. */
export async function loadSearchCollection(
  profile: Pick<SearchProfile, "id" | "user_id" | "filters" | "enabled">,
  userId: string,
  catalog: SearchSource[] | null,
): Promise<SearchSource[] | null> {
  if (!catalog) return null;
  const filters = profile.filters as Filters;
  const sources = catalog.filter((source) => filters.sources?.length ? filters.sources.includes(source.id) : source.enabled);
  const fallback = (state: SearchSource["collectionState"]) => sources.map((source) => ({
    ...source, collectionState: !source.enabled || !profile.enabled ? "paused" as const : state,
  }));
  if (profile.user_id !== userId) return fallback("unknown");
  if (!profile.enabled) return fallback("paused");
  const activeIds = sources.filter((source) => source.enabled).map((source) => source.id);
  if (!activeIds.length) return fallback("paused");
  if ((!filters.make && !filters.model) || !process.env.SUPABASE_SERVICE_ROLE_KEY) return fallback("unknown");
  try {
    // Membership is written by derive_targets for model and inventory targets;
    // never substitute an unrelated source-wide success for this search.
    const { data, error } = await createAdminClient().from("crawl_targets")
      .select("source,make,model,query,collector_runs(status,finished_at)")
      .contains("query", { profile_ids: [profile.id] })
      .in("source", activeIds)
      .eq("active", true)
      .order("started_at", { referencedTable: "collector_runs", ascending: false })
      .order("id", { referencedTable: "collector_runs", ascending: false })
      .limit(1, { referencedTable: "collector_runs" });
    if (error || !data) return fallback("unknown");
    const same = (a: string | null, b: string | undefined) => (a ?? "").trim().toLowerCase() === (b ?? "").trim().toLowerCase();
    return sources.map((source) => {
      const target = data.find((target) => {
        const inventory = target.make === null && target.model === null
          && typeof target.query === "object" && !Array.isArray(target.query) && target.query?.inventory === true;
        return target.source === source.id && (inventory || (same(target.make, filters.make) && same(target.model, filters.model)));
      });
      return { ...source, collectionState: source.enabled ? collectionState(target?.collector_runs[0]) : "paused" };
    });
  } catch {
    return fallback("unknown");
  }
}
