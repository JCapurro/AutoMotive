import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DealerFeesNotice } from "@/components/app/dealer-fees-notice";
import { SELLER_FORM_HINT, SELLER_INFERRED } from "./copy";
import { effectiveSeller, sellerLabel } from "./seller";

// F-02 paso 2 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): the
// twin of worker/intelligence/seller.py.
describe("effectiveSeller", () => {
  it.each([
    [{ seller_type: "dealer", dealer_inferred: false }, "dealer"],
    [{ seller_type: "dealer", dealer_inferred: true }, "dealer"],
    [{ seller_type: "private", dealer_inferred: true }, "dealer"],
    [{ seller_type: null, dealer_inferred: true }, "dealer"],
    [{ seller_type: "private", dealer_inferred: false }, "private"],
    [{ seller_type: null, dealer_inferred: false }, null],
    [{ seller_type: "private" }, "private"],
    [{}, null],
  ])("%j -> %s", (listing, expected) => {
    expect(effectiveSeller(listing)).toBe(expected);
  });
});

describe("sellerLabel", () => {
  it("names a «posible agencia» with how many cars it publishes", () => {
    expect(SELLER_INFERRED).toBe("Posible agencia");
    expect(sellerLabel({ seller_type: null, dealer_inferred: true, seller_listing_count: 6 })).toBe(
      "Posible agencia (publica 6 autos)",
    );
  });

  it("says when the listing itself says «particular» (Juan, 30/10)", () => {
    expect(sellerLabel({ seller_type: "private", dealer_inferred: true, seller_listing_count: 7 })).toBe(
      "Posible agencia (publica 7 autos); la publicación dice particular",
    );
  });

  it("never says «publica null autos»", () => {
    expect(sellerLabel({ seller_type: null, dealer_inferred: true, seller_listing_count: null })).toBe("Posible agencia");
  });

  it("keeps the source's own type otherwise", () => {
    expect(sellerLabel({ seller_type: "private", dealer_inferred: false, seller_listing_count: 3 })).toBe("Particular");
    expect(sellerLabel({ seller_type: "dealer", dealer_inferred: false, seller_listing_count: 9 })).toBe("Concesionaria");
    expect(sellerLabel({ seller_type: "dealer", dealer_inferred: true, seller_listing_count: 9 })).toBe("Concesionaria");
    expect(sellerLabel({ seller_type: null, dealer_inferred: false })).toBeNull();
    expect(sellerLabel({})).toBeNull();
  });
});

describe("DealerFeesNotice", () => {
  const html = (props: { sellerType?: string | null; dealerInferred?: boolean | null }) =>
    renderToStaticMarkup(createElement(DealerFeesNotice, props));

  it("shows for a dealer and for a «posible agencia»", () => {
    expect(html({ sellerType: "dealer" })).toContain('data-testid="dealer-fees-notice"');
    expect(html({ sellerType: "private", dealerInferred: true })).toContain('data-testid="dealer-fees-notice"');
    expect(html({ sellerType: null, dealerInferred: true })).toContain('data-testid="dealer-fees-notice"');
  });

  it("does not show for a private seller or an unknown one", () => {
    expect(html({ sellerType: "private", dealerInferred: false })).toBe("");
    expect(html({ sellerType: null })).toBe("");
    expect(html({})).toBe("");
  });
});

// That search-form.tsx shows it (data-testid=seller-type-hint) is e2e/seller.spec.ts.
it("the dealer preference hint is the approved copy", () => {
  expect(SELLER_FORM_HINT).toBe("Incluye posibles agencias.");
});
