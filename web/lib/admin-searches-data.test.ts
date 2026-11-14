import { describe, expect, it } from "vitest";

import { buildSearchesDashboard, hasNoResults, type SearchRow, vehicleOf } from "./admin-searches-data";

const now = new Date("2026-11-14T12:00:00Z");
const daysAgo = (d: number) => new Date(now.getTime() - d * 86_400_000).toISOString();
const search = (id: number, filters: unknown, extra: Partial<SearchRow> = {}): SearchRow => ({
  id, user_id: `u${id % 2}`, email: null, name: `s${id}`, filters, enabled: true, notification_frequency: "immediate",
  notify_min_level: "good", channels: ["email"], bootstrapped_at: daysAgo(5), rematch_requested_at: null,
  created_at: daysAgo(6), matches: 10, high_matches: 1, alerts: 2, radius_km: 30, ...extra,
});

const searches = [
  search(1, { make: "Ford", model: "Focus", currency: "USD", price_max: 9000, year_min: 2012, location_label: "CABA" }),
  search(2, { make: "Ford", model: "Focus", currency: "USD", price_max: 15000, location_label: "CABA" }, { matches: 0 }),
  search(3, { body_types: ["suv"], currency: "ARS", price_max: 18_000_000 }, { radius_km: null, notification_frequency: "daily" }),
  search(4, { make: "Toyota", model: "Corolla" }, { enabled: false, created_at: daysAgo(60), matches: 0 }),
  search(5, { make: "VW", model: "Gol" }, { bootstrapped_at: null, matches: 0 }),
];
const notifications = [
  { search_profile_id: 1, opened_at: daysAgo(1), clicked_at: daysAgo(1) },
  { search_profile_id: 1, opened_at: null, clicked_at: null },
  { search_profile_id: 3, opened_at: daysAgo(1), clicked_at: null },
  { search_profile_id: null, opened_at: null, clicked_at: null },
];

describe("buildSearchesDashboard", () => {
  const d = buildSearchesDashboard(searches, notifications, now, 30);

  it("summarizes the period", () => {
    expect(d.kpis).toMatchObject({ total: 5, active: 4, created: 4, noResults: 1, pending: 1, sent: 3, openRate: 67, clickRate: 33 });
  });

  it("ranks the cars, with the ones that find nothing", () => {
    expect(d.topModels[0]).toEqual({ label: "Ford Focus", value: 2, note: "1 sin resultados" });
    expect(d.topModels.map((m) => m.label).some((l) => l.startsWith("Sin modelo:"))).toBe(true);
  });

  it("buckets budget, radius and zones", () => {
    expect(d.usd).toEqual([{ label: "USD 8.000–12.000", value: 1 }, { label: "USD 12.000–16.000", value: 1 }]);
    expect(d.ars).toEqual([{ label: "$15–20 M", value: 1 }]);
    expect(d.noPrice).toBe(1);
    expect(d.radius).toEqual([{ label: "Hasta 30 km", value: 3 }, { label: "Todo el país", value: 1 }]);
    expect(d.zones[0]).toEqual({ label: "CABA", value: 2 });
  });

  it("joins each search's alerts", () => {
    expect(d.all.find((s) => s.id === 1)).toMatchObject({ sent: 2, opened: 1, clicked: 1, noResults: false });
  });
});

it("finds no results only in active searches matched over a day ago", () => {
  expect(hasNoResults(search(9, {}, { matches: 0 }), now.getTime())).toBe(true);
  expect(hasNoResults(search(9, {}, { matches: 0, bootstrapped_at: daysAgo(0.5) }), now.getTime())).toBe(false);
  expect(hasNoResults(search(9, {}, { matches: 0, enabled: false }), now.getTime())).toBe(false);
});

it("names the car of a search", () => {
  expect(vehicleOf({ make: "Ford" })).toBe("Ford (cualquier modelo)");
  expect(vehicleOf({})).toBe("Sin vehículo");
});
