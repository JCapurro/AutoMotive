import { describe, expect, it } from "vitest";

import { type AssistedDraft, type SearchLimit, draftToValues, isNationalZone } from "@/lib/assisted";
import { AUTOSAVE_RADIUS_KM, autoSaveValues, inCatalog, noteNeedsChoice, sameProposal, zoneFromText } from "@/lib/assisted-autosave";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";

const catalog: Catalog = [
  { make: "Toyota", models: [{ model: "Hilux", trims: ["SRV"], yearFrom: 2005, yearTo: null, transmissions: [], fuels: [], bodyTypes: ["pickup"] }] },
  { make: "Volkswagen", models: [{ model: "Gol Trend", trims: [], yearFrom: 2008, yearTo: 2023, transmissions: [], fuels: [], bodyTypes: [] }] },
];

const base: SearchValues = {
  name: "", make: "", model: "", trim: "", trims: [], trim_strict: false, year_min: null, year_max: null,
  price_max: null, currency: "USD", km_max: null, transmission: "", fuel: "", body_types: [], sources: ["mercadolibre"],
  location: null, km_target: null, price_target: null, seller_type: "", notification_frequency: "immediate",
  notify_min_level: "good", opportunity_threshold_pct: null,
};

function draft(values: Partial<AssistedDraft["values"]>, notes: string[] = [], resolved = true): AssistedDraft {
  return {
    values: {
      make: "Toyota", model: "Hilux", trim: "SRV", trims: ["SRV"], trim_strict: false, year_min: null, year_max: null,
      price_max: 35_000_000, price_target: null, currency: "ARS", km_max: null, km_target: null, transmission: "automatic",
      fuel: "", body_types: [], seller_type: "", location: "zona norte", radius_km: null, ...values,
    },
    resolved,
    notes,
  };
}

const approximate = { label: "Rosario (zona aproximada)", lat: -32.95, lon: -60.65, approximate: true };
const room: SearchLimit = { capacity: 1, maxProfiles: 1, activeSearches: 0, upsell: null };

function decide(drafts: AssistedDraft[], { limit = room as SearchLimit | null, approximateLocation = approximate as typeof approximate | null } = {}) {
  const { values, notes } = draftToValues(drafts[0], base);
  return autoSaveValues({ drafts, values, notes, catalog, limit, approximateLocation })?.values ?? null;
}

function decideWithNotes(drafts: AssistedDraft[]) {
  const { values, notes } = draftToValues(drafts[0], base);
  return autoSaveValues({ drafts, values, notes, catalog, limit: room, approximateLocation: approximate });
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
  });

  // Requests from the pilot that stayed on the review screen (2026-10).
  it("saves the whole country for «cualquier lado de Argentina», with a note that asks nothing", () => {
    const saved = decideWithNotes([draft({ location: "cualquier lado de argentina" })]);
    expect(saved?.values.location).toBeNull();
    expect(saved?.notes.some((n) => /todo el país/.test(n))).toBe(true);
    expect(saved?.notes.some(noteNeedsChoice)).toBe(false);
  });

  it("takes the first zone it knows of «santa fe o Buenos Aires» and says so", () => {
    const saved = decideWithNotes([draft({ location: "santa fe o Buenos Aires" })]);
    expect(saved?.values.location?.label).toMatch(/Santa Fe/);
    expect(saved?.notes.find((n) => n.startsWith("Buscamos en"))).toMatch(/Buenos Aires/);
  });

  it("searches the whole country for a zone it doesn't know instead of stopping", () => {
    const saved = decideWithNotes([draft({ location: "Narnia" })]);
    expect(saved?.values.location).toBeNull();
    expect(saved?.notes).toEqual([expect.stringMatching(/«Narnia» no está en nuestra lista/)]);
  });

  it("still reviews an unknown zone when something else needs a choice", () => {
    expect(decide([draft({ location: "Narnia" }, ["Falta el modelo de Toyota: elegilo de la lista."])])).toBeNull();
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

  it("isNationalZone reads the ways people say «anywhere»", () => {
    for (const t of ["Argentina", "todo el país", "Cualquier lado", "en cualquier parte", "todo argentina"]) expect(isNationalZone(t)).toBe(true);
    for (const t of ["Rosario", "zona norte", "Costa Atlántica"]) expect(isNationalZone(t)).toBe(false);
  });

  it("draftToValues never sends «Argentina» to the town in Santiago del Estero", () => {
    expect(draftToValues(draft({ location: "Argentina" }), base).values.location).toBeNull();
    expect(draftToValues(draft({ location: "Rosario, Argentina" }), base).values.location?.label).toMatch(/Rosario/);
  });

  it("zoneFromText prefers a place over the country it's in", () => {
    expect(zoneFromText("Rosario, Argentina").location?.label).toMatch(/Rosario/);
    expect(zoneFromText("Argentina").location).toBeNull();
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
