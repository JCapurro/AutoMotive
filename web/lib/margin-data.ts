import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { asStoredMargin, marginLine, type StoredMargin } from "@/lib/margin-view";
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

/** The cards of a page: listing_id -> the margin line of its match. Nothing without access. */
export async function marginLinesFor(supabase: Supabase, access: MarginAccess | null, cards: MarginCard[]): Promise<Map<number, string>> {
  const lines = new Map<number, string>();
  if (!access) return lines;
  const margins = await fetchMatchMargins((fn, args) => supabase.rpc(fn, args), cards.map((c) => c.match_id));
  for (const card of cards) {
    if (card.listing_id == null || card.match_id == null || lines.has(card.listing_id)) continue;
    const ref = margins.get(card.match_id);
    const line = ref ? marginLine(ref) : null;
    if (line) lines.set(card.listing_id, line);
  }
  return lines;
}
