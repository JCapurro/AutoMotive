import { describe, expect, it } from "vitest";
import { DEFAULT_PLAN_LIMITS, freeResultQuota, resultsText, type PlanLimits } from "./pro";

const trial: PlanLimits = {
  plan: "free", enforced: true, state: "trial", limits: { max_visible_results: 50 },
  free_results_used: 50, free_results_limit: 50,
};

describe("the free trial's cumulative results", () => {
  it("offers 50 results in total", () => {
    expect(DEFAULT_PLAN_LIMITS.free.maxVisibleResults).toBe(50);
    expect(resultsText(DEFAULT_PLAN_LIMITS.free)).toBe("Hasta 50 resultados en total durante la prueba");
  });
  it("opens the offer at exactly 50, even in an empty or newly edited search", () => {
    expect(freeResultQuota(trial)).toEqual({ used: 50, limit: 50, reached: true, stockLeft: 0 });
    expect(freeResultQuota({ ...trial, free_results_used: 49 })?.reached).toBe(false);
  });
  it("admits less stock with the reserve on (app_config.trial_reserve), and the quota left with it off", () => {
    const early = { ...trial, free_results_used: 12, free_backfill_used: 10 };
    expect(freeResultQuota({ ...early, free_backfill_max: null })?.stockLeft).toBe(38);
    expect(freeResultQuota({ ...early, free_backfill_max: 30 })?.stockLeft).toBe(20);
    expect(freeResultQuota({ ...early, free_backfill_used: 31, free_backfill_max: 30 })?.stockLeft).toBe(0);
    expect(freeResultQuota({ ...trial, free_results_used: 45, free_backfill_used: 10, free_backfill_max: 30 })?.stockLeft).toBe(5);
  });
  it("says how much of the trial waits for new listings when the reserve is on", () => {
    expect(resultsText(DEFAULT_PLAN_LIMITS.free, 30)).toBe(
      "Hasta 50 resultados en total durante la prueba, hasta 30 ya publicados y el resto, autos nuevos");
    expect(resultsText(DEFAULT_PLAN_LIMITS.free, 50)).toBe("Hasta 50 resultados en total durante la prueba");
    expect(resultsText(DEFAULT_PLAN_LIMITS.pass, 30)).toBe(resultsText(DEFAULT_PLAN_LIMITS.pass));
  });
  it("never prompts paid accounts, admins, the unrestricted pilot, or unknown access", () => {
    expect(freeResultQuota({ ...trial, plan: "pass" })).toBeNull();
    expect(freeResultQuota({ ...trial, plan: "pro" })).toBeNull();
    expect(freeResultQuota({ ...trial, enforced: false })).toBeNull();
    expect(freeResultQuota({ ...trial, free_results_limit: null })).toBeNull();
    expect(freeResultQuota(null)).toBeNull();
  });
});
