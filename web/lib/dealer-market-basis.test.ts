import { describe, expect, it } from "vitest";

import { kmBandText, marketBasisChip, marketBasisNote, marketBasisText, parseMarket } from "@/lib/dealer-insights";

const ref = (over: Record<string, unknown>) => parseMarket({ n: 12, median: 9400, p25: 9200, p75: 9600, vs_market_pct: -10, enough: true, ...over });

describe("the market reference by km (dealer_market_ref's basis)", () => {
  it("reads basis, km band and the whole model; an old row without them is the whole model", () => {
    const m = ref({ basis: "version_km", km: 100000, km_tol: 20000, wide: { n: 40, median: 10900, vs_market_pct: -22.4 } })!;
    expect([m.basis, m.km, m.kmTol, m.wide]).toEqual(["version_km", 100000, 20000, { n: 40, median: 10900, vs_market_pct: -22.4 }]);
    expect(kmBandText(m)).toBe("80.000 a 120.000 km");
    const old = ref({})!;
    expect([old.basis, old.km, old.kmTol, old.wide]).toEqual(["model", null, null, null]);
    expect(ref({ basis: "otra" })!.basis).toBe("model");
    expect(kmBandText(ref({ basis: "km", km: 10000, km_tol: 15000 }))).toBe("0 a 25.000 km");
  });

  it("says against what the price is compared", () => {
    expect(marketBasisText(ref({ basis: "version_km", km: 100000, km_tol: 20000 })))
      .toBe("Comparado con 12 avisos de la misma versión, año ±1 y kilómetros parecidos (80.000 a 120.000 km).");
    expect(marketBasisText(ref({ basis: "km", km: 100000, km_tol: 20000 })))
      .toBe("Comparado con 12 avisos del modelo, año ±1 y kilómetros parecidos (80.000 a 120.000 km).");
    expect(marketBasisText(ref({ basis: "model" })))
      .toBe("Comparado con 12 avisos del modelo, año ±1, sin mirar kilómetros. Cargá los km del auto: es lo que más mueve el precio.");
    expect(marketBasisText(ref({ basis: "model", km: 300000, km_tol: 60000 })))
      .toBe("Hay pocos avisos con kilómetros parecidos (240.000 a 360.000 km): comparado con 12 avisos del modelo, año ±1, de cualquier kilometraje.");
    expect(marketBasisText(ref({ n: 0 }))).toBeNull();
    expect(marketBasisText(null)).toBeNull();
  });

  it("flags in the table only a reference that could not take the km", () => {
    expect(marketBasisNote(ref({ basis: "km", km: 100000, km_tol: 20000 }))).toBeNull();
    expect(marketBasisNote(ref({ basis: "version_km", km: 100000, km_tol: 20000 }))).toBeNull();
    expect(marketBasisNote(ref({ basis: "model" }))).toBe("Sin km: comparación floja");
    expect(marketBasisNote(ref({ basis: "model", km: 300000, km_tol: 60000 }))).toBe("Pocos con km parecidos");
    expect(marketBasisNote(ref({ n: 0 }))).toBeNull();
    expect(marketBasisChip(ref({ basis: "km" }))).toBe("Km parecidos");
    expect(marketBasisChip(ref({ basis: "version_km" }))).toBe("Misma versión y km parecidos");
    expect(marketBasisChip(ref({ basis: "model" }))).toBeNull();
  });
});
