import { describe, expect, it } from "vitest";

import { priceGap, priceGapLine } from "./price-gap";
import type { PriceRef } from "./types";

// The Toyota Corolla XLI 2017 of Juan's 02/11 screenshot: ARS 23.000.000, about USD 14.791.
const REF: PriceRef = { n: 15, level_used: "model", median: 15434, p25: 13917, p75: 15846, median_km: null, diff_pct: 4.17 };
const COROLLA = { price_usd: 14791, price_partial: false };

describe("priceGap (§19)", () => {
  it("the Corolla: about USD 600 below what similar cars ask, 4 %", () => {
    const g = priceGap(COROLLA, REF, 5)!;
    expect(g).toEqual({ usd: 14791, median: 15434, diff: 4.17, gap: 600, inLine: false });
    expect(priceGapLine(g)).toEqual({ gap: "USD 600 debajo", rest: " de lo que suelen pedir por autos parecidos (-4%)." });
  });

  it("above the market, with the sign the other way", () => {
    const g = priceGap({ price_usd: 16700, price_partial: false }, { ...REF, diff_pct: -8.2 }, 5)!;
    expect(g.gap).toBe(1300);
    expect(priceGapLine(g)).toEqual({ gap: "USD 1.300 arriba", rest: " de lo que suelen pedir por autos parecidos (+8%)." });
  });

  it("works the difference out when price_ref has none", () => {
    expect(priceGap(COROLLA, { ...REF, diff_pct: null }, 5)!.diff).toBeCloseTo(4.166, 3);
  });

  it("in line under 2,5 % or USD 100 apart", () => {
    const close = priceGap({ price_usd: 15100, price_partial: false }, { ...REF, diff_pct: 2.2 }, 5)!;
    expect(close.inLine).toBe(true);
    expect(priceGapLine(close)).toEqual({ gap: null, rest: "En línea con lo que suelen pedir por autos parecidos." });
    expect(priceGap({ price_usd: 1000, price_partial: false }, { ...REF, median: 1040, diff_pct: 3.8 }, 5)!.inLine).toBe(true);
  });

  it("nothing to compare: a partial price, no dollars, no or too few comparables", () => {
    expect(priceGap({ ...COROLLA, price_partial: true }, REF, 5)).toBeNull();
    expect(priceGap({ ...COROLLA, price_usd: null }, REF, 5)).toBeNull();
    expect(priceGap(COROLLA, null, 5)).toBeNull();
    expect(priceGap(COROLLA, { ...REF, median: null }, 5)).toBeNull();
    expect(priceGap(COROLLA, { ...REF, n: 4 }, 5)).toBeNull();
  });
});
