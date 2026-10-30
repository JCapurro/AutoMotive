import { SELLER, SELLER_INFERRED } from "./copy";

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
