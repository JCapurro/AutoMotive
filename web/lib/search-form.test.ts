import { describe, expect, it } from "vitest";

import { SearchInput, fromProfile, matchingChanged, toColumns } from "./search-form";
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

  it("round-trips a stored search and knows when matching changes", () => {
    const c = toColumns(input, ALL);
    const stored = { ...c, id: 1, notification_frequency: "immediate", notify_min_level: "good" } as unknown as SearchProfile;
    expect(fromProfile(stored, ALL)).toMatchObject({ make: "Ford", trim: "Titanium", location: { label: "AMBA" } });
    expect(matchingChanged(stored, toColumns({ ...input, notification_frequency: "daily" }, ALL))).toBe(false);
    expect(matchingChanged(stored, toColumns({ ...input, price_max: 12000 }, ALL))).toBe(true);
  });
});
