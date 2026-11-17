import { describe, expect, it } from "vitest";

import { roughDraft } from "@/lib/assisted-fallback";
import type { Catalog } from "@/lib/catalog";

const model = (name: string) => ({ model: name, trims: [], yearFrom: null, yearTo: null, transmissions: [], fuels: [], bodyTypes: [] });
const catalog: Catalog = [
  { make: "Ford", models: [model("Fiesta"), model("Focus"), model("Focus RS")] },
  { make: "Toyota", models: [model("Hilux")] },
];

describe("roughDraft", () => {
  it("reads the landing's example", () => {
    expect(roughDraft("Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km", catalog)).toEqual({
      make: "Ford", model: "Fiesta", year_min: 2016, year_max: 2018, price_max: 11500, currency: "USD", km_max: 150000, transmission: "manual",
    });
  });

  it("prefers the longest model and reads 'mil dólares' and 'en adelante'", () => {
    expect(roughDraft("focus rs 2017 en adelante, hasta 12 mil dólares", catalog)).toEqual({
      make: "Ford", model: "Focus RS", year_min: 2017, price_max: 12000, currency: "USD",
    });
  });

  it("turns a lone year into ±1, not an exact year", () => {
    expect(roughDraft("peugeot 307 2016 manual", catalog)).toMatchObject({ year_min: 2015, year_max: 2017 });
  });

  it("keeps explicit ranges, 'desde' and no year as they were", () => {
    expect(roughDraft("focus 2016 a 2018", catalog)).toMatchObject({ year_min: 2016, year_max: 2018 });
    expect(roughDraft("focus desde 2018", catalog)).toMatchObject({ year_min: 2018 });
    expect(roughDraft("focus desde 2018", catalog)).not.toHaveProperty("year_max");
    expect(roughDraft("focus manual", catalog)).not.toHaveProperty("year_min");
    expect(roughDraft("focus manual", catalog)).not.toHaveProperty("year_max");
  });

  it("reads pesos in millions and an automatic gearbox", () => {
    expect(roughDraft("Hilux automática hasta 35 millones en zona norte", catalog)).toEqual({
      make: "Toyota", model: "Hilux", price_max: 35_000_000, currency: "ARS", transmission: "automatic",
    });
  });

  it("reads AMBA as the city and its suburbs", () => {
    expect(roughDraft("Ford Focus con caja manual en el AMBA", catalog).location).toEqual({
      label: "Ciudad de Buenos Aires, CABA", lat: -34.6037, lon: -58.3816, radius_km: 40,
    });
  });

  it("keeps just the make when no model is named, and nothing from noise", () => {
    expect(roughDraft("un Ford", catalog)).toEqual({ make: "Ford" });
    expect(roughDraft("algo barato", catalog)).toEqual({});
  });
});
