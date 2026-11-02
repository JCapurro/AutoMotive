import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { asMarginRef, asStoredMargin, marginCardLine, type StoredMargin } from "@/lib/margin-view";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Database } from "@/types/database";

/**
 * PRO-02: what the web reads of the estimated dealer margin, only with the
 * plan's dealer_margin flag (Pro). Both RPCs come with migration
 * 20261130120000_pro02_margin: against a database without it they fail and
 * the web shows nothing of PRO-02 (no line, no order, no threshold control,
 * no opportunity_threshold_usd in the inserts).
 */

type Supabase = SupabaseClient<Database>;

export type MarginAccess = { minThresholdUsd: number };

/** Parses my_margin_access()'s {enabled, min_threshold_usd}: access only when both are there. */
export function parseMarginAccess(data: unknown): MarginAccess | null {
  if (!data || typeof data !== "object") return null;
  const v = data as { enabled?: unknown; min_threshold_usd?: unknown };
  const min = v.min_threshold_usd;
  return v.enabled === true && typeof min === "number" && Number.isInteger(min) && min > 0 ? { minThresholdUsd: min } : null;
}

/** The signed-in user's access to the margin, or null (no feature, or a database without the migration). */
export async function marginAccess(supabase: Supabase): Promise<MarginAccess | null> {
  try {
    const { data, error } = await supabase.rpc("my_margin_access");
    return error ? null : parseMarginAccess(data);
  } catch {
    return null;
  }
}

type Rpc = (
  fn: "my_match_margins",
  args: { p_match_ids: number[] },
) => PromiseLike<{ data: { match_id: number; margin_ref: unknown }[] | null; error: unknown }>;

/**
 * my_match_margins for these match ids, by match id: a margin, or «not enough
 * dealers» (Juan, 02/11: say why there is none). Any error leaves the map empty.
 */
export async function fetchMatchMargins(rpc: Rpc, ids: (number | null | undefined)[]): Promise<Map<number, StoredMargin>> {
  const unique = [...new Set(ids.filter((id): id is number => id != null))];
  const out = new Map<number, StoredMargin>();
  if (!unique.length) return out;
  try {
    const { data, error } = await rpc("my_match_margins", { p_match_ids: unique });
    if (error || !data) return out;
    for (const row of data) {
      const ref = asStoredMargin(row.margin_ref);
      if (ref) out.set(Number(row.match_id), ref);
    }
  } catch {
    // A database without the migration: no line.
  }
  return out;
}

export type MarginCard = { listing_id: number | null; match_id?: number | null };

/** The cards of a page: listing_id -> the short margin line of its match (marginCardLine). Nothing without access. */
export async function marginLinesFor(supabase: Supabase, access: MarginAccess | null, cards: MarginCard[]): Promise<Map<number, string>> {
  const lines = new Map<number, string>();
  if (!access) return lines;
  const margins = await fetchMatchMargins((fn, args) => supabase.rpc(fn, args), cards.map((c) => c.match_id));
  for (const card of cards) {
    if (card.listing_id == null || card.match_id == null || lines.has(card.listing_id)) continue;
    const ref = margins.get(card.match_id);
    const line = ref ? marginCardLine(ref) : null;
    if (line) lines.set(card.listing_id, line);
  }
  return lines;
}

/**
 * Juan, 02/11: the other plans see where Pro has a margin, never the margin.
 * Without access, the listing ids among `cards` whose match has one a Pro user
 * would see as a figure (asMarginRef: not «pocas agencias», a plausible price).
 * margin_ref is not readable with the user's session, so this reads it with
 * the server's client, only from `userId`'s own matches; only ids leave here.
 */
export async function marginTeasersFor(userId: string, access: MarginAccess | null, cards: MarginCard[]): Promise<Set<number>> {
  const out = new Set<number>();
  const ids = [...new Set(cards.map((c) => c.match_id).filter((id): id is number => id != null))];
  if (access || !ids.length) return out;
  try {
    const { data, error } = await createAdminClient()
      .from("matches")
      .select("id, margin_ref, search_profiles!inner(user_id)")
      .in("id", ids)
      .eq("search_profiles.user_id", userId)
      .not("margin_ref", "is", null);
    if (error || !data) return out;
    const shown = new Set(data.filter((row) => asMarginRef(row.margin_ref) != null).map((row) => Number(row.id)));
    for (const card of cards) {
      if (card.listing_id != null && card.match_id != null && shown.has(card.match_id)) out.add(card.listing_id);
    }
  } catch {
    // No teaser rather than a broken page.
  }
  return out;
}
