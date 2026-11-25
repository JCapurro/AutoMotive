import { describe, expect, it } from "vitest";

import {
  byLevel, bySource, byWeek, criteriaLines, nextPending, overall, parseQueue, parseStats, progress, reviewerCounts, reviewerLabel, shareText, topReasons, verdictProblem,
  type ReviewItem, type StatsRow,
} from "./admin-match-audit";

const item = (id: number, verdict: ReviewItem["verdict"] = null): ReviewItem => ({
  id, matchId: id, level: "good", source: "kavak", score: 80, verdict, reasons: [], note: "", reviewer: verdict ? { id: "u1", kind: null, email: null } : null, listing: null, search: null,
});

describe("verdictProblem", () => {
  it("asks for a reason on fair and bad only", () => {
    expect(verdictProblem("good", [])).toBeNull();
    expect(verdictProblem("fair", [])).toMatch(/razón/);
    expect(verdictProblem("bad", ["zone"])).toBeNull();
  });
});

describe("parseQueue", () => {
  it("types good rows and drops malformed ones", () => {
    const rows = parseQueue([
      { id: 1, match_id: 9, level: "high", source: "v6", score: 91, verdict: "bad", reasons: ["zone", "nope"], note: "lejos",
        listing: { id: 5, title: "Ford Focus", year: 2015, price_usd: 9000, url: "https://x.test" },
        search: { id: 3, name: "mi", filters: { make: "Ford" }, radius_km: 30 } },
      { id: "x" }, null, { id: 2, level: "weird", verdict: "meh", listing: null, search: [] },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ id: 1, level: "high", verdict: "bad", reasons: ["zone"], note: "lejos" });
    expect(rows[0].listing?.priceUsd).toBe(9000);
    expect(rows[1]).toMatchObject({ level: "low", verdict: null, listing: null, search: null });
    expect(parseQueue("nope")).toEqual([]);
  });
});

describe("progress / nextPending", () => {
  const items = [item(1, "good"), item(2), item(3, "bad"), item(4)];
  it("counts reviewed and finds the first pending", () => {
    expect(progress(items)).toEqual({ done: 2, total: 4, firstPending: 1 });
    expect(progress([item(1, "good")]).firstPending).toBeNull();
  });
  it("moves to the next pending one, wrapping around", () => {
    expect(nextPending(items, 1)).toBe(3);
    expect(nextPending(items, 3)).toBe(1);
    expect(nextPending([item(1, "good")], 0)).toBeNull();
  });
});

describe("criteriaLines", () => {
  it("writes the search in plain words and skips empty fields", () => {
    const lines = criteriaLines({
      id: 1, name: "x", rawQuery: null, radiusKm: 30,
      filters: { make: "Ford", model: "Focus", trims: ["Titanium"], trim_strict: true, year_min: 2014, price_max: 12000, currency: "USD", location_label: "Rosario", km_max: 90000 },
    });
    const get = (l: string) => lines.find((x) => x.label === l)?.value;
    expect(get("Modelo")).toBe("Ford Focus");
    expect(get("Versión")).toBe("Titanium (estricta)");
    expect(get("Años")).toBe("2014 a …");
    expect(get("Zona")).toBe("Rosario a 30 km");
    expect(lines.find((x) => x.label === "Caja")).toBeUndefined();
    expect(criteriaLines(null)).toEqual([]);
  });
});

const rows: StatsRow[] = [
  { week: "2026-11-09", level: "high", source: "kavak", sampled: 10, good: 6, fair: 2, bad: 1 },
  { week: "2026-11-09", level: "good", source: "facebook", sampled: 10, good: 2, fair: 3, bad: 5 },
  { week: "2026-11-02", level: "high", source: "kavak", sampled: 5, good: 5, fair: 0, bad: 0 },
];

describe("statistics", () => {
  it("tallies a week with the sample size behind each share", () => {
    const [w1, w0] = byWeek(rows);
    expect(w1.key).toBe("2026-11-09");
    expect(w1).toMatchObject({ sampled: 20, reviewed: 19, good: 8 });
    expect(w1.goodShare).toBeCloseTo(8 / 19);
    expect(w1.goodOrFairShare).toBeCloseTo(13 / 19);
    expect(w1.smallSample).toBe(true);
    expect(w0.goodShare).toBe(1);
  });
  it("leaves the share null when nothing is reviewed", () => {
    const t = overall([{ week: "w", level: "low", source: "s", sampled: 4, good: 0, fair: 0, bad: 0 }]);
    expect(t.goodShare).toBeNull();
    expect(t.reviewed).toBe(0);
  });
  it("groups by level in fixed order and by source by sample size", () => {
    expect(byLevel(rows).map((t) => t.key)).toEqual(["high", "good"]);
    expect(bySource(rows).map((t) => t.key)).toEqual(["kavak", "facebook"]);
    expect(overall(rows).reviewed).toBe(24);
  });
  it("ranks reasons and can filter by week", () => {
    const reasons = parseStats({
      rows: [],
      reasons: [
        { week: "2026-11-09", reason: "version", verdict: "bad", n: 4 },
        { week: "2026-11-09", reason: "version", verdict: "fair", n: 1 },
        { week: "2026-11-02", reason: "zone", verdict: "bad", n: 9 },
        { week: "2026-11-09", reason: "color", verdict: "bad", n: 3 },
      ],
    }).reasons;
    expect(reasons).toHaveLength(3);
    expect(topReasons(reasons)[0]).toEqual({ reason: "zone", n: 9, fair: 0, bad: 9 });
    expect(topReasons(reasons, ["2026-11-09"])).toEqual([{ reason: "version", n: 5, fair: 1, bad: 4 }]);
  });
  it("parses stats defensively", () => {
    expect(parseStats(null)).toEqual({ rows: [], reasons: [] });
    expect(parseStats({ rows: [{ week: "w", level: "x", source: "s", sampled: 3 }] }).rows[0]).toMatchObject({ level: "low", good: 0, sampled: 3 });
  });
  it("prints a share with its sample", () => {
    expect(shareText(13, 25)).toBe("52 % (13 de 25)");
    expect(shareText(0, 0)).toBe("—");
  });
});

describe("who reviewed", () => {
  it("parses the reviewer only for reviewed rows, and only a declared kind", () => {
    const rows = parseQueue([
      { id: 1, level: "good", verdict: "good", reviewer_id: "u1", reviewer_kind: "person", reviewer_email: "a@x.test" },
      { id: 2, level: "good", verdict: "bad", reasons: ["zone"], reviewer_id: "u1", reviewer_kind: "automated" },
      { id: 3, level: "good", verdict: "fair", reasons: ["zone"], reviewer_id: "u1", reviewer_kind: "robot" },
      { id: 4, level: "good", verdict: null, reviewer_id: "u1", reviewer_kind: "person" },
    ]);
    expect(rows[0].reviewer).toEqual({ id: "u1", kind: "person", email: "a@x.test" });
    expect(rows[1].reviewer?.kind).toBe("automated");
    expect(rows[2].reviewer?.kind).toBeNull();
    expect(rows[3].reviewer).toBeNull();
  });

  it("says a person did it only when the reviewer declared it", () => {
    expect(reviewerLabel(null)).toBeNull();
    expect(reviewerLabel({ id: "u1", kind: "person", email: "a@x.test" }, "u2")).toEqual({ text: "Revisó una persona: a@x.test", person: true });
    expect(reviewerLabel({ id: "u1", kind: "person", email: null }, "u1")?.text).toBe("Revisó una persona: vos");
    expect(reviewerLabel({ id: "u1", kind: "automated", email: null })).toMatchObject({ person: false });
    expect(reviewerLabel({ id: "u1", kind: null, email: null })).toMatchObject({ person: null });
    expect(reviewerLabel({ id: "u1", kind: null, email: null })?.text).toMatch(/No se sabe/);
  });

  it("counts people, scripts and unknown", () => {
    const rev = (kind: "person" | "automated" | null): ReviewItem => ({ ...item(1, "good"), reviewer: { id: "u", kind, email: null } });
    expect(reviewerCounts([rev("person"), rev("person"), rev("automated"), rev(null), item(9)])).toEqual({ person: 2, automated: 1, unknown: 1 });
  });
});
