import { describe, expect, it } from "vitest";

import { BODY_TYPE, BODY_TYPE_CODES, bodyTypeCodes, bodyTypesText } from "./copy";
import { describeFilters, describeVehicle, filterParts } from "./search";

describe("body type labels (docs/CARROCERIA.md)", () => {
  it("has the nine codes, in the worker's order, with their labels", () => {
    expect(BODY_TYPE_CODES).toEqual(["sedan", "hatchback", "suv", "pickup", "rural", "monovolumen", "coupe", "convertible", "utilitario"]);
    expect(BODY_TYPE_CODES.map((code) => BODY_TYPE[code])).toEqual(
      ["Sedán", "Hatchback", "SUV", "Pick-up", "Rural", "Monovolumen", "Coupé", "Convertible", "Utilitario"]);
  });
  it("joins labels in the canonical order and drops what isn't a code", () => {
    expect(bodyTypesText(["pickup", "suv"])).toBe("SUV o Pick-up");
    expect(bodyTypesText(["pickup", "sedan", "suv"])).toBe("Sedán, SUV o Pick-up");
    expect(bodyTypesText(["camioneta"])).toBe("");
    expect(bodyTypesText(undefined)).toBe("");
    expect(bodyTypeCodes(["suv", "suv", "x"])).toEqual(["suv"]);
  });
});

describe("dashboard chips", () => {
  it("describes a model-less search by its body types", () => {
    const filters = { body_types: ["suv", "pickup"], price_max: 20_000, currency: "USD" as const };
    expect(describeVehicle(filters)).toBe("SUV o Pick-up");
    expect(filterParts(filters)).toEqual(["hasta USD 20.000"]);
  });
  it("lists a model's body types among its filters", () => {
    const filters = { make: "Chevrolet", model: "Corsa", trims: [], body_types: ["rural"], fuel: "gnc", year_min: 2008 };
    expect(describeVehicle(filters)).toBe("Chevrolet Corsa");
    expect(filterParts(filters)).toEqual(["desde 2008", "GNC", "Rural"]);
    expect(describeFilters({ make: "Ford", model: "Fiesta" })).toBe("Sin filtros adicionales");
  });
  it("keeps the model description as before", () => {
    expect(describeVehicle({ make: "Ford", model: "Fiesta", trims: ["Titanium"] })).toBe("Ford Fiesta · Titanium (preferida)");
    expect(describeVehicle({ make: "Ford", model: "Fiesta", trims: ["Titanium"], trim_strict: true })).toBe("Ford Fiesta · Titanium");
    expect(describeVehicle({})).toBe("");
  });
});
