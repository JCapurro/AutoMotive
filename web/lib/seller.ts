import { SELLER, SELLER_INFERRED, SELLER_UNKNOWN } from "./copy";

/**
 * F-02 paso 2 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): the
 * effective seller. 'dealer' when the source says so or the listing is a
 * «posible agencia» (listings.dealer_inferred: its seller publishes
 * app_config.seller_classification.min_listings or more cars in the same
 * source); otherwise seller_type. Twin of worker/intelligence/seller.py.
 *
 * Every consumer that treats a seller as an agency reads it from here: the
 * dealer fees notice today, PRO-01's hard filter and PAR-01's costs tomorrow.
 */
export type SellerFields = {
  seller_type?: string | null;
  dealer_inferred?: boolean | null;
  seller_listing_count?: number | null;
};

export function effectiveSeller(listing: SellerFields): "dealer" | "private" | null {
  if (listing.seller_type === "dealer" || listing.dealer_inferred) return "dealer";
  return listing.seller_type === "private" ? "private" : null;
}

/** The listing page's «Vendedor»: «Posible agencia (publica N autos)», adding
 * «; la publicación dice particular» when the listing says so (Juan, 30/10);
 * otherwise the source's type; null when not informed. */
export function sellerLabel(listing: SellerFields): string | null {
  if (listing.dealer_inferred && listing.seller_type !== "dealer") {
    const n = listing.seller_listing_count;
    const label = n != null ? `${SELLER_INFERRED} (publica ${n} autos)` : SELLER_INFERRED;
    return listing.seller_type === "private" ? `${label}; la publicación dice particular` : label;
  }
  return listing.seller_type ? (SELLER[listing.seller_type] ?? listing.seller_type) : null;
}

/**
 * PRO-01, option C: the search has the strict seller filter right now: a
 * seller type stored and the owner's profiles.seller_filter_access (the flag
 * sync_seller_filter_access keeps with plan_feature('seller_filter')). Twin of
 * match_cards.seller_unknown's gate (20261129120100). The stored reasons of a
 * listing the rematch no longer rewrites (gone, paused) outlive a downgrade,
 * so the reasons alone don't say it.
 */
export function strictSellerFilterOn(filters: unknown, sellerFilterAccess: boolean | null | undefined): boolean {
  if (sellerFilterAccess !== true || !filters || typeof filters !== "object") return false;
  const types = (filters as Record<string, unknown>).seller_types;
  return Array.isArray(types) && types.length > 0;
}

/**
 * PRO-01, option C: the strict seller filter ran and didn't know the seller
 * (matches.match_reasons.seller unknown and hard), and it still applies
 * (`strictOn`, strictSellerFilterOn). Twin of match_cards.seller_unknown and
 * worker/intelligence/matching.strict_seller_unknown.
 */
export function strictSellerUnknown(reasons: unknown, strictOn: boolean): boolean {
  if (!strictOn || !reasons || typeof reasons !== "object") return false;
  const seller = (reasons as Record<string, unknown>).seller;
  if (!seller || typeof seller !== "object") return false;
  const { result, kind } = seller as { result?: unknown; kind?: unknown };
  return result === "unknown" && kind === "hard";
}

/** The listing page's «Vendedor» fact: the best match's strict filter without a known seller says so. */
export function sellerFact(listing: SellerFields & { seller_name?: string | null }, reasons: unknown, strictOn: boolean): string {
  const label = strictSellerUnknown(reasons, strictOn) ? SELLER_UNKNOWN : sellerLabel(listing);
  return [label, listing.seller_name].filter(Boolean).join(", ") || "No informado";
}
