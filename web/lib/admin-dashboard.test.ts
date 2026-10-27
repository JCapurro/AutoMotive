import { describe, expect, it } from "vitest";

import { getDashboardPeriod, metricChange, metricRate } from "./admin-dashboard";

describe("admin dashboard complete Argentina days", () => {
  it("keeps the last completed day before Argentina midnight", () => {
    expect(getDashboardPeriod("7", new Date("2026-10-27T02:59:59.999Z"))).toEqual({
      days: 7, start: "2026-10-19T03:00:00.000Z", end: "2026-10-26T03:00:00.000Z",
      previousStart: "2026-10-12T03:00:00.000Z", asOf: "2026-10-27T02:59:59.999Z",
    });
  });
  it("moves both adjacent windows at midnight with no overlap", () => {
    const period = getDashboardPeriod("7", new Date("2026-10-27T03:00:00Z"));
    expect(period.end).toBe("2026-10-27T03:00:00.000Z");
    expect(period.start).toBe("2026-10-20T03:00:00.000Z");
    expect(period.previousStart).toBe("2026-10-13T03:00:00.000Z");
    expect(Date.parse(period.start) - Date.parse(period.previousStart)).toBe(Date.parse(period.end) - Date.parse(period.start));
  });
  it.each([undefined, "0", "8", "7days", "90.0", ["7", "90"]])("defaults an invalid period to 30: %s", (raw) => {
    expect(getDashboardPeriod(raw, new Date("2026-10-27T12:00:00Z")).days).toBe(30);
  });
  it.each(["7", "30", "90"])("accepts only the supported period %s", (raw) => {
    expect(getDashboardPeriod(raw).days).toBe(Number(raw));
  });
});

describe("honest metric ratios", () => {
  it("does not turn an empty cohort into a zero percent rate", () => {
    expect(metricRate(0, 0)).toBeNull();
    expect(metricRate(0, 4)).toBe(0);
    expect(metricRate(1, 4)).toBe(25);
  });
  it("does not invent a relative change from a zero baseline", () => {
    expect(metricChange(0, 0)).toBeNull();
    expect(metricChange(10, 0)).toBeNull();
    expect(metricChange(0, 10)).toBe(-100);
    expect(metricChange(15, 10)).toBe(50);
  });
});
