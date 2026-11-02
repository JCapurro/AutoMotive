import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ListingCard } from "@/components/app/listing-card";
import { SELLER_UNKNOWN, forbiddenTermsIn } from "@/lib/copy";
import { sellerFact, strictSellerFilterOn, strictSellerUnknown } from "@/lib/seller";

/**
 * PRO-01, option C (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md,
 * «Respuestas de Juan 02/11», 4): under the strict seller filter a listing whose
 * effective seller is unknown still passes, and the card and the listing page
 * say «vendedor sin dato». The rule is matches.match_reasons.seller unknown and
 * hard: match_cards.seller_unknown in SQL, strictSellerUnknown here, twin of
 * worker/intelligence/matching.strict_seller_unknown. Nothing changes without it,
 * and only while the search still has the strict filter (strictSellerFilterOn).
 */
const UNKNOWN_HARD = { seller: { result: "unknown", detail: "la publicación no lo informa", kind: "hard" } } as const;

describe("the copy", () => {
  it("is exact and passes the copy lint", () => {
    expect(SELLER_UNKNOWN).toBe("vendedor sin dato");
    expect(forbiddenTermsIn(SELLER_UNKNOWN)).toEqual([]);
  });
});

describe("strictSellerUnknown", () => {
  it("only when the hard check didn't know the seller", () => {
    expect(strictSellerUnknown(UNKNOWN_HARD, true)).toBe(true);
    expect(strictSellerUnknown({ seller: { result: "ok", detail: "particular", kind: "hard" } }, true)).toBe(false);
    expect(strictSellerUnknown({ seller_type: { result: "unknown", detail: "x", kind: "soft" } }, true)).toBe(false);
    expect(strictSellerUnknown({ seller: { result: "unknown", detail: "x", kind: "soft" } }, true)).toBe(false);
    for (const empty of [{}, null, undefined, "x", { seller: null }, { seller: "unknown" }]) {
      expect(strictSellerUnknown(empty, true)).toBe(false);
    }
  });

  it("not once the strict filter stopped applying (stale reasons of a gone listing after a downgrade)", () => {
    expect(strictSellerUnknown(UNKNOWN_HARD, false)).toBe(false);
  });
});

describe("strictSellerFilterOn", () => {
  it("a seller type stored and the owner's seller_filter_access", () => {
    expect(strictSellerFilterOn({ seller_types: ["private"] }, true)).toBe(true);
    expect(strictSellerFilterOn({ seller_types: ["private"] }, false)).toBe(false);
    expect(strictSellerFilterOn({ seller_types: ["dealer"] }, null)).toBe(false);
    expect(strictSellerFilterOn({ seller_types: [] }, true)).toBe(false);
    expect(strictSellerFilterOn({ make: "Ford" }, true)).toBe(false);
    expect(strictSellerFilterOn(null, true)).toBe(false);
  });
});

describe("sellerFact (the listing page's «Vendedor»)", () => {
  it("says «vendedor sin dato» instead of «No informado», keeping the seller's name", () => {
    expect(sellerFact({ seller_type: null }, UNKNOWN_HARD, true)).toBe(SELLER_UNKNOWN);
    expect(sellerFact({ seller_type: null, seller_name: "Juan" }, UNKNOWN_HARD, true)).toBe(`${SELLER_UNKNOWN}, Juan`);
  });

  it("is what it was without the strict filter", () => {
    expect(sellerFact({ seller_type: null }, {}, true)).toBe("No informado");
    expect(sellerFact({ seller_type: null }, UNKNOWN_HARD, false)).toBe("No informado");
    expect(sellerFact({ seller_type: null, seller_name: "Juan" }, null, true)).toBe("Juan");
    expect(sellerFact({ seller_type: "private", seller_name: "Juan" }, {}, true)).toBe("Particular, Juan");
    expect(sellerFact({ seller_type: "dealer", dealer_inferred: false }, { seller: { result: "ok", detail: "x", kind: "hard" } }, true))
      .toBe("Concesionaria");
  });
});

type Card = ComponentProps<typeof ListingCard>["card"];
const card: Card = {
  listing_id: 1, make: "Ford", model: "Fiesta", trim: null, year: 2017, title: "Ford Fiesta", price: 10300,
  currency: "USD", mileage_km: 112000, location_text: "Rosario", published_at: null, first_seen_at: "2026-10-14T12:00:00Z",
  images: [], level: "good", score: 70, status: "new", saved: false, profile_name: "Fiesta", listing_status: "active",
  probable_repost_of: null,
};

describe("the card", () => {
  it("shows the label in its meta line with match_cards.seller_unknown", () => {
    const html = renderToStaticMarkup(createElement(ListingCard, { card: { ...card, seller_unknown: true } }));
    expect(html).toMatch(/<span data-testid="card-seller-unknown">vendedor sin dato<\/span>/);
    expect(html.indexOf("112.000 km")).toBeLessThan(html.indexOf(SELLER_UNKNOWN));
  });

  it("renders byte for byte as before without it", () => {
    const plain = renderToStaticMarkup(createElement(ListingCard, { card }));
    expect(plain).not.toContain(SELLER_UNKNOWN);
    for (const v of [false, null, undefined]) {
      expect(renderToStaticMarkup(createElement(ListingCard, { card: { ...card, seller_unknown: v } }))).toBe(plain);
    }
  });
});
