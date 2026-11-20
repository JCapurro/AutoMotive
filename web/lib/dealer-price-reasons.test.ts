import { describe, expect, it } from "vitest";

import type { MarketRef } from "@/lib/dealer-insights";
import { parsePriceContext, type PriceContext, priceReasons } from "@/lib/dealer-price-reasons";

const market = (pct: number, over: Partial<MarketRef> = {}): MarketRef => ({ n: 40, median: 10000, p25: 9000, p75: 11000, vs_market_pct: pct, enough: true, ...over });
const empty = { n: 0, median: null };
const ctx = (over: Partial<PriceContext> = {}): PriceContext => ({
  km: 90000, kmN: 30, kmMedian: 90000, sameYear: empty, similarKm: empty, closest: empty, sameTrim: empty, dealers: empty, ...over,
});
const car = (priceUsd: number) => ({ priceUsd, year: 2016, trim: "S 1.6" });

describe("priceReasons", () => {
  it("says nothing for a price in line, or without a reference or a context", () => {
    expect(priceReasons(car(9500), market(-5), ctx())).toBeNull();
    expect(priceReasons(car(11000), market(10), ctx())).toBeNull();   // «En precio» in the panel
    expect(priceReasons(car(8000), market(-20, { enough: false }), ctx())).toBeNull();
    expect(priceReasons(car(8000), market(-20), null)).toBeNull();
    expect(priceReasons(car(8000), null, ctx())).toBeNull();
    expect(priceReasons({ ...car(0), priceUsd: null }, market(-20), ctx())).toBeNull();
  });

  it("explains a low price with more km, and closes the gap against the closest look-alikes", () => {
    const why = priceReasons(car(8200), market(-18), ctx({
      km: 140000, kmMedian: 95000, similarKm: { n: 12, median: 8400 }, closest: { n: 6, median: 8300 },
    }))!;
    expect(why.side).toBe("below");
    expect(why.short).toBe("Más km que los parecidos");
    expect(why.reasons).toEqual([
      "Tiene más kilómetros que los parecidos: 140.000 km contra 95.000 km de mediana. Los de kilometraje parecido se publican a USD 8.400 de mediana (12 avisos).",
    ]);
    expect(why.verdict).toBe("Contra los más parecidos (mismo año y kilómetros parecidos, 6 avisos, mediana USD 8.300) está en precio.");
    expect(why.missing).toBeNull();
  });

  it("names the trim, the year and the dealers only when they moved the way of the gap, with enough listings", () => {
    const why = priceReasons(car(8500), market(-15), ctx({
      sameTrim: { n: 9, median: 8800 }, sameYear: { n: 14, median: 9500 }, dealers: { n: 20, median: 10800 },
      similarKm: { n: 4, median: 8000 },
    }))!;
    expect(why.reasons).toEqual([
      "Su versión (S 1.6) se publica más barata que el resto del modelo: USD 8.800 de mediana en 9 avisos, contra USD 10.000 de todo el modelo.",
      "Los de su mismo año (2016) se publican más baratos que el grupo de año ±1: USD 9.500 de mediana en 14 avisos.",
    ]);
    expect(why.short).toBe("Su versión se publica más barata");
    expect(why.verdict).toBe("No hay suficientes avisos con el mismo año y kilómetros parecidos para medir cuánto de la diferencia explican.");
    // Four listings of the trim, or a trim 3 % cheaper, explain nothing.
    expect(priceReasons(car(8500), market(-15), ctx({ sameTrim: { n: 4, median: 8000 } }))!.reasons).toEqual([]);
    expect(priceReasons(car(8500), market(-15), ctx({ sameTrim: { n: 9, median: 9700 } }))!.reasons).toEqual([]);
    // Without the car's trim there is no trim to name.
    expect(priceReasons({ ...car(8500), trim: null }, market(-15), ctx({ sameTrim: { n: 9, median: 8800 } }))!.reasons).toEqual([]);
  });

  it("mirrors it for a price above: fewer km, a dearer trim, dealers asking more", () => {
    const why = priceReasons(car(11500), market(15), ctx({
      km: 40000, kmMedian: 90000, sameTrim: { n: 8, median: 11200 }, dealers: { n: 20, median: 10600 }, similarKm: { n: 7, median: 10200 },
    }))!;
    expect(why.side).toBe("above");
    expect(why.reasons).toEqual([
      "Tiene menos kilómetros que los parecidos: 40.000 km contra 90.000 km de mediana. Los de kilometraje parecido se publican a USD 10.200 de mediana (7 avisos).",
      "Su versión (S 1.6) se publica más cara que el resto del modelo: USD 11.200 de mediana en 8 avisos, contra USD 10.000 de todo el modelo.",
      "Las agencias publican este modelo más caro que el conjunto: USD 10.600 de mediana entre 20 avisos de agencias.",
    ]);
    expect(why.verdict).toBe("Contra los más parecidos (kilómetros parecidos, 7 avisos, mediana USD 10.200) sigue 13 % arriba.");
  });

  it("does not take more km as the reason of a HIGH price, nor fewer km of a low one", () => {
    expect(priceReasons(car(11500), market(15), ctx({ km: 140000, kmMedian: 90000 }))!.reasons).toEqual([]);
    expect(priceReasons(car(8500), market(-15), ctx({ km: 40000, kmMedian: 90000 }))!.reasons).toEqual([]);
  });

  it("says so when nothing explains the gap, and suspects a typo when it is huge", () => {
    const low = priceReasons(car(8500), market(-15), ctx())!;
    expect(low.reasons).toEqual([]);
    expect(low.short).toBe("Sin explicación en los datos");
    expect(low.verdict).toContain("Puede ser el estado del auto, o hay lugar para subir el precio.");
    expect(priceReasons(car(6000), market(-40), ctx())!.verdict).toContain("revisá la moneda y los ceros del precio");
    expect(priceReasons(car(12000), market(20), ctx())!.verdict).toContain("margen para negociar");
    // The closest look-alikes still leave it far: the verdict says how far.
    expect(priceReasons(car(8000), market(-20), ctx({ closest: { n: 5, median: 9800 } }))!.verdict)
      .toBe("Contra los más parecidos (mismo año y kilómetros parecidos, 5 avisos, mediana USD 9.800) sigue 18 % abajo. No encontramos una explicación en los datos (kilómetros, año, versión). Puede ser el estado del auto, o hay lugar para subir el precio.");
  });

  it("asks for the km or the trim it lacks", () => {
    expect(priceReasons(car(8500), market(-15), ctx({ km: null }))!.missing).toBe("Cargá los kilómetros: es lo que más mueve el precio, y sin ellos comparamos con autos de cualquier uso.");
    expect(priceReasons({ ...car(8500), trim: null }, market(-15), ctx())!.missing).toBe("Cargá la versión para comparar con la misma versión.");
  });
});

describe("parsePriceContext", () => {
  it("reads dealer_price_context()'s JSON tolerantly", () => {
    expect(parsePriceContext({ km: 100000, km_n: 6, km_median: 87500, same_year: { n: 3, median: 9500 }, similar_km: { n: 4, median: 9250 },
      closest: { n: 2, median: 9250 }, same_trim: { n: 3, median: 9000 }, dealers: { n: 3, median: 13000 } }))
      .toEqual({ km: 100000, kmN: 6, kmMedian: 87500, sameYear: { n: 3, median: 9500 }, similarKm: { n: 4, median: 9250 },
        closest: { n: 2, median: 9250 }, sameTrim: { n: 3, median: 9000 }, dealers: { n: 3, median: 13000 } });
    expect(parsePriceContext({ km: "x", same_year: [] })).toEqual(ctx({ km: null, kmN: 0, kmMedian: null }));
    expect(parsePriceContext(null)).toBeNull();
    expect(parsePriceContext([])).toBeNull();
  });
});

describe("priceReasons with a reference that already takes the km (20270102120000)", () => {
  const byKm = (pct: number, widePct: number, basis: "km" | "version_km" = "km") =>
    market(pct, { median: 8300, basis, km: 140000, kmTol: 28000, wide: { n: 40, median: 10000, vs_market_pct: widePct } });

  it("does not give the km as the explanation again, and says where the car would sit against the whole model", () => {
    const why = priceReasons(car(7100), byKm(-14.5, -29), ctx({ km: 140000, kmMedian: 95000, similarKm: { n: 12, median: 8300 } }))!;
    expect(why.reasons).toEqual([]);
    expect(why.wide).toBe("Contra todo el modelo, sin mirar kilómetros, estaría 29 % abajo: el auto tiene 140.000 km y la mediana del modelo es 95.000 km.");
    expect(why.verdict).toContain("No encontramos una explicación en los datos");
    expect(why.short).toBe("Sin explicación en los datos");
  });

  it("still names the trim (measured against the whole model) and the same-year look-alikes", () => {
    const why = priceReasons(car(7100), byKm(-14.5, -29), ctx({
      km: 140000, kmMedian: 95000, sameTrim: { n: 9, median: 8800 }, closest: { n: 6, median: 7400 }, similarKm: { n: 12, median: 8300 },
    }))!;
    expect(why.reasons).toEqual([
      "Su versión (S 1.6) se publica más barata que el resto del modelo: USD 8.800 de mediana en 9 avisos, contra USD 10.000 de todo el modelo.",
    ]);
    expect(why.verdict).toBe("Contra los más parecidos (mismo año y kilómetros parecidos, 6 avisos, mediana USD 7.400) está en precio.");
  });

  it("with the trim in the reference, neither the trim nor a closer group is offered", () => {
    const why = priceReasons(car(7100), byKm(-14.5, -29, "version_km"), ctx({
      km: 140000, kmMedian: 95000, sameTrim: { n: 9, median: 8800 }, closest: { n: 6, median: 7400 },
    }))!;
    expect(why.reasons).toEqual([]);
    expect(why.verdict).toContain("No encontramos una explicación en los datos");
  });

  it("leaves the whole-model line out when it says the same", () => {
    expect(priceReasons(car(7100), byKm(-14.5, -17), ctx({ km: 140000, kmMedian: 135000 }))!.wide).toBeNull();
    expect(priceReasons(car(8500), market(-15), ctx())!.wide).toBeNull();
  });
});
