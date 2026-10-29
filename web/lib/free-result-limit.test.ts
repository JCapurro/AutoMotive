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
    expect(freeResultQuota(trial)).toEqual({ used: 50, limit: 50, reached: true });
    expect(freeResultQuota({ ...trial, free_results_used: 49 })?.reached).toBe(false);
  });
  it("never prompts paid accounts, admins, the unrestricted pilot, or unknown access", () => {
    expect(freeResultQuota({ ...trial, plan: "pass" })).toBeNull();
    expect(freeResultQuota({ ...trial, plan: "pro" })).toBeNull();
    expect(freeResultQuota({ ...trial, enforced: false })).toBeNull();
    expect(freeResultQuota({ ...trial, free_results_limit: null })).toBeNull();
    expect(freeResultQuota(null)).toBeNull();
  });
});
