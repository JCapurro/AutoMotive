import { describe, expect, it } from "vitest";

import {
  planFeatures,
  accountAlertCap, alertCapsText, bannerCopy, canAcquirePlan, DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER, extendsPass, includesImmediateAlerts,
  isPlacement, isWaitlistPlan, modelLessText, planLimits, proOffer, searchCapacity, visibleResults,
} from "./pro";

const free = (enforced: boolean) => ({ plan: "free" as const, enforced, limits: { max_visible_results: 50 } });

describe("canAcquirePlan", () => {
  it.each(["pass", "pro"] as const)("hides acquisition for active %s access, including manual grants", (plan) => {
    expect(canAcquirePlan({ plan, enforced: true, active: true, state: "paid", limits: {} })).toBe(false);
    expect(canAcquirePlan({ plan, enforced: false, active: true, state: "pilot", limits: {} })).toBe(false);
  });
  it("knows a running Particular can be extended (2.4), from Ajustes and Planes", () => {
    expect(extendsPass({ plan: "pass", enforced: true, active: true, state: "paid", limits: {} })).toBe(true);
    expect(extendsPass({ plan: "pro", enforced: true, active: true, state: "paid", limits: {} })).toBe(false);
    expect(extendsPass(null)).toBe(false);
  });
  it.each(["pass", "pro"] as const)("allows acquisition after %s access expires", (plan) => {
    expect(canAcquirePlan({ plan, enforced: true, active: false, state: "expired", limits: {} })).toBe(true);
  });
  it.each(["available", "trial", "expired"] as const)("allows acquisition during free %s access", (state) => {
    expect(canAcquirePlan({ plan: "free", enforced: true, active: state === "trial", state, limits: {} })).toBe(true);
  });
  it("doesn't offer acquisition until the account's access is known", () => {
    expect(canAcquirePlan(null)).toBe(false);
    expect(canAcquirePlan({ plan: "pro", enforced: true, limits: {} })).toBe(false);
  });
});

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

describe("planLimits", () => {
  it("reads immediate_alerts_per_day and leaves results uncapped when absent", () => {
    expect(planLimits({
      enforced: true,
      free: { max_profiles: 1, max_visible_results: 100, immediate_alerts_per_day: 3 },
      pass: { max_profiles: 3, immediate_alerts_per_day: 10, model_less_search: true },
      pro: { max_profiles: 15, immediate_alerts_per_day: 50, threshold_alerts: true, model_less_search: true },
    })).toEqual({ ...DEFAULT_PLAN_LIMITS,
      pro: { maxProfiles: 15, maxVisibleResults: null, immediateAlertsPerDay: 50, thresholdAlerts: true, modelLessSearch: true } });
  });
  it("gives a feature only to the plans that say true", () => {
    const limits = planLimits({ pro: { max_profiles: 20, threshold_alerts: true }, pass: { max_profiles: 3, threshold_alerts: "true" } });
    expect([limits.pro.thresholdAlerts, limits.pass.thresholdAlerts]).toEqual([true, false]);
    // model_less_search (docs/CARROCERIA.md) the same way.
    expect([limits.pro.modelLessSearch, limits.pass.modelLessSearch]).toEqual([false, false]);
    expect(planLimits({ pass: { max_profiles: 3, model_less_search: true } }).pass.modelLessSearch).toBe(true);
    expect([DEFAULT_PLAN_LIMITS.free, DEFAULT_PLAN_LIMITS.pass, DEFAULT_PLAN_LIMITS.pro].map((p) => p.modelLessSearch))
      .toEqual([false, true, true]);
  });
  it("reads the legacy boolean as the database does: the global cap or none", () => {
    const legacy = planLimits({
      free: { max_profiles: 1, max_visible_results: 50, immediate_alerts: false },
      pass: { max_profiles: 3, immediate_alerts: true },
      pro: { max_profiles: 10, immediate_alerts: true },
    }, 10);
    expect(legacy.free).toEqual({ maxProfiles: 1, maxVisibleResults: 50, immediateAlertsPerDay: 0, thresholdAlerts: false, modelLessSearch: false });
    expect(legacy.pro).toEqual({ maxProfiles: 10, maxVisibleResults: null, immediateAlertsPerDay: 10, thresholdAlerts: false, modelLessSearch: false });
  });
  it("keeps the defaults for a missing config or plan, and rejects junk", () => {
    expect(planLimits(null)).toEqual(DEFAULT_PLAN_LIMITS);
    expect(planLimits({ free: { max_profiles: "1", immediate_alerts_per_day: -2 } }).free)
      .toEqual({ maxProfiles: 1, maxVisibleResults: null, immediateAlertsPerDay: 0, thresholdAlerts: false, modelLessSearch: false });
  });
  it("words the per-plan alert caps for the plans page and terms", () => {
    expect(alertCapsText(DEFAULT_PLAN_LIMITS)).toBe(
      "Particular incluye hasta 10 avisos inmediatos de nuevas coincidencias por día y Pro, hasta 50, o sin tope para las oportunidades que elegís; los que pasan el tope van al resumen.");
    expect(alertCapsText({ ...DEFAULT_PLAN_LIMITS, pro: { ...DEFAULT_PLAN_LIMITS.pro, thresholdAlerts: false } })).toBe(
      "Particular incluye hasta 10 avisos inmediatos de nuevas coincidencias por día y Pro, hasta 50; los que pasan el tope van al resumen.");
  });
  it("lists Pro's card lines from its features", () => {
    expect(planFeatures(DEFAULT_PLAN_LIMITS.pro)).toEqual(["Hasta 20 búsquedas activas", "Todos los resultados disponibles",
      "Avisos inmediatos sin tope de las oportunidades que elegís", "Búsqueda por carrocería, sin modelo", "Historial y favoritos"]);
    expect(planFeatures(DEFAULT_PLAN_LIMITS.pass)).toEqual(["Hasta 3 búsquedas activas", "Todos los resultados disponibles",
      "Hasta 10 avisos inmediatos por día y resumen diario", "Búsqueda por carrocería, sin modelo", "Historial y favoritos"]);
    expect(planFeatures({ ...DEFAULT_PLAN_LIMITS.pass, modelLessSearch: false })).not.toContain("Búsqueda por carrocería, sin modelo");
  });
  it("words which plans search by body type without a model, from plan_limits", () => {
    expect(modelLessText(DEFAULT_PLAN_LIMITS)).toBe("Con Particular y Pro también podés buscar por carrocería, sin elegir "
      + "modelo (por ejemplo, cualquier SUV hasta un precio máximo): cuenta como una búsqueda.");
    const passless = { ...DEFAULT_PLAN_LIMITS, pass: { ...DEFAULT_PLAN_LIMITS.pass, modelLessSearch: false } };
    expect(modelLessText(passless)).toMatch(/^Con Pro también podés buscar por carrocería/);
    expect(modelLessText({ ...passless, pro: { ...DEFAULT_PLAN_LIMITS.pro, modelLessSearch: false } })).toBeNull();
  });
});

describe("account limits", () => {
  const trial = { plan: "free" as const, enforced: true, state: "trial" as const, active_searches: 0, limits: { max_profiles: 1 } };
  it("gives the remaining capacity only when limits are enforced", () => {
    expect(searchCapacity(trial)).toBe(1);
    expect(searchCapacity({ ...trial, plan: "pass", limits: { max_profiles: 3 }, active_searches: 1 })).toBe(2);
    expect(searchCapacity({ ...trial, active_searches: 2 })).toBe(0);
    expect(searchCapacity({ ...trial, enforced: false })).toBeNull();
    expect(searchCapacity(null)).toBeNull();
  });
  it("gives the daily alert cap of the account's plan", () => {
    expect(accountAlertCap(trial, DEFAULT_PLAN_LIMITS)).toBe(3);
    expect(accountAlertCap({ ...trial, plan: "pro" }, DEFAULT_PLAN_LIMITS)).toBe(50);
    expect(accountAlertCap({ ...trial, enforced: false }, DEFAULT_PLAN_LIMITS)).toBeNull();
  });
  it("tells whether the account gets immediate alerts, in both config shapes", () => {
    expect(includesImmediateAlerts({ ...trial, limits: { immediate_alerts_per_day: 3 } })).toBe(true);
    expect(includesImmediateAlerts({ ...trial, limits: { immediate_alerts_per_day: 0 } })).toBe(false);
    expect(includesImmediateAlerts({ ...trial, limits: { immediate_alerts: false } })).toBe(false);
    expect(includesImmediateAlerts({ ...trial, plan: "pass", limits: { immediate_alerts: true } })).toBe(true);
    expect(includesImmediateAlerts({ ...trial, enforced: false, limits: { immediate_alerts_per_day: 0 } })).toBe(true);
  });
  it("words the plans banner without fixed limits", () => {
    expect(bannerCopy("results", 100).body).toBe("Tu plan muestra hasta 100 publicaciones por búsqueda. Particular y Pro muestran todos los resultados disponibles.");
    expect(bannerCopy("plan_limit").body).not.toMatch(/\d/);
  });
});
