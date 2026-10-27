import { describe, expect, it } from "vitest";

import { AdminLifecycleInput, AdminOfferInput, AdminPlanLimitsInput, configDifferences, LIFECYCLE_KINDS, MAX_OFFER_ARS, sameConfig, SourceUpdateInput, validateConfigChange } from "@/lib/admin-config";
import { DEFAULT_PRO_OFFER } from "@/lib/pro";

describe("guided config validators", () => {
  it.each([-1, 1.5, NaN, Infinity, 2_147_483_648, "3"])("rejects invalid plan counts: %s", (n) => {
    expect(AdminPlanLimitsInput.safeParse({ free: { max_profiles: n } }).success).toBe(false);
  });
  it("honors unlimited results/locations, zero searches/alerts, booleans, and legacy options", () => {
    const value = { enforced: true, free: { max_profiles: 0, max_visible_results: null, immediate_alerts_per_day: 0, max_locations: null, immediate_alerts: true, future_feature: { retain: true } }, future_plan: { any: "value" } };
    expect(AdminPlanLimitsInput.parse(value)).toEqual(value);
    expect(AdminPlanLimitsInput.safeParse({ pro: { max_visible_results: 0 } }).success).toBe(false);
    expect(AdminPlanLimitsInput.safeParse({ pro: { max_locations: 0 } }).success).toBe(false);
    expect(AdminPlanLimitsInput.safeParse({ pro: { threshold_alerts: "true" } }).success).toBe(false);
  });
  it("preserves unknown fields in offers, plans, lifecycle options and kinds", () => {
    const offer = { ...DEFAULT_PRO_OFFER, extra: "keep", pass_30: { ...DEFAULT_PRO_OFFER.pass_30, another: 7 } };
    expect(AdminOfferInput.parse(offer)).toEqual(offer);
    const lifecycle = { kinds: { trial_ended: false, future_mail: "retain" }, future: { a: 1 } };
    expect(AdminLifecycleInput.parse(lifecycle)).toEqual(lifecycle);
    expect(AdminLifecycleInput.parse({})).toEqual({}); // Opening does not materialize defaults.
  });
  it.each([{ amount: 1.2 }, { amount: 0 }, { currency: "USD" }, { days: 31 }])("keeps the ARS/30 day offer contract: %o", (change) => {
    expect(AdminOfferInput.safeParse({ ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, ...change } }).success).toBe(false);
  });
  it("requires a new version when effective prices change, but not for unrelated data", () => {
    const changed = { ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: 12345 } };
    expect(validateConfigChange("pro_offer", changed, DEFAULT_PRO_OFFER)).toMatch(/versión/);
    expect(validateConfigChange("pro_offer", { ...changed, version: "new-version" }, DEFAULT_PRO_OFFER)).toBeNull();
    expect(validateConfigChange("pro_offer", { ...DEFAULT_PRO_OFFER, extra: true }, DEFAULT_PRO_OFFER)).toBeNull();
    // Restoring an old price with the current version is validated like any other edit.
    expect(validateConfigChange("pro_offer", DEFAULT_PRO_OFFER, changed)).toMatch(/versión/);
  });
  it("fits the numeric(12,2) payment ledger", () => {
    expect(AdminOfferInput.safeParse({ ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: MAX_OFFER_ARS } }).success).toBe(true);
    expect(AdminOfferInput.safeParse({ ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: MAX_OFFER_ARS + 1 } }).success).toBe(false);
  });
  it.each(["24:00", "9:00", "09:60", 900, null])("rejects invalid HH:MM types: %s", (send_from) => {
    expect(AdminLifecycleInput.safeParse({ send_from }).success).toBe(false);
  });
  it("requires a same-day window and a validity longer than its night", () => {
    expect(AdminLifecycleInput.safeParse({ send_from: "21:00", send_until: "09:00" }).success).toBe(false);
    expect(AdminLifecycleInput.safeParse({ send_from: "09:00", send_until: "21:00", window_hours: 12 }).success).toBe(false);
    expect(AdminLifecycleInput.safeParse({ send_from: "09:00", send_until: "21:00", window_hours: 13, max_per_day: 0 }).success).toBe(true);
    expect(AdminLifecycleInput.safeParse({ max_per_day: true }).success).toBe(false);
    expect(AdminLifecycleInput.safeParse({ window_hours: Infinity }).success).toBe(false);
    expect(AdminLifecycleInput.safeParse({ window_hours: 720 }).success).toBe(true);
    expect(AdminLifecycleInput.safeParse({ window_hours: 721 }).success).toBe(false);
  });
  it("validates every supported email kind without enabling default-off kinds", () => {
    expect(Object.keys(LIFECYCLE_KINDS)).toHaveLength(12);
    for (const kind of Object.keys(LIFECYCLE_KINDS)) expect(AdminLifecycleInput.safeParse({ kinds: { [kind]: "false" } }).success).toBe(false);
    expect(LIFECYCLE_KINDS.search_feedback.enabled).toBe(false);
    expect(LIFECYCLE_KINDS.bonus_trial_offer.enabled).toBe(false);
  });
  it("cannot enable the commercial pilot or enforced limits through generic config", () => {
    expect(validateConfigChange("commercial_pilot", {}, {})).toMatch(/Cobros/);
    expect(validateConfigChange("plan_limits", { enforced: true }, { enforced: false })).toMatch(/Cobros/);
    expect(validateConfigChange("plan_limits", {}, { enforced: true })).toMatch(/Cobros/);
    expect(validateConfigChange("other", [], {})).toMatch(/object/);
    expect(validateConfigChange("other", null, {})).toMatch(/null/);
    expect(validateConfigChange("other", { overflow: Infinity }, {})).toMatch(/finitos/);
  });
  it("validates exact source seconds and requires the previous values", () => {
    const input = { id: "source", enabled: false, crawl_interval_seconds: 125, expected: { enabled: true, crawl_interval_seconds: 123 } };
    expect(SourceUpdateInput.parse(input)).toEqual(input);
    expect(SourceUpdateInput.safeParse({ ...input, expected: undefined }).success).toBe(false);
    for (const n of [59, 86401, 120.1, NaN, Infinity]) expect(SourceUpdateInput.safeParse({ ...input, crawl_interval_seconds: n }).success).toBe(false);
    expect(SourceUpdateInput.safeParse({ ...input, actor_id: "client-controlled" }).success).toBe(false);
  });
});

it("compares JSON independent of object ordering and previews field deletions", () => {
  expect(sameConfig({ a: 1, nested: { b: 2 } }, { nested: { b: 2 }, a: 1 })).toBe(true);
  expect(sameConfig([1, 2], [2, 1])).toBe(false);
  expect(configDifferences({ a: 1, nested: { b: true } }, { nested: { b: false } })).toEqual([
    { path: "a", before: 1, after: undefined }, { path: "nested.b", before: true, after: false },
  ]);
});
