import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ListingCard } from "@/components/app/listing-card";
import { forbiddenTermsIn } from "@/lib/copy";
import { OTHER_VERSION, otherVersionMatchIds } from "@/lib/other-version";

/**
 * Trim blando (docs/TRIM_BLANDO.md): the worker marks matches.score_breakdown.trim_cap for a car of another
 * version than a non-strict search names; the card says «Otra versión» from that mark.
 */
const CARD: ComponentProps<typeof ListingCard>["card"] = {
  listing_id: 1, make: "Ford", model: "Fiesta", trim: "SE Plus", year: 2017, title: "Ford Fiesta SE Plus 2017",
  price: 10300, currency: "USD", mileage_km: 112000, location_text: "Vicente López", published_at: null,
  first_seen_at: "2026-11-24T12:00:00Z", images: [], level: "match", score: 81, status: "new", saved: false,
  profile_name: "Fiesta", listing_status: "active", probable_repost_of: null,
};

describe("the copy", () => {
  it("is exact and passes the copy lint", () => {
    expect(OTHER_VERSION).toBe("Otra versión");
    expect(forbiddenTermsIn(OTHER_VERSION)).toEqual([]);
  });
});

describe("otherVersionMatchIds", () => {
  it("only the matches the worker marked with a real true", () => {
    const ids = otherVersionMatchIds([
      { id: 1, capped: "true" }, { id: 2, capped: "false" }, { id: 3, capped: null }, { id: null, capped: "true" },
    ]);
    expect([...ids]).toEqual([1]);
  });
  it("nothing without rows", () => {
    expect(otherVersionMatchIds(null).size).toBe(0);
    expect(otherVersionMatchIds(undefined).size).toBe(0);
  });
});

describe("the card", () => {
  it("shows the tag next to the version only when it is another one", () => {
    const html = renderToStaticMarkup(createElement(ListingCard, { card: CARD, otherVersion: true }));
    expect(html).toContain('data-testid="card-other-version"');
    expect(html).toContain("Otra versión");
    expect(html).toContain("Ford Fiesta SE Plus 2017");
  });
  it("has none by default", () => {
    const html = renderToStaticMarkup(createElement(ListingCard, { card: CARD }));
    expect(html).not.toContain("card-other-version");
    expect(html).not.toContain("Otra versión");
  });
});
