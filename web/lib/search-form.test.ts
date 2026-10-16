import { describe, expect, it } from "vitest";

import { SearchInput, defaultName, fromProfile, isModelLess, matchingChanged, modelBodyTypes, toColumns, toFilters } from "./search-form";
import type { SearchProfile } from "./types";

const ALL = ["mercadolibre", "kavak", "v6", "facebook", "autocosmos"];

const input = SearchInput.parse({
  make: "Ford",
  model: "Fiesta",
  trim: "Titanium",
  year_min: 2016,
  year_max: 2018,
  price_max: 11500,
  km_max: 150000,
  transmission: "manual",
  sources: ALL,
  location: { label: "AMBA", lat: -34.6037, lon: -58.3816, radius_km: 60 },
  km_target: 120000,
});

describe("search form → search_profiles (sección 4.3)", () => {
  it("preserves all versions when creating and editing a search", () => {
    const values = SearchInput.parse({ ...input, trim: "Titanium", trims: ["Titanium", "SE"], trim_strict: true });
    const columns = toColumns(values, ALL);
    expect(columns.filters.trims).toEqual(["Titanium", "SE"]);
    expect(columns.filters.trim_strict).toBe(true);
    expect(columns.name).toBe("Ford Fiesta Titanium / SE");
    const stored = { ...columns, notification_frequency: "immediate", notify_min_level: "good" } as SearchProfile;
    expect(toColumns(fromProfile(stored, ALL), ALL).filters.trims).toEqual(["Titanium", "SE"]);
  });
  it("maps hard filters, soft preferences and the place", () => {
    const c = toColumns(input, ALL);
    expect(c.name).toBe("Ford Fiesta Titanium");
    expect(c.filters).toEqual({
      make: "Ford",
      model: "Fiesta",
      trims: ["Titanium"],
      trim_strict: false,
      year_min: 2016,
      year_max: 2018,
      price_max: 11500,
      currency: "USD",
      km_max: 150000,
      transmission: "manual",
      location_label: "AMBA",
    });
    expect(c.preferences).toEqual({ km_target: 120000 });
    expect([c.origin_lat, c.origin_lon, c.radius_km]).toEqual([-34.6037, -58.3816, 60]);
  });

  it("stores sources only when some are left out", () => {
    expect(toColumns({ ...input, sources: ["mercadolibre"] }, ALL).filters.sources).toEqual(["mercadolibre"]);
  });

  it("rejects a reversed year range", () => {
    const r = SearchInput.safeParse({ make: "Ford", model: "Fiesta", year_min: 2019, year_max: 2016 });
    expect(r.success).toBe(false);
  });

  it("keeps a whole-percent opportunity threshold, which never changes what matches (3.2)", () => {
    const values = SearchInput.parse({ ...input, opportunity_threshold_pct: 10 });
    const columns = toColumns(values, ALL);
    expect(columns.opportunity_threshold_pct).toBe(10);
    expect(SearchInput.parse(input).opportunity_threshold_pct).toBeNull();
    for (const bad of [0, 91, 7.5]) expect(SearchInput.safeParse({ ...input, opportunity_threshold_pct: bad }).success).toBe(false);
    const stored = { ...columns, id: 1, notification_frequency: "immediate", notify_min_level: "good" } as unknown as SearchProfile;
    expect(fromProfile(stored, ALL).opportunity_threshold_pct).toBe(10);
    expect(matchingChanged(stored, toColumns({ ...values, opportunity_threshold_pct: 15 }, ALL))).toBe(false);
  });

  it("round-trips a stored search and knows when matching changes", () => {
    const c = toColumns(input, ALL);
    const stored = { ...c, id: 1, notification_frequency: "immediate", notify_min_level: "good" } as unknown as SearchProfile;
    expect(fromProfile(stored, ALL)).toMatchObject({ make: "Ford", trim: "Titanium", location: { label: "AMBA" } });
    expect(matchingChanged(stored, toColumns({ ...input, notification_frequency: "daily" }, ALL))).toBe(false);
    expect(matchingChanged(stored, toColumns({ ...input, price_max: 12000 }, ALL))).toBe(true);
  });
});

describe("body types (docs/CARROCERIA.md)", () => {
  const suv = { body_types: ["suv"], price_max: 20000, sources: ALL };
  const issues = (raw: Parameters<typeof SearchInput.safeParse>[0]) => {
    const r = SearchInput.safeParse(raw);
    return r.success ? {} : Object.fromEntries(r.error.issues.map((i) => [String(i.path[0]), i.message]));
  };

  it("accepts a search without make and model with body types and a max price", () => {
    const values = SearchInput.parse(suv);
    expect(isModelLess(values)).toBe(true);
    const c = toColumns(values, ALL);
    // No make, model or versions: the shape the database and the worker read as model-less.
    expect(c.filters).toEqual({ body_types: ["suv"], price_max: 20000, currency: "USD" });
    expect(c.name).toBe("SUV hasta USD 20.000");
  });

  it("asks for a model, or for body types and a max price", () => {
    expect(issues({ sources: ALL })).toEqual({
      make: "Elegí una marca.", model: "Elegí un modelo.", body_types: "Elegí al menos una carrocería.",
    });
    expect(issues({ body_types: ["suv"] })).toEqual({ price_max: "Poné un precio máximo para buscar por carrocería." });
    expect(issues({ make: "Ford", body_types: ["suv"], price_max: 1 })).toEqual({ model: "Elegí un modelo." });
    expect(issues({ model: "Ka" })).toEqual({ make: "Elegí una marca." });
    expect(issues({ make: " ", model: " ", body_types: ["suv"], price_max: 1 })).toEqual({});
    expect(SearchInput.safeParse({ ...suv, body_types: ["camioneta"] }).success).toBe(false);
  });

  it("stores body types only when there are some, once each, in the canonical order", () => {
    expect(toFilters(SearchInput.parse(input), ALL)).not.toHaveProperty("body_types");
    const within = SearchInput.parse({ ...input, body_types: ["sedan", "hatchback", "sedan"] });
    expect(toFilters(within, ALL)).toMatchObject({ make: "Ford", model: "Fiesta", body_types: ["sedan", "hatchback"] });
    const two = SearchInput.parse({ ...suv, body_types: ["pickup", "suv"], currency: "ARS", price_max: 25_000_000 });
    expect(toFilters(two).body_types).toEqual(["suv", "pickup"]);
    expect(toColumns(two, ALL).name).toBe("SUV o Pick-up hasta $ 25.000.000");
  });

  it("names a model-less search by its body types and price, and a model search as before", () => {
    expect(defaultName({ body_types: ["suv"], price_max: 20000, currency: "USD" })).toBe("SUV hasta USD 20.000");
    expect(defaultName({ body_types: ["sedan", "suv", "pickup"] })).toBe("Sedán, SUV o Pick-up");
    expect(defaultName({ body_types: [] })).toBe("");
    expect(defaultName({ make: "Ford", model: "Ka", body_types: ["sedan"] })).toBe("Ford Ka");
    const all = defaultName({ body_types: ["sedan", "hatchback", "suv", "pickup", "rural", "monovolumen", "coupe", "convertible", "utilitario"], price_max: 20000 });
    expect(all).toBe("9 carrocerías hasta USD 20.000");
  });

  it("round-trips a model-less search and rematches when the body types change", () => {
    const c = toColumns(SearchInput.parse({ ...suv, body_types: ["suv", "pickup"] }), ALL);
    const stored = { ...c, id: 2, notification_frequency: "daily", notify_min_level: "good" } as unknown as SearchProfile;
    const back = fromProfile(stored, ALL);
    expect(back).toMatchObject({ make: "", model: "", body_types: ["suv", "pickup"], price_max: 20000, name: "SUV o Pick-up hasta USD 20.000" });
    expect(matchingChanged(stored, toColumns(back, ALL))).toBe(false);
    expect(matchingChanged(stored, toColumns({ ...back, body_types: ["suv"] }, ALL))).toBe(true);
    expect(fromProfile({ ...stored, filters: { make: "Ford", model: "Ka" } }, ALL).body_types).toEqual([]);
  });

  it("offers body types within a model only when the catalog lists two or more", () => {
    expect(modelBodyTypes(["hatchback", "sedan"])).toEqual(["hatchback", "sedan"]);
    expect(modelBodyTypes(["pickup"])).toEqual([]);
    expect(modelBodyTypes([])).toEqual([]);
    expect(modelBodyTypes(undefined)).toEqual([]);
    expect(modelBodyTypes(["suv", "camioneta"])).toEqual([]);
  });
});
