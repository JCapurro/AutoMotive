import { describe, expect, it } from "vitest";

import { ageLine, imageUrls, km, money, pct, vehicle } from "./format";

const NOW = new Date("2026-09-28T12:00:00Z");

describe("format", () => {
  it("uses Argentine thousands separators", () => {
    expect(money(10300, "USD")).toBe("USD 10.300");
    expect(money(12_500_000, "ARS")).toBe("ARS 12.500.000");
    expect(money(null, "USD")).toBe("sin precio");
    expect(km(112000)).toBe("112.000 km");
    expect(pct(6.09, 1)).toBe("6,1%");
  });

  it("says Publicado only when the source gives the date (§11, principio 5)", () => {
    expect(ageLine({ published_at: "2026-09-28T11:56:00Z", first_seen_at: "2026-09-28T11:58:00Z" }, NOW)).toBe(
      "Publicado hace 4 minutos",
    );
    expect(ageLine({ published_at: null, first_seen_at: "2026-09-28T09:00:00Z" }, NOW)).toBe("Detectado hace 3 horas");
    expect(ageLine({ published_at: "2026-09-20T12:00:00Z" }, NOW)).toBe("Publicado hace 8 días");
  });

  it("names the vehicle", () => {
    expect(vehicle({ make: "Ford", model: "Fiesta", trim: "Titanium", year: 2017 })).toBe("Ford Fiesta Titanium 2017");
    expect(vehicle({ title: "Fiesta impecable" })).toBe("Fiesta impecable");
  });

  it("keeps only http(s) images", () => {
    expect(imageUrls(["https://a/1.jpg", { url: "https://a/2.jpg" }, "javascript:alert(1)", 3])).toEqual([
      "https://a/1.jpg",
      "https://a/2.jpg",
    ]);
  });
});
