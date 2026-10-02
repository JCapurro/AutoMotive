import { describe, expect, it } from "vitest";

import { DEFAULT_PRO_OFFER, isPlacement, isWaitlistPlan, proOffer, visibleResults } from "./pro";

const free = (enforced: boolean) => ({ plan: "free" as const, enforced, limits: { max_visible_results: 50 } });

describe("visibleResults", () => {
  it("measures but doesn't cap while the pilot doesn't enforce", () => {
    expect(visibleResults(80, free(false))).toEqual({ cap: null, over: true });
  });
  it("caps when enforced", () => {
    expect(visibleResults(80, free(true))).toEqual({ cap: 50, over: true });
    expect(visibleResults(20, free(true))).toEqual({ cap: 50, over: false });
  });
  it("no limit for Pro or without config", () => {
    expect(visibleResults(500, { plan: "pro", enforced: true, limits: {} })).toEqual({ cap: null, over: false });
    expect(visibleResults(500, null)).toEqual({ cap: null, over: false });
  });
});

describe("proOffer", () => {
  it("reads app_config.pro_offer and falls back per plan", () => {
    expect(proOffer({ pro_monthly: { amount: 80000, currency: "ARS", days: 30 }, pass_30: { price_usd: "x" } })).toEqual({
      ...DEFAULT_PRO_OFFER,
      pro_monthly: { amount: 80000, currency: "ARS", days: 30 },
    });
    expect(proOffer(null)).toEqual(DEFAULT_PRO_OFFER);
    expect(proOffer({ pass_30: { price_usd: 15 }, pro_monthly: { amount: 49, currency: "USD", days: 30 } })).toEqual(DEFAULT_PRO_OFFER);
  });
});

describe("guards", () => {
  it("only known plans and placements", () => {
    expect(isWaitlistPlan("pass_90")).toBe(false);
    expect(isWaitlistPlan("pass_30")).toBe(true);
    expect(isWaitlistPlan("gold")).toBe(false);
    expect(isPlacement("dashboard")).toBe(true);
    expect(isPlacement("<script>")).toBe(false);
  });
});
