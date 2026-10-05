import { describe, expect, it } from "vitest";
import { CITIES, PROVINCES, citiesInProvince, cityByLocation, cityFromText } from "./argentina-locations";

describe("province and city selectors", () => {
  it("includes every province and associates each city with a valid province", () => {
    expect(PROVINCES).toHaveLength(24);
    expect(CITIES.length).toBeGreaterThan(3900);
    const provinces = new Set(PROVINCES.map((p) => p.id));
    expect(CITIES.every((c) => provinces.has(c.provinceId) && Number.isFinite(c.lat) && Number.isFinite(c.lon))).toBe(true);
  });

  it("shows CABA as a single city, without census communes", () => {
    expect(citiesInProvince("02").map((c) => c.city)).toEqual(["Ciudad de Buenos Aires"]);
  });

  it("filters cities by province and restores the saved city", () => {
    const cities = citiesInProvince("06");
    expect(cities.every((c) => c.provinceId === "06")).toBe(true);
    const city = cities.find((c) => c.city === "La Plata")!;
    expect(cityByLocation(city)?.id).toBe(city.id);
    expect(cityByLocation({ ...city, label: "Mi ubicación actual" })).toBeUndefined();
  });

  it("recognizes cities outside the former short list", () => {
    expect(cityFromText("Ushuaia")?.provinceId).toBe("94");
    expect(cityFromText("San Pedro Buenos Aires")?.provinceId).toBe("06");
  });
});
