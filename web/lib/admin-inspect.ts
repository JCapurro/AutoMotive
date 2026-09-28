import "server-only";

import { createAdminClient } from "@/lib/supabase/admin";
import type { Database } from "@/types/database";

type Tables = Database["public"]["Tables"];
export type NotificationRow = Tables["notifications"]["Row"];
export type MatchRow = Tables["matches"]["Row"];
export type ListingRow = Tables["listings"]["Row"];
export type ProfileRow = Tables["search_profiles"]["Row"];

/**
 * Everything the inspector (sección 10, §45) needs about one alert or match:
 * the notification and its sibling rows on other channels (one decision), the
 * match that carried it, the listing, the search and its owner. Service role:
 * call only after requireAdmin().
 */
export type Inspection = {
  notification: NotificationRow | null;
  siblings: NotificationRow[];
  match: MatchRow | null;
  listing: ListingRow | null;
  sourceName: string | null;
  profile: ProfileRow | null;
  email: string | null;
  related: NotificationRow[];
};

export async function inspectNotification(id: number): Promise<Inspection | null> {
  const admin = createAdminClient();
  const { data: n } = await admin.from("notifications").select("*").eq("id", id).maybeSingle();
  if (!n) return null;

  let match: MatchRow | null = null;
  if (n.match_id) {
    ({ data: match } = await admin.from("matches").select("*").eq("id", n.match_id).maybeSingle());
  }
  if (!match && n.listing_id) {
    // price_drop / listing_gone rows carry no match: the user's best one for the listing.
    const { data: profiles } = await admin.from("search_profiles").select("id").eq("user_id", n.user_id);
    const ids = n.search_profile_id ? [n.search_profile_id] : (profiles ?? []).map((p) => p.id);
    if (ids.length) {
      ({ data: match } = await admin
        .from("matches")
        .select("*")
        .eq("listing_id", n.listing_id)
        .in("search_profile_id", ids)
        .order("score", { ascending: false })
        .limit(1)
        .maybeSingle());
    }
  }
  const { data: siblings } = await admin
    .from("notifications")
    .select("*")
    .eq("user_id", n.user_id)
    .eq("dedupe_key", n.dedupe_key)
    .neq("id", n.id)
    .order("id");
  const rest = await context(match?.listing_id ?? n.listing_id, match?.search_profile_id ?? n.search_profile_id, n.user_id);
  return { notification: n, siblings: siblings ?? [], match, ...rest, related: [] };
}

export async function inspectMatch(id: number): Promise<Inspection | null> {
  const admin = createAdminClient();
  const { data: match } = await admin.from("matches").select("*").eq("id", id).maybeSingle();
  if (!match) return null;
  const rest = await context(match.listing_id, match.search_profile_id, null);
  const { data: related } = rest.profile
    ? await admin
        .from("notifications")
        .select("*")
        .eq("user_id", rest.profile.user_id)
        .eq("listing_id", match.listing_id)
        .order("id", { ascending: false })
    : { data: [] };
  return { notification: null, siblings: [], match, ...rest, related: related ?? [] };
}

async function context(listingId: number | null, profileId: number | null, userId: string | null) {
  const admin = createAdminClient();
  const [{ data: listing }, { data: profile }] = await Promise.all([
    listingId ? admin.from("listings").select("*, sources(name)").eq("id", listingId).maybeSingle() : Promise.resolve({ data: null }),
    profileId ? admin.from("search_profiles").select("*").eq("id", profileId).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  const owner = profile?.user_id ?? userId;
  const { data: user } = owner
    ? await admin.from("profiles").select("email").eq("id", owner).maybeSingle()
    : { data: null };
  const { sources, ...row } = (listing ?? {}) as ListingRow & { sources?: { name: string } | null };
  return {
    listing: listing ? (row as ListingRow) : null,
    sourceName: sources?.name ?? null,
    profile: (profile ?? null) as ProfileRow | null,
    email: user?.email ?? null,
  };
}
