import "server-only";

import { loadCatalog } from "@/lib/catalog";
import type { createClient } from "@/lib/supabase/server";

/** What the search form needs: catalog, enabled sources and the user's defaults. */
export async function loadFormData(supabase: Awaited<ReturnType<typeof createClient>>) {
  const [catalog, { data: sources }, { data: profile }] = await Promise.all([
    loadCatalog(supabase),
    supabase.from("sources").select("id, name").eq("enabled", true).order("priority"),
    supabase
      .from("profiles")
      .select("default_notification_frequency, default_origin_lat, default_origin_lon, default_origin_label")
      .maybeSingle(),
  ]);
  const defaultOrigin =
    profile?.default_origin_lat != null && profile.default_origin_lon != null
      ? {
          label: profile.default_origin_label ?? "Mi ubicación",
          lat: profile.default_origin_lat,
          lon: profile.default_origin_lon,
        }
      : null;
  return {
    catalog,
    sources: sources ?? [],
    defaultOrigin,
    defaultFrequency: profile?.default_notification_frequency ?? "immediate",
  };
}
