import { describe, expect, it } from "vitest";

import { ageLine, ceilTo, floorTo, formatArsRange, formatRange, formatUsdRange, imageUrls, isoDayMonth, km, money, pct, thousands, vehicle } from "./format";

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
    expect(ageLine({}, NOW)).toBe("Fecha de publicación no informada");
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

// PAR-01: the same outward rounding and thousands as worker/intelligence/cost_estimator.py.
describe("cost ranges", () => {
  it("rounds outward with the one-cent margin", () => {
    expect(floorTo(321999.99999999994, 100)).toBe(322000);
    expect(ceilTo(506000.00000000006, 100)).toBe(506000);
    expect(floorTo(321999.98, 100)).toBe(321900);
    expect(ceilTo(506000.02, 100)).toBe(506100);
    expect(floorTo(21188950, 1000)).toBe(21188000);
    expect(ceilTo(21517532.5, 1000)).toBe(21518000);
  });

  it("groups thousands by hand", () => {
    expect([0, 950, 16290, 110619000].map(thousands)).toEqual(["0", "950", "16.290", "110.619.000"]);
  });

  it("prints ranges and collapses equal ends", () => {
    expect(formatRange(16290, 16560, "USD")).toBe("USD 16.290 – 16.560");
    expect(formatRange(20208000, 20208000, "ARS")).toBe("ARS 20.208.000");
    expect(formatArsRange(21188950, 21517532.5)).toBe("ARS 21.188.000 – 21.518.000");
    expect(formatUsdRange(21188950 / 1300, 21517532.5 / 1300)).toBe("USD 16.290 – 16.560");
  });

  it("reads an as_of as dd/mm without a time zone", () => {
    expect(isoDayMonth("2026-10-30")).toBe("30/10");
    expect(isoDayMonth("2026-01-05")).toBe("05/01");
  });
});
