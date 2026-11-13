import { describe, expect, it } from "vitest";

import { COLOR, COLOR_CODES, colorName, colorsText } from "@/lib/copy";
import { ANY_COLOR_VALUE, SearchInput, checkedColors, fromProfile, toFilters, toggleColor } from "@/lib/search-form";
import type { SearchProfile } from "@/lib/types";

// docs/PLAN_FILTRO_COLOR.md §8: «Cualquier color» plus the 8 colors, in both modes, stored as filters.colors.
describe("color codes and labels", () => {
  it("keeps the contract's codes, labels and order", () => {
    expect(COLOR_CODES).toEqual(["blanco", "negro", "gris", "azul", "rojo", "verde", "beige", "otro"]);
    expect(COLOR_CODES.map((c) => COLOR[c])).toEqual(
      ["Blanco", "Negro", "Gris o plata", "Azul o celeste", "Rojo o bordó", "Verde", "Beige o marrón", "Otro color"]);
    expect(COLOR_CODES.map(colorName)).toEqual(["blanco", "negro", "gris", "azul", "rojo", "verde", "beige", "otro"]);
  });
  it("writes a list in the canonical order, unknown codes dropped", () => {
    expect(colorsText(["gris", "blanco"])).toBe("blanco o gris");
    expect(colorsText(["rojo", "blanco", "gris", "violeta"])).toBe("blanco, gris o rojo");
    expect(colorsText([])).toBe("");
    expect(colorsText(null)).toBe("");
  });
});

describe("the color checkboxes", () => {
  it("starts on «Cualquier color»", () => {
    expect(checkedColors([])).toEqual([ANY_COLOR_VALUE]);
    expect(checkedColors(["gris"])).toEqual(["gris"]);
  });
  it("checking a color unchecks «Cualquier color»; unchecking them all goes back to it", () => {
    let colors = toggleColor([], "gris", true);
    expect(colors).toEqual(["gris"]);
    expect(checkedColors(colors)).not.toContain(ANY_COLOR_VALUE);
    colors = toggleColor(colors, "blanco", true);
    expect(colors).toEqual(["blanco", "gris"]);
    colors = toggleColor(colors, "gris", false);
    colors = toggleColor(colors, "blanco", false);
    expect(colors).toEqual([]);
    expect(checkedColors(colors)).toEqual([ANY_COLOR_VALUE]);
  });
  it("checking «Cualquier color» clears the colors; unchecking it does nothing", () => {
    expect(toggleColor(["rojo", "verde"], ANY_COLOR_VALUE, true)).toEqual([]);
    expect(toggleColor([], ANY_COLOR_VALUE, false)).toEqual([]);
    expect(toggleColor(["rojo"], "violeta", true)).toEqual(["rojo"]);
  });
});

describe("filters.colors", () => {
  const byModel = { make: "Volkswagen", model: "Gol", sources: ["mercadolibre"] };
  const byBody = { body_types: ["suv" as const], price_max: 20000, sources: ["mercadolibre"] };

  it("stores the codes in both modes, once each and in order", () => {
    expect(toFilters(SearchInput.parse({ ...byModel, colors: ["gris", "blanco", "gris"] })).colors).toEqual(["blanco", "gris"]);
    expect(toFilters(SearchInput.parse({ ...byBody, colors: ["blanco"] }))).toMatchObject({ body_types: ["suv"], colors: ["blanco"] });
  });
  it("omits it when empty", () => {
    expect(toFilters(SearchInput.parse(byModel))).not.toHaveProperty("colors");
    expect(toFilters(SearchInput.parse({ ...byModel, colors: [] }))).not.toHaveProperty("colors");
  });
  it("refuses an unknown code or a value that isn't a list", () => {
    const bad = SearchInput.safeParse({ ...byModel, colors: ["violeta"] });
    expect(bad.success).toBe(false);
    if (!bad.success) expect(bad.error.issues[0].path[0]).toBe("colors");
    expect(SearchInput.safeParse({ ...byModel, colors: "blanco" }).success).toBe(false);
  });
  it("reads a stored search back, dropping unknown codes", () => {
    const profile = {
      name: "Gol", filters: { make: "Volkswagen", model: "Gol", colors: ["gris", "violeta", "blanco"] }, preferences: {},
      origin_lat: null, origin_lon: null, radius_km: null, notification_frequency: "immediate", notify_min_level: "good",
      opportunity_threshold_pct: null, opportunity_threshold_usd: null,
    } as unknown as SearchProfile;
    expect(fromProfile(profile, ["mercadolibre"]).colors).toEqual(["blanco", "gris"]);
    expect(fromProfile({ ...profile, filters: { make: "Volkswagen", model: "Gol" } } as SearchProfile, []).colors).toEqual([]);
  });
});
