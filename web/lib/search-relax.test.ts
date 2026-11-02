import { describe, expect, it } from "vitest";

import { SearchInput } from "@/lib/search-form";
import { MAX_RELAX_VARIANTS, applyRelax, bestSuggestions, relaxVariants, roundPrice } from "@/lib/search-relax";

const search = (raw: SearchInput) => SearchInput.parse(raw);
const keys = (raw: SearchInput) => relaxVariants(search(raw), 2026).map((r) => r.key);

describe("relaxVariants", () => {
  it("loosens the versions, the years and the place of «Renault Sandero GT Line 2021»", () => {
    const v = search({
      make: "Renault", model: "Sandero", trims: ["GT Line"], trim_strict: true, year_min: 2021, year_max: 2021,
      location: { label: "CABA", lat: -34.6, lon: -58.4, radius_km: 30 },
    });
    expect(relaxVariants(v, 2026)).toEqual([
      { key: "trims", label: "Sin la versión GT Line", change: { trim_strict: false } },
      { key: "years", label: "2019–2023", change: { year_min: 2019, year_max: 2023 } },
      { key: "location", label: "Toda la Argentina", change: { location: null } },
    ]);
  });

  it("widens the years, the price by 20% and drops the km cap of «Audi A3 2010-2012, < USD 11.000, < 150.000 km»", () => {
    const v = search({ make: "Audi", model: "A3", year_min: 2010, year_max: 2012, price_max: 11000, currency: "USD", km_max: 150000 });
    expect(relaxVariants(v, 2026)).toEqual([
      { key: "years", label: "2008–2014", change: { year_min: 2008, year_max: 2014 } },
      { key: "price", label: "Hasta USD 13.000", change: { price_max: 13000 } },
      { key: "km", label: "Sin tope de km", change: { km_max: null } },
    ]);
  });

  it("skips versions that don't filter (no trim_strict)", () => {
    expect(keys({ make: "Renault", model: "Sandero", trims: ["GT Line"] })).toEqual([]);
  });

  it("widens one end of the years alone and never past next year", () => {
    expect(relaxVariants(search({ make: "Ford", model: "Ka", year_min: 2015 }), 2026)[0]).toMatchObject({ label: "Desde 2013", change: { year_min: 2013, year_max: null } });
    expect(relaxVariants(search({ make: "Ford", model: "Ka", year_max: 2026 }), 2026)[0]).toMatchObject({ label: "Hasta 2027", change: { year_max: 2027 } });
    expect(keys({ make: "Ford", model: "Ka", year_max: 2027 })).toEqual([]);
  });

  it("shows a peso budget in pesos", () => {
    const [price] = relaxVariants(search({ make: "Fiat", model: "Cronos", price_max: 25_000_000, currency: "ARS" }), 2026);
    expect(price).toMatchObject({ label: "Hasta $ 30.000.000", change: { price_max: 30_000_000 } });
  });

  it("loosens transmission, fuel and body types, up to the cap", () => {
    const all = keys({
      make: "Peugeot", model: "208", trims: ["GT"], trim_strict: true, year_min: 2020, price_max: 20000, km_max: 50000,
      location: { label: "Rosario", lat: -32.9, lon: -60.6, radius_km: 50 }, transmission: "automatic", fuel: "nafta",
      body_types: ["hatchback"],
    });
    expect(all).toEqual(["trims", "years", "price", "km", "location", "transmission"]);
    expect(all).toHaveLength(MAX_RELAX_VARIANTS);
    expect(keys({ make: "Peugeot", model: "208", fuel: "nafta", body_types: ["hatchback"] })).toEqual(["fuel", "body_types"]);
  });

  it("has nothing for a model-less search", () => {
    expect(keys({ body_types: ["suv"], price_max: 20000, km_max: 100000 })).toEqual([]);
  });

  it("applies a change over the search", () => {
    const v = search({ make: "Audi", model: "A3", km_max: 150000, price_max: 11000 });
    expect(applyRelax(v, { km_max: null })).toMatchObject({ make: "Audi", km_max: null, price_max: 11000 });
  });
});

describe("roundPrice", () => {
  it("keeps two significant digits and stays above the original", () => {
    expect(roundPrice(13200, 11000)).toBe(13000);
    expect(roundPrice(8450, 7000)).toBe(8500);
    expect(roundPrice(1010, 1000)).toBe(1100);
    expect(roundPrice(12, 10)).toBe(12);
  });
});

describe("bestSuggestions", () => {
  const s = (key: "trims" | "years" | "price" | "km", count: number) => ({ key, label: key, change: {}, count });

  it("keeps the ones with listings, most first, up to three", () => {
    expect(bestSuggestions([s("trims", 0), s("years", 51), s("price", 20), s("km", 51)]).map((x) => x.key))
      .toEqual(["years", "km", "price"]);
    expect(bestSuggestions([s("trims", 0)])).toEqual([]);
    expect(bestSuggestions([s("trims", 3), s("years", 2), s("price", 1), s("km", 9)])).toHaveLength(3);
  });
});

describe("PRO-01: the strict seller filter", () => {
  it("offers «Cualquier vendedor» only for a strict seller filter", () => {
    const strict = relaxVariants(search({ make: "Ford", model: "Fiesta", seller_type: "private", seller_strict: true }), 2026);
    expect(strict).toEqual([{ key: "seller", label: "Cualquier vendedor", change: { seller_strict: false } }]);
    expect(keys({ make: "Ford", model: "Fiesta", seller_type: "private" })).toEqual([]);
    // Applied, the type stays as the preference.
    const applied = applyRelax(search({ make: "Ford", model: "Fiesta", seller_type: "private", seller_strict: true }), strict[0].change);
    expect([applied.seller_type, applied.seller_strict]).toEqual(["private", false]);
  });
});
