import { describe, expect, it } from "vitest";

import { DEFAULT_FIRST_YEAR, MIN_YEAR, SearchInput, yearOptions } from "./search-form";

describe("yearOptions", () => {
  it("starts at the catalog's year_from, before 1990 too (Ford F-100 1959–2011)", () => {
    const years = yearOptions({ yearFrom: 1959, yearTo: 2011 }, 2026);
    expect(years[0]).toBe(2011);
    expect(years.at(-1)).toBe(1959);
    expect(years).toHaveLength(2011 - 1959 + 1);
  });

  it("starts at 1990 for a model without a year_from", () => {
    expect(yearOptions({ yearFrom: null, yearTo: null }, 2026).at(-1)).toBe(DEFAULT_FIRST_YEAR);
    expect(yearOptions(undefined, 2026)).toHaveLength(2026 - 1990 + 1);
  });

  it("never goes below the schema floor nor past this year", () => {
    expect(yearOptions({ yearFrom: 1930, yearTo: null }, 2026).at(-1)).toBe(MIN_YEAR);
    expect(yearOptions({ yearFrom: 2024, yearTo: 2030 }, 2026)).toEqual([2026, 2025, 2024]);
  });

  it("keeps models that start after 1990 where they were", () => {
    expect(yearOptions({ yearFrom: 1995, yearTo: 2014 }, 2026).at(-1)).toBe(1995);
  });

  it("offers only years the schema accepts", () => {
    const oldest = yearOptions({ yearFrom: 1959, yearTo: 2011 }, 2026).at(-1)!;
    expect(() => SearchInput.parse({ make: "Ford", model: "F-100", year_min: oldest })).not.toThrow();
  });
});
