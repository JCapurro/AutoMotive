import "server-only";

import { loadCatalog } from "@/lib/catalog";
import { type PlanLimits, locationCap } from "@/lib/pro";
import type { createClient } from "@/lib/supabase/server";

/** What the search form needs: catalog, enabled sources, the user's default
 * frequency and whether their plan has the opportunity threshold (Pro) and
 * the search by body type without a model (Particular and Pro) and the
 * strict seller filter (Pro). */
export async function loadFormData(supabase: Awaited<ReturnType<typeof createClient>>) {
  const [catalog, { data: sources }, { data: profile }, { data: thresholdAlerts }, { data: modelLessSearch }, { data: snapshot }, { data: sellerFilter }] = await Promise.all([
    loadCatalog(supabase),
    supabase.from("sources").select("id, name").eq("enabled", true).order("priority"),
    supabase
      .from("profiles")
      .select("default_notification_frequency")
      .maybeSingle(),
    supabase.rpc("my_plan_feature", { p_feature: "threshold_alerts" }),
    supabase.rpc("my_plan_feature", { p_feature: "model_less_search" }),
    supabase.rpc("my_plan_snapshot"),
    supabase.rpc("my_plan_feature", { p_feature: "seller_filter" }),
  ]);
  return {
    catalog,
    sources: sources ?? [],
    defaultFrequency: profile?.default_notification_frequency ?? "immediate",
    thresholdAlerts: thresholdAlerts === true,
    modelLessSearch: modelLessSearch === true,
    /** The strict seller filter (Pro, PRO-01). */
    sellerFilter: sellerFilter === true,
    /** Places one search may look in; null = no cap. */
    maxLocations: locationCap((snapshot ?? null) as PlanLimits | null),
  };
}
