import { describe, expect, it } from "vitest";

import { provinceCapital } from "@/lib/argentina-locations";
import { type AssistedDraft, draftToValues } from "@/lib/assisted";
import { locationCap, locationCapText } from "@/lib/pro";
import { SearchInput, toFilters } from "@/lib/search-form";

const base = SearchInput.parse({ make: "Toyota", model: "Corolla" });

function draft(location: string, locations: string[], radius_km: number | null = null): AssistedDraft {
  return {
    values: {
      make: "Toyota", model: "Corolla", trim: "", trims: [], trim_strict: false, year_min: null, year_max: null,
      price_max: null, price_target: null, currency: "ARS", km_max: null, km_target: null, transmission: "",
      fuel: "", body_types: [], seller_type: "", location, locations, radius_km,
    },
    resolved: true,
    notes: [],
  };
}

describe("a search that names several places", () => {
  it("«Chaco o Corrientes» is Resistencia and Corrientes", () => {
    const { values, notes } = draftToValues(draft("Chaco", ["Chaco", "Corrientes"]), base);
    expect(values.location?.label).toMatch(/^Resistencia/);
    expect(values.extra_locations.map((z) => z.label)).toEqual([expect.stringMatching(/^Corrientes/)]);
    expect(notes).toEqual([]);
  });

  it("a province alone is its capital", () => {
    expect(provinceCapital("Chaco")?.city).toBe("Resistencia");
    expect(provinceCapital("provincia de Misiones")?.city).toBe("Posadas");
    expect(provinceCapital("Chaquito")).toBeUndefined();
  });

  it("drafts from before `locations` keep their single place", () => {
    const { values } = draftToValues(draft("Rosario", []), base);
    expect(values.location?.label).toMatch(/^Rosario/);
    expect(values.extra_locations).toEqual([]);
  });

  it("the plan's cap keeps the first places and says so", () => {
    const { values, notes } = draftToValues(draft("Rosario", ["Rosario", "Córdoba", "Mendoza", "Salta"]), base, true, 3);
    expect(values.extra_locations).toHaveLength(2);
    expect(notes.join(" ")).toContain("hasta tres zonas");
  });

  it("an unknown place is reported and the rest are kept", () => {
    const { values, notes } = draftToValues(draft("Rosario", ["Rosario", "Narnia"]), base);
    expect(values.location?.label).toMatch(/^Rosario/);
    expect(notes.join(" ")).toContain("Narnia");
  });

  it("the places are stored in filters, next to the label", () => {
    const { values } = draftToValues(draft("Rosario", ["Rosario", "Córdoba"], 50), base);
    const f = toFilters(values);
    expect(f.extra_locations).toHaveLength(1);
    expect(f.extra_locations?.[0].radius_km).toBe(50);
  });

  it("extras without a place of their own are dropped", () => {
    const v = SearchInput.parse({ make: "Toyota", model: "Corolla",
      extra_locations: [{ label: "Rosario", lat: -32.9, lon: -60.6, radius_km: 30 }] });
    expect(toFilters(v).extra_locations).toBeUndefined();
  });
});

describe("the plan's cap on places", () => {
  const access = (max_locations?: number) => ({ enforced: true, limits: { max_locations } }) as never;
  it("is the plan's when enforced and none otherwise", () => {
    expect(locationCap(access(3))).toBe(3);
    expect(locationCap(access())).toBeNull();
    expect(locationCap({ enforced: true, plan: "free", limits: {} } as never)).toBe(3);
    expect(locationCap({ enforced: true, plan: "pass", limits: {} } as never)).toBeNull();
    expect(locationCap({ enforced: false, limits: { max_locations: 3 } } as never)).toBeNull();
    expect(locationCap(null)).toBeNull();
  });
  it("is worded for the user", () => {
    expect(locationCapText(3)).toContain("tres zonas");
    expect(locationCapText(null)).toBeNull();
  });
});

describe("zones with the country words and the autosave", () => {
  it("«Chaco, Argentina» keeps Chaco and a bare «Argentina» asks for the whole country", () => {
    expect(draftToValues(draft("Chaco, Argentina", []), base).values.location?.label).toMatch(/^Resistencia/);
    const { values, notes } = draftToValues(draft("Argentina", ["Argentina"]), base);
    expect(values.location).toBeNull();
    expect(notes.join(" ")).toContain("todo el país");
  });

  it("«Santa Fe o Buenos Aires» in one text are two zones", () => {
    const { values } = draftToValues(draft("Rosario o Córdoba", []), base);
    expect(values.location?.label).toMatch(/^Rosario/);
    expect(values.extra_locations.map((z) => z.label)).toEqual([expect.stringMatching(/^Córdoba/)]);
  });
});
