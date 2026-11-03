import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { freeResultQuota, type PlanLimits, visibleResults } from "@/lib/pro";
import type { SearchSource } from "@/lib/search-collection";
import type { Filters } from "@/lib/types";
import type { Database, Json } from "@/types/database";
import {
  type NoticeProfile,
  noticeGate,
  parseZone,
  WIDER_RADII,
  withoutPlace,
  type Zone,
  type ZoneNoticeAnswer,
  zoneKind,
  zoneOf,
  zoneOptions,
  zonePlace,
} from "@/lib/zone-notice";

type Client = SupabaseClient<Database>;

/**
 * The zones «Dejar así» hid for this search (events zone_notice_dismissed,
 * RLS: own rows), or null when they couldn't be read.
 */
export async function dismissedZones(supabase: Client, profileId: number): Promise<Zone[] | null> {
  const { data, error } = await supabase.from("events").select("props")
    .eq("name", "zone_notice_dismissed").eq("props->>profile_id", String(profileId));
  if (error || !Array.isArray(data)) return null;
  return data.map((row) => parseZone((row?.props as { zone?: unknown } | null)?.zone)).filter((z): z is Zone => z != null);
}

/** search_result_counts' all_count (the «Todos» pill), or null without the row. */
export function allCount(rows: unknown): number | null {
  const value = (Array.isArray(rows) ? rows[0] : null)?.all_count;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** preview_search's count, or null when it fails. */
async function previewCount(supabase: Client, filters: Filters, zone: Zone | null): Promise<number | null> {
  const { data, error } = await supabase.rpc("preview_search", {
    p_filters: filters as Json,
    p_origin_lat: zone?.[0],
    p_origin_lon: zone?.[1],
    p_radius_km: zone?.[2],
  });
  const count = Number((data as { count?: unknown } | null)?.count);
  return error || !Number.isFinite(count) ? null : count;
}

/**
 * Whether the zone notice shows for a search, and with which options
 * (lib/zone-notice.ts). `profile`: read through the user's RLS client;
 * `count`: search_result_counts.all_count, null when the row is missing;
 * `sources`: loadSearchCollection's, for the first reads. Only when nothing
 * else rules it out, preview_search counts the zone, each wider radius and
 * the whole country in parallel, with the search's stored filters. What
 * can't be read (the sources, the dismissed zones, a count) answers
 * `pending`, never a notice.
 */
export async function zoneNotice(supabase: Client, { profile, count, access, sources, dismissed }: {
  profile: NoticeProfile & { id: number };
  count: number | null;
  access: PlanLimits | null;
  sources: SearchSource[] | null;
  dismissed: Zone[] | null;
}): Promise<ZoneNoticeAnswer> {
  const quota = freeResultQuota(access);
  // Sources unread (null, or «unknown» after a failed read of their targets) may be on a first read.
  const unread = dismissed == null || sources == null
    || sources.some((source) => source.firstRead || source.collectionState === "unknown");
  const gate = noticeGate({ profile, count, quotaReached: quota?.reached ?? false, dismissed: dismissed ?? [], reading: unread });
  const zone = zoneOf(profile);
  if (gate !== "count" || count == null || !zone) return { state: gate === "count" ? "none" : gate };
  const filters = (profile.filters ?? {}) as Filters;
  const radii = WIDER_RADII.filter((radius) => radius > zone[2]);
  const [current, country, ...wider] = await Promise.all([
    previewCount(supabase, filters, zone),
    previewCount(supabase, withoutPlace(filters), null),
    ...radii.map((radius) => previewCount(supabase, filters, [zone[0], zone[1], radius])),
  ]);
  if (current == null || country == null || wider.some((n) => n == null)) return { state: "pending" };
  // What an enforced free trial can still show: the admitted results plus the quota left, within its visible cap.
  const visibleCap = visibleResults(count, access).cap;
  const cap = quota
    ? Math.min(count + Math.max(quota.limit - quota.used, 0), visibleCap ?? Infinity)
    : visibleCap;
  const options = zoneOptions({
    count, current, country, cap,
    radii: radii.map((radius, i) => ({ radius, count: wider[i] as number })),
  });
  if (!options.length) return { state: "none" };
  return {
    state: "show",
    notice: {
      profileId: profile.id,
      count,
      place: zonePlace(filters.location_label),
      kind: zoneKind(filters.location_label),
      zone,
      options,
      cold: sources?.some((source) => source.newTarget) ?? false,
    },
  };
}
