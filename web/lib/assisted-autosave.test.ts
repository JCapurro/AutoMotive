import { describe, expect, it } from "vitest";

import { type AssistedDraft, type SearchLimit, draftToValues } from "@/lib/assisted";
import { AUTOSAVE_RADIUS_KM, autoSaveValues, inCatalog, noteNeedsChoice, sameProposal } from "@/lib/assisted-autosave";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";

const catalog: Catalog = [
  { make: "Toyota", models: [{ model: "Hilux", trims: ["SRV"], yearFrom: 2005, yearTo: null, transmissions: [], fuels: [], bodyTypes: ["pickup"] }] },
  { make: "Volkswagen", models: [{ model: "Gol Trend", trims: [], yearFrom: 2008, yearTo: 2023, transmissions: [], fuels: [], bodyTypes: [] }] },
];

const base: SearchValues = {
  name: "", make: "", model: "", trim: "", trims: [], trim_strict: false, year_min: null, year_max: null,
  price_max: null, currency: "USD", km_max: null, transmission: "", fuel: "", body_types: [], sources: ["mercadolibre"],
  location: null, extra_locations: [], km_target: null, price_target: null, seller_type: "", notification_frequency: "immediate",
  notify_min_level: "good", opportunity_threshold_pct: null,
};

function draft(values: Partial<AssistedDraft["values"]>, notes: string[] = [], resolved = true): AssistedDraft {
  return {
    values: {
      make: "Toyota", model: "Hilux", trim: "SRV", trims: ["SRV"], trim_strict: false, year_min: null, year_max: null,
      price_max: 35_000_000, price_target: null, currency: "ARS", km_max: null, km_target: null, transmission: "automatic",
      fuel: "", body_types: [], seller_type: "", location: "zona norte", locations: [], radius_km: null, ...values,
    },
    resolved,
    notes,
  };
}

const approximate = { label: "Rosario (zona aproximada)", lat: -32.95, lon: -60.65, approximate: true };
const room: SearchLimit = { capacity: 1, maxProfiles: 1, activeSearches: 0, upsell: null };

function decide(drafts: AssistedDraft[], { limit = room as SearchLimit | null, approximateLocation = approximate as typeof approximate | null } = {}) {
  const { values, notes } = draftToValues(drafts[0], base);
  return autoSaveValues({ drafts, values, notes, catalog, limit, approximateLocation });
}

describe("autoSaveValues", () => {
  it("saves a single resolved draft from the catalog with its zone", () => {
    const saved = decide([draft({})]);
    expect(saved).toMatchObject({ make: "Toyota", model: "Hilux", price_max: 35_000_000 });
    expect(saved?.location?.label).toMatch(/Zona Norte/i);
  });

  it("takes the approximate zone when the text names none, as a new form would", () => {
    const saved = decide([draft({ location: "" })]);
    expect(saved?.location).toEqual({ label: approximate.label, lat: approximate.lat, lon: approximate.lon, radius_km: AUTOSAVE_RADIUS_KM });
  });

  it("asks for the zone when there's none at all", () => {
    expect(decide([draft({ location: "" })], { approximateLocation: null })).toBeNull();
  });

  it("reviews several vehicles", () => {
    expect(decide([draft({}), draft({ make: "Volkswagen", model: "Gol Trend", trim: "", trims: [] })])).toBeNull();
  });

  it("reviews an unresolved draft or one off the catalog", () => {
    expect(decide([draft({}, [], false)])).toBeNull();
    expect(decide([draft({ make: "Tesla", model: "Model 3" })])).toBeNull();
    expect(decide([draft({ make: "", model: "", body_types: ["suv"], price_max: 20000 })])).toBeNull();
  });

  it("reviews a draft whose notes ask to choose something", () => {
    expect(decide([draft({}, ["Falta el modelo de Toyota: elegilo de la lista."])])).toBeNull();
    expect(decide([draft({}, ["No encontramos «Hiluxx» en el catálogo: elegí marca y modelo de la lista."])])).toBeNull();
    // draftToValues adds the zone's note.
    expect(decide([draft({ location: "Narnia" })])).toBeNull();
  });

  it("doesn't stop at informative notes", () => {
    expect(decide([draft({}, ["Interpretamos «goltrend» como Volkswagen Gol Trend.", "No dijiste la moneda: tomamos USD."])])).not.toBeNull();
  });

  it("needs room in the plan; without enforced limits there's always room", () => {
    expect(decide([draft({})], { limit: { ...room, capacity: 0, activeSearches: 1 } })).toBeNull();
    expect(decide([draft({})], { limit: null })).not.toBeNull();
  });
});

describe("helpers", () => {
  it("noteNeedsChoice spots choices regardless of accents and case", () => {
    expect(noteNeedsChoice("Elegí marca y modelo")).toBe(true);
    expect(noteNeedsChoice("La versión «X» no figura para el Hilux: elegila de la lista.")).toBe(true);
    expect(noteNeedsChoice("No reconocimos la zona «Narnia»: elegila de la lista.")).toBe(true);
    expect(noteNeedsChoice("Descartamos el año desde 1900: está fuera de rango.")).toBe(false);
  });

  it("inCatalog matches the catalog's spelling case-insensitively", () => {
    expect(inCatalog(catalog, "volkswagen", "gol trend")).toBe(true);
    expect(inCatalog(catalog, "Volkswagen", "Golf")).toBe(false);
    expect(inCatalog(catalog, "", "")).toBe(false);
  });

  it("sameProposal compares what would be saved", () => {
    const a = draftToValues(draft({}), base).values;
    expect(sameProposal(a, draftToValues(draft({}), base).values)).toBe(true);
    expect(sameProposal(a, draftToValues(draft({ price_max: 30_000_000 }), base).values)).toBe(false);
    expect(sameProposal(a, null)).toBe(false);
  });
});
