import { describe, expect, it } from "vitest";

import { AdminLifecycleInput, AdminOfferInput, AdminPlanLimitsInput, configDifferences, configFieldLabel, LIFECYCLE_KINDS, MAX_OFFER_ARS, sameConfig, SourceUpdateInput, validateConfigChange } from "@/lib/admin-config";
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
  it("keeps price_track.min_drop_pct a percentage (PAR-03)", () => {
    const current = { min_drop_pct: 1 };
    expect(validateConfigChange("price_track", { min_drop_pct: 0.5 }, current)).toBeNull();
    expect(validateConfigChange("price_track", { min_drop_pct: 0 }, current)).toBeNull();
    for (const min_drop_pct of [-1, 101, "1", null]) {
      expect(validateConfigChange("price_track", { min_drop_pct }, current)).toMatch(/min_drop_pct/);
    }
    expect(validateConfigChange("price_track", {}, current)).toMatch(/min_drop_pct/);
  });
  it("accepts only safe official links in risk (PAR-02)", () => {
    const current = { checklist_enabled: true, links: { dnrpa: null, patentes: [], infracciones: [], vtv: null, form_08: null } };
    expect(validateConfigChange("risk", current, current)).toBeNull();
    const withLink = (url: string, label = "DNRPA") => ({ ...current, links: { ...current.links, dnrpa: { label, url } } });
    expect(validateConfigChange("risk", withLink("https://dnrpa.example.test/informe"), current)).toBeNull();
    for (const url of ["http://dnrpa.example.test/", "javascript:alert(1)", "https://u:p@dnrpa.example.test/", `https://dnrpa.example.test/${"x".repeat(300)}`]) {
      expect(validateConfigChange("risk", withLink(url), current)).toMatch(/https/);
    }
    expect(validateConfigChange("risk", withLink("https://dnrpa.example.test/", " "), current)).toMatch(/etiqueta/);
    expect(validateConfigChange("risk", { ...current, checklist_enabled: "no" }, current)).toMatch(/checklist_enabled/);
    expect(validateConfigChange("risk", [], current)).toMatch(/object/);
  });
  it("names the risk fields in the change preview (PAR-02)", () => {
    expect(configFieldLabel("risk", "checklist_enabled")).toBe("Checklist «Antes de señar» visible");
    expect(configFieldLabel("risk", "links.dnrpa.url")).toBe("Link oficial: informe de dominio (DNRPA) (url)");
    expect(configFieldLabel("risk", "links.patentes")).toBe("Link oficial: patentes");
    expect(configFieldLabel("risk", "other")).toBe("other");
  });
  it("keeps the much_cheaper bands reachable in red_flags (PAR-02)", () => {
    const current = { much_cheaper_pct: 25, anticipo_pct: 50, min_km_per_year: 5000, min_description_chars: 150 };
    expect(validateConfigChange("red_flags", current, current)).toBeNull();
    expect(validateConfigChange("red_flags", { ...current, much_cheaper_verify_pct: 35 }, current)).toBeNull();
    expect(validateConfigChange("red_flags", { ...current, much_cheaper_verify_pct: 50 }, current)).toBeNull();
    for (const much_cheaper_verify_pct of [20, 25, 51, "35"]) {
      expect(validateConfigChange("red_flags", { ...current, much_cheaper_verify_pct }, current)).toMatch(/much_cheaper_verify_pct/);
    }
    // Missing keys fall back to the worker's defaults (25 / 35 / 50).
    expect(validateConfigChange("red_flags", { anticipo_pct: 30 }, current)).toMatch(/much_cheaper_verify_pct/);
    expect(validateConfigChange("red_flags", { much_cheaper_pct: 40 }, current)).toMatch(/much_cheaper_verify_pct/);
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
