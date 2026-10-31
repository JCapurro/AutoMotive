import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { buyerJurisdiction, nearestLocality } from "./buyer-jurisdiction";
import { parseCostEstimator } from "./cost-estimator";

const ROOT = path.resolve(__dirname, "../..");
const GOLDEN = JSON.parse(readFileSync(path.join(ROOT, "worker/tests/fixtures/cost_estimator/golden.json"), "utf-8"));
const cfg = parseCostEstimator(GOLDEN.config);

// PAR-01: a port of worker/normalization/zone.py nearest_locality over the same file.
describe("nearestLocality", () => {
  it("reads the same localities as the worker", () => {
    expect(readFileSync(path.join(ROOT, "web/lib/data/argentina-locations.json"), "utf-8")).toBe(
      readFileSync(path.join(ROOT, "worker/normalization/data/ar_localities.json"), "utf-8"),
    );
  });

  it.each([
    // Measured with the worker's nearest_locality (distance before its round(…, 2)).
    [-34.5875, -58.42, "CABA - Comuna 14", "02", 1.5444653623264677],
    [-34.4708, -58.5286, "San Isidro", "06", 1.9721726336148526],
    [-34.9011, -56.1645, "Punta Indio", "06", 106.83416118889446],
    [-33.4489, -70.6693, "Las Cuevas", "50", 91.29786866399593],
  ])("(%d, %d) -> %s", (lat, lon, name, province, km) => {
    const near = nearestLocality(lat, lon);
    expect([near.city.name, near.city.provinceId]).toEqual([name, province]);
    expect(Math.abs(near.km - km)).toBeLessThan(1e-9);
  });

  it("caches by coordinates", () => {
    expect(nearestLocality(-32.9442, -60.6505)).toBe(nearestLocality(-32.9442, -60.6505));
  });
});

describe("buyerJurisdiction", () => {
  it("needs buyer_zone: without it there is no jurisdiction (no default distance)", () => {
    const rest = { ...GOLDEN.config };
    delete rest.buyer_zone;
    expect(buyerJurisdiction([{ lat: -34.5875, lon: -58.42, label: "Palermo, CABA" }], parseCostEstimator(rest))).toBeNull();
    expect(buyerJurisdiction([{ lat: -34.5875, lon: -58.42, label: "Palermo, CABA" }], cfg)).toEqual(["caba"]);
  });

  it("cuts by buyer_zone.max_locality_km", () => {
    const wide = parseCostEstimator({ ...GOLDEN.config, buyer_zone: { ...GOLDEN.config.buyer_zone, max_locality_km: 110 } });
    expect(buyerJurisdiction([{ lat: -34.9011, lon: -56.1645, label: "Montevideo" }], wide)).toEqual(["ba"]);
  });
});
