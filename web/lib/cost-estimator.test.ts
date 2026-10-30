import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { buyerJurisdiction } from "./buyer-jurisdiction";
import {
  BLOCKS,
  buildCostInput,
  costEstimatorProblem,
  costEstimatorReview,
  costHeadline,
  costLine,
  estimateCost,
  missingSuffix,
  parseCostEstimator,
  searchZones,
  termAmount,
} from "./cost-estimator";

// PAR-01: the golden vectors shared with worker/tests/test_cost_estimator.py.
type Patch = { path: (string | number)[]; value?: unknown; delete?: boolean }[];
const GOLDEN = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/cost_estimator/golden.json"), "utf-8"),
) as {
  config: Record<string, unknown>;
  cases: { name: string; input: { listing: never; jurisdiction: never; seller: never; fx_latest: never; config_patch?: Patch }; expect: Record<string, unknown> | null }[];
  jurisdiction_cases: { name: string; zones: never; expect: string[] | null }[];
  input_cases: { name: string; row: never; search: never; fx_latest: never; today: string; expect: Record<string, unknown> | null }[];
  config_cases: { name: string; config_patch: Patch; expect_null: string[] | null }[];
};
const TOL = 0.01;

function patched(raw: unknown, patch: Patch = []): unknown {
  const out = structuredClone(raw) as Record<string | number, unknown>;
  for (const op of patch) {
    const parents = op.path.slice(0, -1), last = op.path[op.path.length - 1];
    let node = out as Record<string | number, unknown>;
    for (const key of parents) node = node[key] as Record<string | number, unknown>;
    if (op.delete) delete node[last];
    else node[last] = op.value;
  }
  return out;
}
const cfgFor = (patch: Patch = []) => parseCostEstimator(patched(GOLDEN.config, patch));

/** Compares the keys an expectation names: numbers within TOL, the rest exactly. */
function expectMatches(actual: unknown, expected: unknown, where = "") {
  if (expected && typeof expected === "object" && !Array.isArray(expected)) {
    expect(actual && typeof actual === "object", where).toBe(true);
    for (const [key, value] of Object.entries(expected)) expectMatches((actual as Record<string, unknown>)[key], value, `${where}.${key}`);
  } else if (Array.isArray(expected)) {
    expect(Array.isArray(actual), where).toBe(true);
    expect((actual as unknown[]).length, `${where}: ${JSON.stringify(actual)}`).toBe(expected.length);
    expected.forEach((e, i) => expectMatches((actual as unknown[])[i], e, `${where}[${i}]`));
  } else if (typeof expected === "number") {
    expect(typeof actual, where).toBe("number");
    expect(Math.abs((actual as number) - expected), `${where}: ${actual} != ${expected}`).toBeLessThanOrEqual(TOL);
  } else {
    expect(actual, where).toEqual(expected);
  }
}

describe("golden: calculator", () => {
  it.each(GOLDEN.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const i = c.input;
    const est = estimateCost(i.listing, i.jurisdiction, i.seller, i.fx_latest, cfgFor(i.config_patch));
    if (c.expect === null) {
      expect(est).toBeNull();
      return;
    }
    expect(est).not.toBeNull();
    const { line, details, missing, terms, extras, ...rest } = c.expect as Record<string, unknown>;
    expectMatches(est, rest);
    expectMatches(est!.terms.map(({ code, min, max }) => ({ code, min, max })), terms, "terms");
    expectMatches(est!.extras.map(({ code, min, max }) => ({ code, min, max })), extras, "extras");
    expect(est!.missing).toEqual(missing);
    expect(costLine(est!)).toBe(line);
    const lines = Object.fromEntries(
      [...est!.terms, ...est!.extras].filter((t) => t.min != null).map((t) => [t.code, termAmount(t as { min: number; max: number })]),
    );
    for (const [code, text] of Object.entries((details ?? {}) as Record<string, string>)) expect(lines[code], code).toBe(text);
  });
});

describe("golden: jurisdiction", () => {
  const cfg = cfgFor();
  it.each(GOLDEN.jurisdiction_cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(buyerJurisdiction(c.zones, cfg)).toEqual(c.expect);
  });
});

describe("golden: input", () => {
  const cfg = cfgFor();
  it.each(GOLDEN.input_cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const zones = searchZones(c.search);
    const built = buildCostInput(c.row, zones, c.fx_latest, cfg, c.today, buyerJurisdiction);
    if (c.expect === null) {
      expect(built).toBeNull();
      return;
    }
    const { p_ars, zones: expectedZones, ...rest } = c.expect;
    if (expectedZones !== undefined) expect(zones).toEqual(expectedZones);
    expectMatches(built, rest);
    if (p_ars !== undefined) {
      const est = estimateCost(built!.listing, built!.jurisdiction, built!.seller, built!.fx_latest, cfg);
      expectMatches(est!.p_ars, p_ars, "p_ars");
    }
  });
});

describe("golden: tolerant parser", () => {
  it.each(GOLDEN.config_cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const cfg = cfgFor(c.config_patch);
    if (c.expect_null === null) {
      expect(cfg).toBeNull();
      return;
    }
    const nulls = Object.entries(cfg!.blocks).filter(([, v]) => v === null).map(([k]) => k).sort();
    expect(nulls).toEqual([...c.expect_null].sort());
    expect(Object.keys(cfg!.blocks).sort()).toEqual([...BLOCKS].sort());
  });

  it("never throws on garbage", () => {
    for (const raw of [null, [], "x", 3, { as_of: "2026-10-30", dnrpa: "x", patente: [], fixed_ars: 7, stamp_tax_pct: null }]) {
      const cfg = parseCostEstimator(raw);
      if (cfg) expect(Object.values(cfg.blocks).every((v) => v === null)).toBe(true);
    }
  });

  it("fills no default: with only the root as_of every term is missing", () => {
    const listing = { price: 20000000, currency: "ARS" as const, fx_rate: 1300, cash: false, year: 2017, body_type: "sedan" };
    const est = estimateCost(listing, ["caba"], "private", null, parseCostEstimator({ as_of: "2026-10-30" }));
    expect(est!.terms).toEqual([]);
    expect(est!.extras).toEqual([]);
    expect(est!.missing.map((m) => m.code)).toEqual(["arancel", "sellos", "formularios", "patente"]);
    expect(est!.total_ars).toEqual({ min: 20000000, max: 20000000 });
  });
});

describe("costEstimatorProblem (the /admin validator)", () => {
  it("accepts the approved config", () => {
    expect(costEstimatorProblem(GOLDEN.config)).toBeNull();
  });

  it.each([
    [[{ path: ["patente", "ba", "brackets", 1, "from"], value: 0 }], 'cost_estimator.patente.ba.brackets: los "from" deben crecer.'],
    [[{ path: ["patente", "caba", "brackets", 0, "from"], value: 5 }], 'cost_estimator.patente.caba.brackets: el primer "from" tiene que ser 0.'],
    [[{ path: ["dnrpa", "pct"], value: { min: 2, max: 1 } }], "cost_estimator.dnrpa.pct: min tiene que ser menor o igual que max."],
    [[{ path: ["vf_from_price_k", "max"], value: 1.2 }], "cost_estimator.vf_from_price_k.max: no puede superar 1 (base = precio)."],
    [[{ path: ["patente", "rest", "max_pct_bands", 2, "vf_upto"], value: 1 }], 'cost_estimator.patente.rest.max_pct_bands: el último "vf_upto" tiene que ser null.'],
    [[{ path: ["mrpa_ars", "as_of"], value: "2026-02-30" }], "cost_estimator.mrpa_ars.as_of: as_of tiene que ser una fecha AAAA-MM-DD."],
    [[{ path: ["fx", "source"], value: " " }], "cost_estimator.fx.source: source no puede estar vacío."],
    [[{ path: ["stamp_tax_pct", "caba", "private", "max"], value: 300 }], "cost_estimator.stamp_tax_pct.caba.private.max: un porcentaje no puede superar 100."],
    [[{ path: ["review", "months"], value: [12, 13] }], "cost_estimator.review.months.1: los meses van de 1 a 12."],
    [[{ path: ["patente", "values_year"], value: "2026" }], "cost_estimator.patente.values_year: tiene que ser un año entero."],
    [[{ path: ["gestoria"], delete: true }], "cost_estimator.gestoria: falta el bloque."],
    [[{ path: ["as_of"], delete: true }], "cost_estimator.as_of: tiene que ser una fecha AAAA-MM-DD (la de tu última revisión)."],
    [[{ path: ["domain_report", "in_total"], value: true }], "cost_estimator.domain_report.in_total: in_total tiene que ser false: va fuera del total."],
  ] as [Patch, string][])("rejects %j", (patch, message) => {
    expect(costEstimatorProblem(patched(GOLDEN.config, patch))).toBe(message);
  });

  it("rejects what the tolerant parser drops, block by block", () => {
    for (const c of GOLDEN.config_cases) {
      const problem = costEstimatorProblem(patched(GOLDEN.config, c.config_patch));
      if (c.expect_null === null) expect(problem, c.name).toMatch(/^cost_estimator\.as_of: /);
      else if (c.expect_null.length === 0) expect(problem, c.name).toBeNull();
      else expect(problem, c.name).toMatch(new RegExp(`^cost_estimator\\.${c.expect_null[0].replace(/\./g, "\\.")}[.:]`));
    }
  });
});

describe("costEstimatorReview", () => {
  const cfg = (asOf: string, review: Record<string, unknown> = {}) =>
    parseCostEstimator(patched(GOLDEN.config, [{ path: ["as_of"], value: asOf }, ...Object.entries(review).map(([k, v]) => ({ path: ["review", k], value: v }))]));

  it("is stale after review.max_age_days", () => {
    expect(costEstimatorReview(cfg("2026-06-01"), "2026-09-30")).toBe("stale"); // 121 days
    expect(costEstimatorReview(cfg("2026-06-02"), "2026-09-30")).toBeNull(); // 120 days
    expect(costEstimatorReview(cfg("2026-06-23"), "2026-10-21")).toBeNull(); // 120 days, October
  });

  it("is due in the review months until reviewed, across the year end", () => {
    expect(costEstimatorReview(cfg("2026-10-30"), "2026-12-20")).toBe("due");
    expect(costEstimatorReview(cfg("2026-12-05"), "2026-12-20")).toBeNull();
    expect(costEstimatorReview(cfg("2026-12-05"), "2027-01-15")).toBeNull();
    expect(costEstimatorReview(cfg("2026-11-30"), "2027-01-02")).toBe("due");
    expect(costEstimatorReview(cfg("2026-10-30"), "2026-11-20")).toBeNull();
  });

  it("stale wins over due", () => {
    expect(costEstimatorReview(cfg("2026-08-01"), "2026-12-20")).toBe("stale");
  });

  it("is missing without a review block or a config", () => {
    expect(costEstimatorReview(parseCostEstimator(patched(GOLDEN.config, [{ path: ["review"], delete: true }])), "2026-11-01")).toBe("missing");
    expect(costEstimatorReview(null, "2026-11-01")).toBe("missing");
    expect(costEstimatorReview(cfg("2026-10-30", { months: [0] }), "2026-11-01")).toBe("missing");
  });
});

describe("header", () => {
  it.each([
    [[], ""],
    [["fx"], ""],
    [["patente"], " (sin patente)"],
    [["patente", "sellos"], " (sin sellos ni patente)"],
    [["formularios"], " (sin formularios)"],
    [["arancel"], " (sin arancel)"],
    [["sellos", "formularios", "patente"], " (sin sellos, formularios ni patente)"],
    [["patente", "arancel", "sellos", "fx"], " (sin arancel, sellos ni patente)"],
    [["arancel", "sellos", "formularios", "patente"], " (sin arancel, sellos, formularios ni patente)"],
    [["arancel", "sellos"], " (sin arancel ni sellos)"],
  ])("missingSuffix(%j) = %j", (codes, text) => {
    expect(missingSuffix(codes)).toBe(text);
  });

  it("is built from rounded totals, like the email", () => {
    expect(costHeadline({ min: 21188000, max: 21518000 }, { min: 16290, max: 16560 }, [])).toBe(
      "Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)",
    );
    expect(costHeadline({ min: 21188000, max: 21518000 }, null, ["fx", "patente"])).toBe(
      "Costo total estimado (sin patente): ARS 21.188.000 – 21.518.000 (sin dólar del día)",
    );
    expect(costHeadline(null, null, ["fx"])).toBe("Costo total estimado: sin dólar del día, no se puede estimar");
  });
});
