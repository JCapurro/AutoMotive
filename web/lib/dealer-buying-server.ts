import "server-only";

import { type BuyMarketQuery, type BuyOpportunity, parseBuyOpportunities, parseSellers, type SellerRow } from "@/lib/dealer-buying";
import { rpcCode } from "@/lib/dealer-program";
import { createClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";

/**
 * Fase 3 reads, always with the signed-in user's client: the RPCs check that
 * the user belongs to an approved agency. On a failure only the RPC's code is
 * logged and returned (never data).
 */

type Result<T> = { rows: T[]; error: string | null };

export async function buyOpportunities(): Promise<Result<BuyOpportunity>> {
  const { data, error } = await (await createClient()).rpc("dealer_buy_opportunities");
  if (error) {
    console.error("dealer_buy_opportunities:", error.code);
    return { rows: [], error: rpcCode(error.message) };
  }
  return { rows: parseBuyOpportunities(data), error: null };
}

export type BuyMarketListing = Database["public"]["Functions"]["dealer_buy_market_listings"]["Returns"][number];

export async function buyMarketListings(q: BuyMarketQuery): Promise<Result<BuyMarketListing>> {
  const { data, error } = await (await createClient()).rpc("dealer_buy_market_listings", {
    p_make: q.make, p_model: q.model, p_year_from: q.yearFrom, p_year_to: q.yearTo,
  });
  if (error) {
    console.error("dealer_buy_market_listings:", error.code);
    return { rows: [], error: rpcCode(error.message) };
  }
  return { rows: data ?? [], error: null };
}

export async function dealerSellers(): Promise<Result<SellerRow>> {
  const { data, error } = await (await createClient()).rpc("dealer_sellers");
  if (error) {
    console.error("dealer_sellers:", error.code);
    return { rows: [], error: rpcCode(error.message) };
  }
  return { rows: parseSellers(data), error: null };
}
