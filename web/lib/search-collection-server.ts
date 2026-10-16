import "server-only";

import {
  bodyTypeTargetsOf,
  type CollectionState,
  collectionState,
  DEFAULT_BODY_TYPE_SOURCES,
  type SearchSource,
} from "@/lib/search-collection";
import { isModelLess } from "@/lib/search-form";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Filters, SearchProfile } from "@/lib/types";

// One source, several targets (a model-less search with several body types): the state shown.
const BUSIEST: CollectionState[] = ["loading", "waiting", "failed", "unknown", "done"];

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
  const modelLess = isModelLess(filters);
  const bodyTypes = filters.body_types ?? [];
  if ((modelLess && !bodyTypes.length) || !process.env.SUPABASE_SERVICE_ROLE_KEY) return fallback("unknown");
  try {
    const admin = createAdminClient();
    // The sources with a target per body type (app_config.body_type_targets).
    let configured = DEFAULT_BODY_TYPE_SOURCES;
    if (modelLess) {
      const { data: config } = await admin.from("app_config").select("value").eq("key", "body_type_targets").maybeSingle();
      const value = config?.value;
      if (value && typeof value === "object" && !Array.isArray(value) && Array.isArray(value.sources)) {
        configured = value.sources.filter((s): s is string => typeof s === "string");
      }
    }
    // Membership is written by derive_targets for model, inventory and body
    // type targets; never substitute an unrelated source-wide success for this search.
    const { data, error } = await admin.from("crawl_targets")
      .select("source,make,model,body_type,query,collector_runs(status,finished_at)")
      .contains("query", { profile_ids: [profile.id] })
      .in("source", activeIds)
      .eq("active", true)
      .order("started_at", { referencedTable: "collector_runs", ascending: false })
      .order("id", { referencedTable: "collector_runs", ascending: false })
      .limit(1, { referencedTable: "collector_runs" });
    if (error || !data) return fallback("unknown");
    const same = (a: string | null, b: string | undefined) => (a ?? "").trim().toLowerCase() === (b ?? "").trim().toLowerCase();
    return sources.map((source) => {
      const targets = data.filter((target) => {
        const vehicleless = target.make === null && target.model === null;
        const inventory = vehicleless && target.body_type == null
          && typeof target.query === "object" && !Array.isArray(target.query) && target.query?.inventory === true;
        const byBody = vehicleless && target.body_type != null && modelLess && bodyTypes.includes(target.body_type);
        const byModel = target.body_type == null && !modelLess
          && same(target.make, filters.make) && same(target.model, filters.model);
        return target.source === source.id && (inventory || byBody || byModel);
      });
      if (!source.enabled) return { ...source, collectionState: "paused" as const };
      let states: CollectionState[];
      if (modelLess) {
        // A source that searches these body types waits for a target per body
        // type until derive_targets links this search to it, like a model's
        // target. The other sources feed them from their own targets: idle,
        // never waiting. Several body types: the busiest state.
        const inventory = targets.filter((target) => target.body_type == null);
        const expected = bodyTypeTargetsOf(source.id, bodyTypes, configured);
        states = [
          ...inventory.map((target) => collectionState(target.collector_runs[0])),
          ...expected.map((code) => collectionState(targets.find((target) => target.body_type === code)?.collector_runs[0])),
        ];
        if (!states.length) return { ...source, collectionState: "done" as const };
      } else {
        states = targets.length ? targets.map((target) => collectionState(target.collector_runs[0])) : [collectionState(undefined)];
      }
      return { ...source, collectionState: BUSIEST.find((state) => states.includes(state)) ?? states[0] };
    });
  } catch {
    return fallback("unknown");
  }
}
