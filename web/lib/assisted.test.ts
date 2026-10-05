import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { AssistedOutput, addedVehicle, draftTitle, draftToValues, placeFromText } from "./assisted";
import { cityFromText } from "./argentina-locations";
import { SearchInput, type SearchValues, toFilters } from "./search-form";

// What the worker writes to llm_jobs.output, kept current by
// worker/tests/test_llm_contract.py::test_web_example_output_is_current.
const WORKER_OUTPUT = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/llm/parse_search_output.json"), "utf-8"),
);

const BASE: SearchValues = SearchInput.parse({
  make: "x",
  model: "x",
  sources: ["mercadolibre", "kavak"],
  location: { label: "Mi casa", lat: -34.5, lon: -58.5, radius_km: 30 },
  notification_frequency: "daily",
  notify_min_level: "high",
});

describe("llm_jobs.output (sección 8.4)", () => {
  it("parses what the worker writes", () => {
    const out = AssistedOutput.parse(WORKER_OUTPUT);
    expect(out.drafts.map((d, i) => draftTitle(d, i))).toEqual([
      "Ford Fiesta Titanium",
      "Volkswagen Polo Highline",
      "Vehículo 3",
      "Volkswagen Vento Highline",
    ]);
  });

  it("rejects anything else", () => {
    expect(AssistedOutput.safeParse({ drafts: [{ values: { make: "Ford" } }] }).success).toBe(false);
    expect(AssistedOutput.safeParse(null).success).toBe(false);
  });
});

describe("draft → structured form", () => {
  const [fiesta, , tesla, vento] = AssistedOutput.parse(WORKER_OUTPUT).drafts;

  it("fills the vehicle and keeps the user's defaults for the rest", () => {
    const { values, notes } = draftToValues(fiesta, BASE);
    expect(notes).toEqual([]);
    expect(values).toMatchObject({
      name: "",
      make: "Ford",
      model: "Fiesta",
      trim: "Titanium",
      year_min: 2017,
      year_max: null,
      price_max: 12000,
      currency: "USD",
      sources: ["mercadolibre", "kavak"],
      notification_frequency: "daily",
      notify_min_level: "high",
      location: BASE.location,
    });
    // Valid input for saveSearch, and the filters the structured form would store.
    expect(toFilters(SearchInput.parse(values))).toMatchObject({ make: "Ford", model: "Fiesta", trims: ["Titanium"] });
  });

  it("maps the zone onto a place, with the radius the text gives", () => {
    const { values } = draftToValues(vento, BASE);
    expect(values.trim_strict).toBe(true);
    const city = cityFromText("Córdoba")!;
    expect(values.location).toEqual({ label: city.label, lat: city.lat, lon: city.lon, radius_km: 50 });
  });

  it("an unresolved vehicle arrives blank, with the worker's note", () => {
    const { values, notes } = draftToValues(tesla, BASE);
    expect([values.make, values.model]).toEqual(["", ""]);
    expect(values.year_min).toBe(2021);
    expect(notes[0]).toContain("Tesla Model 3");
  });

  it("an unknown zone keeps the default place and says so", () => {
    const draft = { ...fiesta, values: { ...fiesta.values, location: "Una zona que no existe" } };
    const { values, notes } = draftToValues(draft, BASE);
    expect(values.location).toEqual(BASE.location);
    expect(notes).toEqual(["No reconocimos la zona «Una zona que no existe»: elegila de la lista."]);
  });

  it("keeps multiple versions in a single editable proposal", () => {
    const draft = { ...fiesta, values: { ...fiesta.values, trims: ["Titanium", "SE"] } };
    const { values } = draftToValues(draft, BASE);
    expect(toFilters(SearchInput.parse(values)).trims).toEqual(["Titanium", "SE"]);
    expect(draftTitle(draft, 0)).toBe("Ford Fiesta Titanium / SE");
    expect(addedVehicle(values).trims).toEqual([]);
  });
});

describe("a vehicle the user adds on the review screen", () => {
  it("keeps the request's shared filters and blanks the vehicle", () => {
    const { values } = draftToValues(AssistedOutput.parse(WORKER_OUTPUT).drafts[0], BASE);
    const added = addedVehicle(values);
    expect(added).toMatchObject({ make: "", model: "", trim: "", trim_strict: false, name: "" });
    expect(added.year_min).toBe(values.year_min);
    expect(added.price_max).toBe(values.price_max);
    expect(added.location).toEqual(values.location);
    expect(added.sources).toEqual(values.sources);
  });
});

describe("placeFromText", () => {
  it.each([
    ["zona norte", "zona-norte"],
    ["Zona Norte de GBA", "zona-norte"],
    ["AMBA", "amba"],
    ["GBA", "amba"],
    ["Buenos Aires", "amba"],
    ["Capital Federal", "caba"],
    ["capital", "caba"],
    ["CABA", "caba"],
    ["Córdoba capital", "cordoba"],
    ["cordoba", "cordoba"],
    ["Mar del Plata", "mar-del-plata"],
    ["La Plata", "la-plata"],
    ["Tucumán", "tucuman"],
    ["bahía blanca", "bahia-blanca"],
  ])("%s → %s", (text, id) => {
    expect(placeFromText(text)?.id).toBe(id);
  });

  it("returns nothing for places it doesn't know", () => {
    expect(placeFromText("Una zona que no existe")).toBeUndefined();
    expect(placeFromText("")).toBeUndefined();
    expect(placeFromText(null)).toBeUndefined();
  });
});
