import { describe, expect, it } from "vitest";

import { buildDemandDashboard, type DemandRow, type DemandRun, STALE_HOURS, vehicleOf } from "./admin-demand-data";

const now = new Date("2026-11-14T12:00:00Z");
const hoursAgo = (h: number) => new Date(now.getTime() - h * 3_600_000).toISOString();

const row = (id: number, over: Partial<DemandRow> = {}): DemandRow => ({
  search_profile_id: id, user_id: `u${id}`, make: "Ford", model: "Focus", zone_label: "Córdoba", result_count: 0,
  market: 10, market_in_zone: 2, relaxed_zone: 0, relaxed_price: 0, relaxed_trim: 0, relaxed_year: 0, cause: "none",
  computed_at: hoursAgo(8), ...over,
});
const run = (over: Partial<DemandRun> = {}): DemandRun => ({
  computed_at: hoursAgo(8), duration_ms: 6234, searches: 5, skipped_model_less: 2, max_results: 3, min_age_hours: 24,
  cap_enforced: true, hidden_by_level: { good: 40, high: 7 }, hidden_accounts: 12, ...over,
});

const rows = [
  row(1, { cause: "zone", relaxed_zone: 6 }),
  row(2, { cause: "zone", relaxed_zone: 3, result_count: 1, market: 14, market_in_zone: 4 }),
  row(3, { cause: "price", relaxed_price: 5, model: "Fiesta", zone_label: "CABA" }),
  row(4, { cause: "none", model: "Ka", zone_label: null, market: 0, market_in_zone: 0 }),
  row(5, { cause: "year", relaxed_year: 2, model: "Fiesta", zone_label: "CABA" }),
];

describe("buildDemandDashboard", () => {
  const d = buildDemandDashboard(rows, run(), now);

  it("counts each cause, biggest first, always the five of them", () => {
    expect(d.causes.map((c) => [c.key, c.value])).toEqual([["zone", 2], ["price", 1], ["trim", 0], ["year", 1], ["none", 1]]
      .sort((a, b) => (b[1] as number) - (a[1] as number)));
    expect(d.causes).toHaveLength(5);
    expect(d.total).toBe(5);
    expect(d.causes.reduce((n, c) => n + c.value, 0)).toBe(d.total);
  });

  it("groups by model and zone with the waiting searches and the listings", () => {
    const focus = d.modelZones.find((m) => m.model === "Ford Focus")!;
    expect(focus).toMatchObject({ zone: "Córdoba", searches: 2, listings: 14, listingsInZone: 4, cause: "zone" });
    expect(d.modelZones.find((m) => m.model === "Ford Ka")!.zone).toBe("Sin zona");
    expect(d.modelZones[0].searches).toBe(2);
  });

  it("lists the searches that would gain the most first, with what the cause adds", () => {
    expect(d.affected.map((a) => a.search_profile_id)).toEqual([1, 3, 5, 2, 4]);
    expect(d.affected[0].unlocks).toBe(6);
    expect(d.affected.find((a) => a.search_profile_id === 2)!.unlocks).toBe(2);   // 3 relaxed, 1 already shown
    expect(d.affected.find((a) => a.search_profile_id === 4)!.unlocks).toBe(0);
  });

  it("caps the tables", () => {
    const small = buildDemandDashboard(rows, run(), now, { models: 1, searches: 2 });
    expect(small.modelZones).toHaveLength(1);
    expect(small.affected).toHaveLength(2);
    expect(small.total).toBe(5);
  });

  it("reports the run and how stale it is", () => {
    expect(d).toMatchObject({ seconds: 6.2, skippedModelLess: 2, stale: false, threshold: { maxResults: 3, minAgeHours: 24 } });
    expect(buildDemandDashboard(rows, run({ computed_at: hoursAgo(STALE_HOURS + 1) }), now).stale).toBe(true);
  });

  it("shows what the cap hides by level, best level first", () => {
    expect(d.hidden).toEqual({ known: true, enforced: true, total: 47, accounts: 12, levels: [{ level: "high", value: 7 }, { level: "good", value: 40 }] });
    expect(buildDemandDashboard(rows, run({ cap_enforced: false, hidden_by_level: {} }), now).hidden).toMatchObject({ enforced: false, total: 0, levels: [] });
  });

  it("copes with a job that never ran", () => {
    const empty = buildDemandDashboard([], null, now);
    expect(empty).toMatchObject({ computedAt: null, stale: true, total: 0, seconds: null, threshold: null });
    expect(empty.hidden.known).toBe(false);
    expect(empty.modelZones).toEqual([]);
  });
});

describe("vehicleOf", () => {
  it("names the car", () => {
    expect(vehicleOf({ make: "Ford", model: "Focus" })).toBe("Ford Focus");
    expect(vehicleOf({ make: null, model: null })).toBe("Sin modelo");
  });
});
