import "server-only";

import { loadCatalog } from "@/lib/catalog";
import { marginAccess } from "@/lib/margin-data";
import { type PlanLimits, locationCap } from "@/lib/pro";
import type { createClient } from "@/lib/supabase/server";

/** What the search form needs: catalog, enabled sources, the user's default
 * frequency and whether their plan has the opportunity threshold (Pro) and
 * the search by body type without a model (Particular and Pro). */
export async function loadFormData(supabase: Awaited<ReturnType<typeof createClient>>) {
  const [catalog, { data: sources }, { data: profile }, { data: thresholdAlerts }, { data: modelLessSearch }, { data: snapshot }, margin] = await Promise.all([
    loadCatalog(supabase),
    supabase.from("sources").select("id, name").eq("enabled", true).order("priority"),
    supabase
      .from("profiles")
      .select("default_notification_frequency")
      .maybeSingle(),
    supabase.rpc("my_plan_feature", { p_feature: "threshold_alerts" }),
    supabase.rpc("my_plan_feature", { p_feature: "model_less_search" }),
    supabase.rpc("my_plan_snapshot"),
    marginAccess(supabase),
  ]);
  return {
    catalog,
    sources: sources ?? [],
    defaultFrequency: profile?.default_notification_frequency ?? "immediate",
    thresholdAlerts: thresholdAlerts === true,
    modelLessSearch: modelLessSearch === true,
    /** PRO-02: the threshold by margin and its minimum (Pro); null without it or without the migration. */
    marginThreshold: margin,
    /** Places one search may look in; null = no cap. */
    maxLocations: locationCap((snapshot ?? null) as PlanLimits | null),
  };
}
