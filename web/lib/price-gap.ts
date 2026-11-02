/**
 * §19: the published price against the observed market (the comparables'
 * median in matches.price_ref). The listing page's «¿Está bien de precio?»
 * and its decision panel read the same numbers from here.
 */
import { PRICE_GAP } from "@/lib/copy";
import { money, pct } from "@/lib/format";
import type { Listing, PriceRef } from "@/lib/types";

export type PriceGap = {
  usd: number;
  median: number;
  /** How far below the median, in % (negative: above); price_ref.diff_pct when stored. */
  diff: number;
  /** The difference in dollars, to the nearest 100. */
  gap: number;
  /** Under 2,5 % or USD 100 apart: no difference worth a sentence. */
  inLine: boolean;
};

/** Null when there is nothing to compare: a down payment or an installment, no price in dollars, or fewer than minN comparables. */
export function priceGap(listing: Pick<Listing, "price_usd" | "price_partial">, refs: PriceRef | null, minN: number): PriceGap | null {
  const usd = listing.price_usd;
  const median = refs?.median ?? null;
  if (listing.price_partial || !usd || !refs || !median || refs.n < minN) return null;
  const diff = refs.diff_pct ?? (1 - usd / median) * 100;
  const gap = Math.round(Math.abs(median - usd) / 100) * 100;
  return { usd, median, diff, gap, inLine: Math.abs(diff) < 2.5 || gap < 100 };
}

/** The panel's line in two parts: the gap («USD 600 debajo», highlighted when cheaper) and the rest of the sentence. */
export function priceGapLine(g: PriceGap): { gap: string | null; rest: string } {
  if (g.inLine) return { gap: null, rest: PRICE_GAP.inLine };
  const below = g.diff > 0;
  return {
    gap: (below ? PRICE_GAP.below : PRICE_GAP.above).replace("{gap}", money(g.gap, "USD")),
    rest: PRICE_GAP.rest.replace("{pct}", `${below ? "-" : "+"}${pct(Math.abs(g.diff))}`),
  };
}
