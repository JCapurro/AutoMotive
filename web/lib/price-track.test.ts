import { describe, expect, it } from "vitest";

import { FORBIDDEN_TERMS, PRICE_TRACK } from "./copy";
import { dayMonth } from "./format";
import { fetchPriceTracks, hasNetDrop, type PriceTrack, summaryLine, trackingNote, trackLine } from "./price-track";

function track(over: Partial<PriceTrack> = {}): PriceTrack {
  return {
    listing_id: 1,
    drops: 1,
    rises: 0,
    first_at: "2026-09-20T15:00:00Z",
    first_price: 24000,
    first_currency: "USD",
    last_price: 22500,
    last_currency: "USD",
    cum_pct: 6.25,
    cum_usd: 1500,
    last_drop_at: "2026-09-25T15:00:00Z",
    ...over,
  };
}

// dayMonth as the page shows it (the ICU of the runtime decides 20/09 or 20/9).
const D = dayMonth("2026-09-20T15:00:00Z");

const ars = (over: Partial<PriceTrack> = {}) =>
  track({ first_price: 12_000_000, first_currency: "ARS", last_price: 10_800_000, last_currency: "ARS", cum_pct: 10, cum_usd: 800, ...over });

describe("trackLine (PAR-03)", () => {
  it("says one drop in the singular", () => {
    expect(trackLine(track())).toBe("Bajó 1 vez desde que la vimos: -USD 1.500 (-6,3%).");
  });

  it("says several drops in the plural", () => {
    expect(trackLine(track({ drops: 3 }))).toBe("Bajó 3 veces desde que la vimos: -USD 1.500 (-6,3%).");
  });

  it("tells pesos in pesos, with the dollars", () => {
    expect(trackLine(ars({ drops: 2 }))).toBe("Bajó 2 veces desde que la vimos: -$ 1.200.000 (-10,0%), unos USD 800.");
    expect(trackLine(ars({ cum_usd: null }))).toBe("Bajó 1 vez desde que la vimos: -$ 1.200.000 (-10,0%).");
  });

  it("tells a currency change in dollars", () => {
    expect(trackLine(track({ first_currency: "ARS", first_price: 12_000_000, cum_pct: 5, cum_usd: 500 }))).toBe(
      "Bajó 1 vez desde que la vimos: -USD 500 (-5,0%).",
    );
  });

  it("says nothing without a net drop", () => {
    for (const t of [null, undefined, track({ drops: 0 }), track({ cum_pct: 0 }), track({ cum_pct: -4 }), track({ cum_pct: null }), track({ cum_usd: null })]) {
      expect(trackLine(t)).toBeNull();
    }
    expect(hasNetDrop(track({ drops: 2, rises: 1, cum_pct: -3 }))).toBe(false);
  });
});

describe("summaryLine", () => {
  it("counts the drops since the first snapshot", () => {
    expect(summaryLine(track())).toBe(`1 baja · -USD 1.500 (-6,3%) desde el ${D}`);
    expect(summaryLine(track({ drops: 2 }))).toBe(`2 bajas · -USD 1.500 (-6,3%) desde el ${D}`);
    expect(summaryLine(ars({ drops: 3 }))).toBe(`3 bajas · -$ 1.200.000 (-10,0%) desde el ${D}`);
    expect(summaryLine(track({ cum_pct: -2 }))).toBeNull();
  });
});

describe("trackingNote", () => {
  it("says we count from the detection without published_at", () => {
    expect(trackingNote({ published_at: null }, "2026-09-20T15:00:00Z")).toBe(
      "No sabemos cuándo se publicó; contamos desde que la detectamos.",
    );
  });

  it("says since when we follow a listing published 2 or more days before we saw it", () => {
    expect(trackingNote({ published_at: "2026-09-18T15:00:00Z" }, "2026-09-20T15:00:00Z")).toBe(
      `Seguimos este aviso desde el ${D}; no vemos los cambios anteriores.`,
    );
    expect(trackingNote({ published_at: "2026-09-18T16:00:00Z" }, "2026-09-20T15:00:00Z")).toBeNull();
    expect(trackingNote({ published_at: "2026-09-18T15:00:00Z" }, null)).toBeNull();
  });
});

describe("fetchPriceTracks", () => {
  it("indexes the rows by listing and asks once for unique ids", async () => {
    const calls: number[][] = [];
    const map = await fetchPriceTracks(async (_fn, args) => {
      calls.push(args.p_listing_ids);
      return { data: [track({ listing_id: 7 }), track({ listing_id: 9, drops: 2 })], error: null };
    }, [7, 9, 7]);
    expect(calls).toEqual([[7, 9]]);
    expect(map.get(9)?.drops).toBe(2);
  });

  it("degrades to nothing when the RPC fails or is missing", async () => {
    expect((await fetchPriceTracks(async () => ({ data: null, error: { message: "no function" } }), [1])).size).toBe(0);
    expect((await fetchPriceTracks(async () => Promise.reject(new Error("down")), [1])).size).toBe(0);
    let called = false;
    await fetchPriceTracks(async () => ((called = true), { data: [], error: null }), []);
    expect(called).toBe(false);
  });
});

describe("copy", () => {
  it("keeps the PAR-03 texts prudent", () => {
    const texts = [...Object.values(PRICE_TRACK).flat(), trackLine(ars({ drops: 2 })) ?? "", summaryLine(track()) ?? ""];
    for (const text of texts) {
      const lower = text.toLowerCase();
      for (const term of FORBIDDEN_TERMS) expect(lower, `${text}: ${term}`).not.toContain(term);
      for (const term of ["precio de cierre", "ofertá", "equivale"]) expect(lower).not.toContain(term);
    }
  });
});
