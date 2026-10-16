import { describe, expect, it } from "vitest";

import { filterSummary, reasonValue } from "./admin-format";

describe("filterSummary", () => {
  it("summarizes a model search as before", () => {
    expect(filterSummary({ make: "Ford", model: "Fiesta", year_min: 2016, year_max: 2018, price_max: 11500, km_max: 150000, transmission: "manual" }))
      .toBe("Ford Fiesta · 2016–2018 · ≤ USD 11.500 · ≤ 150.000 km · manual");
    expect(filterSummary(null)).toBe("Sin vehículo");
  });
  it("names a model-less search by its body types (docs/CARROCERIA.md)", () => {
    expect(filterSummary({ body_types: ["suv", "pickup"], price_max: 20000, currency: "USD" })).toBe("SUV o Pick-up · sin modelo · ≤ USD 20.000");
    expect(filterSummary({ body_types: "suv" })).toBe("Sin vehículo");
  });
  it("adds a model's body types at the end", () => {
    expect(filterSummary({ make: "Chevrolet", model: "Corsa", body_types: ["rural", "sedan"] })).toBe("Chevrolet Corsa · Sedán o Rural");
  });
  it("writes a reason as §45 does", () => {
    expect([reasonValue("ok"), reasonValue("fail"), reasonValue("unknown")]).toEqual(["true", "false", "unknown"]);
  });
});
