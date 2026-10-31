import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";
import { cache } from "react";

import { buyerJurisdiction } from "@/lib/buyer-jurisdiction";
import { webConfig } from "@/lib/config";
import {
  buildCostInput,
  type CostConfig,
  costLine,
  type CostRow,
  type Estimate,
  estimateCost,
  type FxQuote,
  searchZones,
  type Zone,
} from "@/lib/cost-estimator";
import type { SellerKind } from "@/lib/cost-estimate-view";
import { TIME_ZONE } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Database } from "@/types/database";

/**
 * PAR-01: what the listing page and the cards need to show the total cost
 * estimate, read on the server and only with the plan's total_cost flag
 * (Particular; Free during the pilot). Built over lib/cost-estimator.ts, the
 * twin of the worker's: the same partial-price rule, effective seller and
 * jurisdiction as the opportunity email.
 */

type Supabase = SupabaseClient<Database>;

/** The listings columns the estimate reads, the same the listing page has. */
export const CARD_COLUMNS = "id, price, currency, price_usd, price_partial, description_facts, seller_type, dealer_inferred, year, body_type";

/**
 * The latest stored quote for USD listings: the most recent blue row, else
 * the most recent oficial one (not "date desc, blue first": an oficial row of
 * today would beat yesterday's blue). fx_rates has no client access: admin client.
 */
export const latestFx = cache(async (): Promise<FxQuote | null> => {
  const admin = createAdminClient();
  for (const kind of ["blue", "oficial"]) {
    const { data } = await admin
      .from("fx_rates")
      .select("rate, kind, date")
      .eq("kind", kind)
      .order("date", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (data && Number(data.rate) > 0) return { rate: Number(data.rate), kind: data.kind, date: data.date };
  }
  return null;
});

const AR_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });

/** Today in Argentina, "YYYY-MM-DD" (fx.max_age_days counts from it). */
export function todayAr(now: Date = new Date()): string {
  return AR_DAY.format(now);
}

type SearchRow = { id?: number; origin_lat: number | null; origin_lon: number | null; filters: unknown };
type DefaultOrigin = { default_origin_lat: number | null; default_origin_lon: number | null; default_origin_label: string | null };

function zonesOfSearch(p: SearchRow): Zone[] {
  const f = (p.filters && typeof p.filters === "object" ? p.filters : {}) as { location_label?: string; extra_locations?: unknown };
  return searchZones({ lat: p.origin_lat, lon: p.origin_lon, label: f.location_label ?? null, extra_locations: f.extra_locations });
}

function zonesOfProfile(p: DefaultOrigin | null): Zone[] {
  return p ? searchZones({ lat: p.default_origin_lat, lon: p.default_origin_lon, label: p.default_origin_label }) : [];
}

async function allowed(supabase: Supabase): Promise<CostConfig | null> {
  const [{ data }, cfg] = await Promise.all([supabase.rpc("my_plan_feature", { p_feature: "total_cost" }), webConfig()]);
  return data === true ? cfg.costEstimator : null;
}

async function defaultOrigin(supabase: Supabase, userId: string): Promise<DefaultOrigin | null> {
  const { data } = await supabase
    .from("profiles")
    .select("default_origin_lat, default_origin_lon, default_origin_label")
    .eq("id", userId)
    .maybeSingle();
  return data ?? null;
}


export type CostView = {
  estimate: Estimate;
  line: string;
  /** The zones the jurisdiction came from, and whether they are a search's or the account's default place. */
  zones: Zone[];
  from: "search" | "profile";
  sellerKind: SellerKind;
  cfg: CostConfig;
};

function sellerKind(row: CostRow, seller: string | null): SellerKind {
  if (row.dealer_inferred && row.seller_type !== "dealer") return "inferred";
  return seller === "dealer" ? "dealer" : seller === "private" ? "private" : "none";
}

function estimateRow(row: CostRow, zones: Zone[], fx: FxQuote | null, cfg: CostConfig, today: string) {
  const input = buildCostInput(row, zones, fx, cfg, today, buyerJurisdiction);
  if (!input) return null;
  const estimate = estimateCost(input.listing, input.jurisdiction, input.seller, input.fx_latest, cfg);
  return estimate ? { estimate, seller: input.seller } : null;
}

/**
 * The listing page: the best match's search, else the account's default
 * place (profiles.default_origin_*), else no zone. Null without the flag,
 * a config or a price to estimate.
 */
export async function costEstimateFor(
  supabase: Supabase,
  userId: string,
  listing: CostRow,
  searchProfileId: number | null,
): Promise<CostView | null> {
  const cfg = await allowed(supabase);
  if (!cfg) return null;
  let zones: Zone[];
  let from: CostView["from"] = "search";
  if (searchProfileId != null) {
    const { data } = await supabase.from("search_profiles").select("origin_lat, origin_lon, filters").eq("id", searchProfileId).maybeSingle();
    zones = data ? zonesOfSearch(data) : [];
  } else {
    zones = zonesOfProfile(await defaultOrigin(supabase, userId));
    from = "profile";
  }
  const fx = listing.currency === "USD" ? await latestFx() : null;
  const out = estimateRow(listing, zones, fx, cfg, todayAr());
  if (!out) return null;
  return { estimate: out.estimate, line: costLine(out.estimate), zones, from, sellerKind: sellerKind(listing, out.seller), cfg };
}

export type CostCard = { listing_id: number | null; search_profile_id?: number | null };

/**
 * The cards of a page: one line per listing, the header of the listing
 * page. One listings query for the page, one for the distinct searches, the
 * account's default place only if a card has no search, and the quote only
 * for USD listings. Without the flag, nothing past the flag check.
 */
export async function costLinesFor(supabase: Supabase, userId: string, cards: CostCard[]): Promise<Map<number, string>> {
  const lines = new Map<number, string>();
  const ids = [...new Set(cards.map((c) => c.listing_id).filter((id): id is number => id != null))];
  if (!ids.length) return lines;
  const cfg = await allowed(supabase);
  if (!cfg) return lines;
  const profileIds = [...new Set(cards.map((c) => c.search_profile_id).filter((id): id is number => id != null))];
  const needsDefault = cards.some((c) => c.listing_id != null && c.search_profile_id == null);
  const [{ data: rows }, { data: searches }, origin] = await Promise.all([
    supabase.from("listings").select(CARD_COLUMNS).in("id", ids),
    profileIds.length
      ? supabase.from("search_profiles").select("id, origin_lat, origin_lon, filters").in("id", profileIds)
      : Promise.resolve({ data: [] as SearchRow[] }),
    needsDefault ? defaultOrigin(supabase, userId) : Promise.resolve(null),
  ]);
  const byId = new Map((rows ?? []).map((r) => [r.id, r as CostRow]));
  const zonesBySearch = new Map((searches ?? []).map((s) => [s.id as number, zonesOfSearch(s)]));
  const fx = (rows ?? []).some((r) => r.currency === "USD") ? await latestFx() : null;
  const today = todayAr();
  for (const card of cards) {
    const row = card.listing_id != null ? byId.get(card.listing_id) : undefined;
    if (!row || lines.has(card.listing_id!)) continue;
    const zones = card.search_profile_id != null ? (zonesBySearch.get(card.search_profile_id) ?? []) : zonesOfProfile(origin);
    const out = estimateRow(row, zones, fx, cfg, today);
    if (out) lines.set(card.listing_id!, costLine(out.estimate));
  }
  return lines;
}
