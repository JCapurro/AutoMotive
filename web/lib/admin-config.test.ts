import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { AdminLifecycleInput, AdminOfferInput, AdminPlanLimitsInput, configDifferences, configFieldLabel, CONFIRM_SOURCES_MESSAGE, DEALER_MARGIN_MESSAGE, LEVEL_THRESHOLDS_ORDER_MESSAGE, LIFECYCLE_KINDS, MAX_OFFER_ARS, RESCORE_EVERY_HOURS_MESSAGE, RESCORE_HOUR_MESSAGE, sameConfig, SCORE_GUARDS_ORDER_MESSAGE, SCORE_MODEL_F3_BOUNDS, SCORE_MODEL_F3_DEFAULTS, SCORE_MODEL_F3_LABELS, SCORE_MODEL_F3_MODES, SCORE_WEIGHTS_ZERO_MESSAGE, ScoreModelF3Input, scoreModelF3Problem, SourceUpdateInput, TRIAL_RESERVE_CONFIG_MESSAGE, validateConfigChange, visibleConfigRows, ZONE_NOTICE_CONFIG_MESSAGE } from "@/lib/admin-config";
import { DEFAULT_PRO_OFFER } from "@/lib/pro";

describe("guided config validators", () => {
  it("keeps trial_reserve a switch with a whole backfill_max and names both (prueba gratis)", () => {
    const seeded = { enabled: false, backfill_max: 30 };
    expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 30 }, seeded)).toBeNull();
    expect(validateConfigChange("trial_reserve", { enabled: false, backfill_max: 0 }, seeded)).toBeNull();
    for (const bad of [{ enabled: true }, { enabled: "true", backfill_max: 30 }, { enabled: true, backfill_max: -1 },
      { enabled: true, backfill_max: 1.5 }, { enabled: true, backfill_max: 2_147_483_648 }]) {
      expect(validateConfigChange("trial_reserve", bad, seeded)).toBe(TRIAL_RESERVE_CONFIG_MESSAGE);
    }
    expect(configFieldLabel("trial_reserve", "enabled")).toBe("Reserva de la prueba para autos nuevos");
    expect(configFieldLabel("trial_reserve", "backfill_max")).toBe("Máximo de resultados ya publicados");
  });
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
  it("validates dealer_margin and the PRO-02 plan keys", () => {
    const current = { as_of: "2026-11-02", source: "Juan", reconditioning: { pct: 5, min_usd: 300 }, transfer: { enabled: true } };
    expect(validateConfigChange("dealer_margin", current, current)).toBeNull();
    expect(validateConfigChange("dealer_margin", { ...current, reconditioning: { pct: 7.5, min_usd: 0 } }, current)).toBeNull();
    expect(validateConfigChange("dealer_margin", { ...current, plausible_ratio: { min: 0.4, max: 3 } }, current)).toBeNull();
    for (const bad of [{ reconditioning: { pct: 120, min_usd: 300 } }, { reconditioning: { pct: 5 } }, { transfer: { enabled: "yes" } },
      { as_of: "02/11/2026" }, { reconditioning: { pct: 5, min_usd: -1 } }, { plausible_ratio: { min: 0, max: 3 } },
      { plausible_ratio: { min: 0.4, max: 0.9 } }, { plausible_ratio: { min: 0.4 } }]) {
      expect(validateConfigChange("dealer_margin", { ...current, ...bad }, current)).toBe(DEALER_MARGIN_MESSAGE);
    }
    const limits = { enforced: false, pro: { max_profiles: 20, dealer_margin: true, min_threshold_usd: 500 } };
    expect(validateConfigChange("plan_limits", limits, limits)).toBeNull();
    expect(validateConfigChange("plan_limits", { ...limits, pro: { ...limits.pro, min_threshold_usd: 0 } }, limits)).not.toBeNull();
    expect(validateConfigChange("plan_limits", { ...limits, pro: { ...limits.pro, dealer_margin: "true" } }, limits)).not.toBeNull();
    expect(configFieldLabel("plan_limits", "pro.min_threshold_usd")).toBe("Pro: umbral mínimo por margen (USD)");
  });

  it("keeps seller_classification within the worker's bounds (F-02)", () => {
    const current = { enabled: true, min_listings: 6, window_days: 30 };
    const message = "enabled debe ser true/false, min_listings un entero entre 2 y 100 y window_days entre 1 y 180.";
    expect(validateConfigChange("seller_classification", current, current)).toBeNull();
    expect(validateConfigChange("seller_classification", { enabled: false, min_listings: 2, window_days: 180 }, current)).toBeNull();
    expect(validateConfigChange("seller_classification", { enabled: true, min_listings: 100, window_days: 1 }, current)).toBeNull();
    for (const bad of [
      { enabled: "true" }, { enabled: 1 }, { enabled: null },
      { min_listings: 1 }, { min_listings: 101 }, { min_listings: 6.5 }, { min_listings: "6" },
      { window_days: 0 }, { window_days: 181 }, { window_days: 7.5 }, { window_days: "30" },
    ]) {
      expect(validateConfigChange("seller_classification", { ...current, ...bad }, current)).toBe(message);
    }
    expect(validateConfigChange("seller_classification", { enabled: true, min_listings: 6 }, current)).toBe(message);
    expect(validateConfigChange("seller_classification", { ...current, min_listing: 5 }, current)).toBe(message);
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
  it("keeps zone_notice a true/false switch and names it (aviso de zona)", () => {
    expect(validateConfigChange("zone_notice", { enabled: false }, { enabled: true })).toBeNull();
    for (const value of [{}, { enabled: "false" }, { enabled: null }]) {
      expect(validateConfigChange("zone_notice", value, { enabled: true })).toBe(ZONE_NOTICE_CONFIG_MESSAGE);
    }
    expect(configFieldLabel("zone_notice", "enabled")).toBe("Aviso de zona visible (resultados y modo asistido)");
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

describe("retired config keys (X-01 notes removed, Juan 02/11)", () => {
  it("hides listing_tracking from /admin/config and keeps the rest in order", () => {
    const rows = [{ key: "comparables" }, { key: "listing_tracking" }, { key: "risk" }];
    expect(visibleConfigRows(rows)).toEqual([{ key: "comparables" }, { key: "risk" }]);
  });
  it("refuses to save listing_tracking", () => {
    expect(validateConfigChange("listing_tracking", { note_max_chars: 300 }, { note_max_chars: 500 })).toMatch(/ya no se usa/);
  });
});

describe("scoring config bounds (same as worker/intelligence/config.py)", () => {
  // app_config in production on 09/11/2026: every value must still save.
  const production = {
    score_weights: { km: 15, trim: 10, match: 25, price: 35, recency: 10, completeness: 5 },
    level_thresholds: { good: 70, high: 85, match: 50 },
    score_curves: {
      km: { base: 0.5, slope: 1.25 }, trim: { other: 0.2, unknown: 0.5, preferred: 1, no_preference: 1 },
      match: { unknown_penalty: 0.15 }, price: { base: 0.5, pct_per_unit: 20 },
      guards: { partial_pct: 65, suspicious_pct: 50 }, recency: { half_life_hours: 24 },
      completeness: { min_images: 3, min_description_chars: 150 },
    },
    comparables: { min_n: 5, year_tol: 1, km_tol_pct: 25, max_age_days: 30, confirm_grace_hours: 36,
      confirm_sources: ["autocity", "carone", "deruedas", "gruporandazzo", "mardelusados", "rosariogarage", "mercadolibre"] },
    rescore: { days: 14, hour: "04:00", every_hours: 6 },
    digest_top_n: 10, price_drop_min_pct: 3, alerts_max_per_user_day: 10,
  } as Record<string, unknown>;
  const check = (key: string, value: unknown) => validateConfigChange(key, value, production[key]);
  const curves = production.score_curves as Record<string, Record<string, unknown>>;
  const withCurve = (name: string, change: Record<string, unknown>) => ({ ...curves, [name]: { ...curves[name], ...change } });

  it.each(Object.keys(production))("accepts the production %s", (key) => {
    expect(check(key, production[key])).toBeNull();
  });

  it("keeps score_weights finite, from 0 to 1000 and not all zero", () => {
    const weights = production.score_weights as Record<string, number>;
    expect(check("score_weights", { ...weights, completeness: 0 })).toBeNull();
    expect(check("score_weights", { price: 100, match: 0, km: 0, trim: 0, recency: 0, completeness: 0 })).toBeNull();
    expect(check("score_weights", { price: 0 })).toBeNull(); // the others keep their defaults
    expect(check("score_weights", { price: 0, match: 0, km: 0, trim: 0, recency: 0, completeness: 0 })).toBe(SCORE_WEIGHTS_ZERO_MESSAGE);
    expect(check("score_weights", { ...weights, price: -1 })).toBe("score_weights.price tiene que ser un número de 0 a 1.000.");
    for (const price of [1001, "35", null, true]) expect(check("score_weights", { ...weights, price })).toMatch(/^score_weights\.price /);
    expect(check("score_weights", { ...weights, price: NaN })).toMatch(/números finitos/);
    expect(check("score_weights", { ...weights, prcie: 40 })).toBe("score_weights no usa prcie; sus claves son price, match, km, trim, recency, completeness.");
  });

  it("keeps level_thresholds numbers from 0 to 100 with high > good > match", () => {
    expect(check("level_thresholds", { high: 90, good: 75, match: 55 })).toBeNull();
    expect(check("level_thresholds", { high: 90 })).toBeNull();
    expect(check("level_thresholds", { high: "80", good: 70, match: 50 })).toBe("level_thresholds.high tiene que ser un número de 0 a 100.");
    for (const bad of [{ high: 60, good: 70 }, { high: 60, good: 70, match: 50 }, { high: 70, good: 70, match: 50 }, { match: 70 }]) {
      expect(check("level_thresholds", bad)).toBe(LEVEL_THRESHOLDS_ORDER_MESSAGE);
    }
    expect(check("level_thresholds", { high: 101, good: 70, match: 50 })).toMatch(/^level_thresholds\.high /);
    expect(check("level_thresholds", { high: 85, good: 70, match: -1 })).toMatch(/^level_thresholds\.match /);
    expect(check("level_thresholds", { high: 85, good: 70, match: 50, low: 0 })).toMatch(/no usa low/);
  });

  it("keeps score_curves with positive divisors and values a component can take", () => {
    expect(check("score_curves", { recency: { half_life_hours: 12 } })).toBeNull();
    expect(check("score_curves", withCurve("recency", { half_life_hours: 0.5 }))).toBeNull();
    expect(check("score_curves", withCurve("recency", { half_life_hours: 0 }))).toBe("score_curves.recency.half_life_hours tiene que ser un número mayor que 0 y hasta 720.");
    expect(check("score_curves", withCurve("price", { pct_per_unit: 0 }))).toBe("score_curves.price.pct_per_unit tiene que ser un número mayor que 0 y hasta 100.");
    const bad: [string, Record<string, unknown>][] = [
      ["price", { pct_per_unit: -20 }], ["price", { base: 1.5 }], ["match", { unknown_penalty: -0.1 }],
      ["km", { slope: -1 }], ["km", { slope: 11 }], ["trim", { preferred: 1.5 }], ["trim", { other: "0.2" }],
      ["recency", { half_life_hours: 721 }], ["completeness", { min_images: 2.5 }], ["completeness", { min_description_chars: -1 }],
      ["guards", { partial_pct: 10 }], ["guards", { suspicious_pct: 101 }],
    ];
    for (const [name, change] of bad) {
      const [field] = Object.keys(change);
      expect(check("score_curves", withCurve(name, change))).toMatch(new RegExp(`^score_curves\\.${name}\\.${field} tiene que ser`));
    }
    expect(check("score_curves", withCurve("guards", { suspicious_pct: 70 }))).toBe(SCORE_GUARDS_ORDER_MESSAGE);
    expect(check("score_curves", { guards: { suspicious_pct: 70 } })).toBe(SCORE_GUARDS_ORDER_MESSAGE); // partial_pct defaults to 65
    expect(check("score_curves", withCurve("guards", { suspicious_pct: 65 }))).toBeNull();
    expect(check("score_curves", { ...curves, price: null })).toBe("score_curves.price tiene que ser un objeto.");
    expect(check("score_curves", { ...curves, prices: {} })).toMatch(/^score_curves no usa prices;/);
    expect(check("score_curves", withCurve("km", { slpoe: 1 }))).toMatch(/^score_curves\.km no usa slpoe;/);
  });

  it("keeps comparables whole numbers in sane ranges and lets other keys through", () => {
    const current = production.comparables as Record<string, unknown>;
    expect(check("comparables", { ...current, min_n: 1, year_tol: 0, km_tol_pct: 100, max_age_days: 180 })).toBeNull();
    expect(check("comparables", { ...current, gone_max_age_days: 7 })).toBeNull();
    expect(check("comparables", { ...current, gone_max_age_days: null })).toBeNull();
    expect(check("comparables", { ...current, future_key: "x" })).toBeNull();
    expect(check("comparables", { ...current, min_n: 0 })).toBe("comparables.min_n tiene que ser un entero de 1 a 1.000.");
    for (const change of [{ min_n: 1.5 }, { min_n: "5" }, { min_n: 1001 }, { year_tol: 1.5 }, { year_tol: 11 },
      { km_tol_pct: 101 }, { km_tol_pct: 12.5 }, { max_age_days: 0 }, { max_age_days: 181 },
      { confirm_grace_hours: -1 }, { gone_max_age_days: 0 }, { min_n: null }]) {
      const [field] = Object.keys(change);
      expect(check("comparables", { ...current, ...change })).toMatch(new RegExp(`^comparables\\.${field} tiene que ser un entero`));
    }
    for (const confirm_sources of ["autocity", ["autocity", 1], [""], null]) {
      expect(check("comparables", { ...current, confirm_sources })).toBe(CONFIRM_SOURCES_MESSAGE);
    }
  });

  it("keeps rescore.hour a valid HH:MM, every_hours a divisor of 24 and days from 1 to 180", () => {
    expect(check("rescore", { days: 1, hour: "00:00", every_hours: 1 })).toBeNull();
    expect(check("rescore", { days: 180, hour: "23:59", every_hours: 24 })).toBeNull();
    expect(check("rescore", { days: 14 })).toBeNull();
    for (const hour of ["25:00", "24:00", "04:60", "4:00", "4", 400, null]) {
      expect(check("rescore", { days: 14, hour, every_hours: 6 })).toBe(RESCORE_HOUR_MESSAGE);
    }
    for (const every_hours of [1, 2, 3, 4, 6, 8, 12, 24]) expect(check("rescore", { days: 14, hour: "04:00", every_hours })).toBeNull();
    // Not a divisor of 24: the worker would run it once a day (next_slot).
    for (const every_hours of [5, 7, 9, 10, 16, 0, 25, 48, 1.5, "6", null]) {
      expect(check("rescore", { days: 14, hour: "04:00", every_hours })).toBe(RESCORE_EVERY_HOURS_MESSAGE);
    }
    expect(check("rescore", { days: 0, hour: "04:00" })).toBe("rescore.days tiene que ser un entero de 1 a 180.");
    expect(check("rescore", { days: 14, hour: "04:00", every_hour: 6 })).toMatch(/^rescore no usa every_hour;/);
  });

  it("keeps the alert and digest numbers in range", () => {
    expect(check("digest_top_n", 1)).toBeNull();
    expect(check("digest_top_n", 50)).toBeNull();
    for (const n of [0, 51, 2.5]) expect(check("digest_top_n", n)).toBe("digest_top_n tiene que ser un entero de 1 a 50.");
    expect(check("price_drop_min_pct", 0)).toBeNull();
    expect(check("price_drop_min_pct", 0.5)).toBeNull();
    for (const n of [-1, 101]) expect(check("price_drop_min_pct", n)).toBe("price_drop_min_pct tiene que ser un número de 0 a 100.");
    expect(check("alerts_max_per_user_day", 0)).toBeNull();
    for (const n of [-1, 7.5, 2_147_483_648]) {
      expect(check("alerts_max_per_user_day", n)).toBe("alerts_max_per_user_day tiene que ser un entero de 0 a 2.147.483.647.");
    }
    expect(check("alerts_max_per_user_day", "10")).toMatch(/tiene que ser number/); // the shape check, as before
  });
});

// f3 «precio × encaje» in shadow (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §8).
const REPO = path.resolve(__dirname, "../..");
const MIGRATION = "supabase/migrations/20261212120000_score_f3_shadow.sql";
/** The app_config row the migration seeds (kept ONE json literal, as worker/tests/test_f3_migration_defaults.py reads it). */
function migrationValue(): Record<string, unknown> {
  const sql = readFileSync(path.join(REPO, MIGRATION), "utf-8");
  const literal = /values \('score_model_f3', '(\{[\s\S]*?\})'::jsonb\)/.exec(sql)?.[1];
  if (!literal) throw new Error(`${MIGRATION}: no score_model_f3 json literal`);
  return JSON.parse(literal) as Record<string, unknown>;
}
/** worker/intelligence/config.py, the side this validator mirrors. */
const WORKER_CONFIG = readFileSync(path.join(REPO, "worker/intelligence/config.py"), "utf-8");
/** The Python dict literal assigned to `name` (until the closing brace at column 0), as JSON. */
function pythonDict(name: string): Record<string, unknown> {
  const block = new RegExp(`^${name}[^=\\n]*= (\\{[\\s\\S]*?\\n\\})`, "m").exec(WORKER_CONFIG)?.[1];
  if (!block) throw new Error(`worker/intelligence/config.py: ${name} not found; update this test with the worker`);
  return JSON.parse(block.replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false").replace(/\(([^()]*)\)/g, "[$1]").replace(/,(\s*[}\]])/g, "$1")) as Record<string, unknown>;
}
const CURRENT = migrationValue();
const f3 = (value: unknown) => validateConfigChange("score_model_f3", value, CURRENT);

describe("score_model_f3 (f3 «precio × encaje», shadow)", () => {
  it("mirrors the worker: defaults, modes, bounds and the whole-count key", () => {
    expect(pythonDict("DEFAULT_SCORE_MODEL_F3")).toEqual(SCORE_MODEL_F3_DEFAULTS);
    expect(SCORE_MODEL_F3_DEFAULTS.mode).toBe("off");
    expect(/^F3_MODES = \(([^)]*)\)/m.exec(WORKER_CONFIG)?.[1].split(",").map((m) => m.trim().replace(/"/g, ""))).toEqual([...SCORE_MODEL_F3_MODES]);
    expect(pythonDict("F3_BOUNDS")).toEqual(SCORE_MODEL_F3_BOUNDS);
    expect(/^F3_INTEGERS = frozenset\(\{([^}]*)\}\)/m.exec(WORKER_CONFIG)?.[1].trim()).toBe('("levels", "n_min_high")');
    // Every tunable key has a bound and a default, and the other way around.
    for (const group of ["deal", "fit", "levels"] as const) {
      expect(Object.keys(SCORE_MODEL_F3_BOUNDS[group]).sort()).toEqual(Object.keys(SCORE_MODEL_F3_DEFAULTS[group]).sort());
    }
  });

  it("accepts the migration's row, which is the defaults with mode shadow", () => {
    expect(CURRENT).toEqual({ ...SCORE_MODEL_F3_DEFAULTS, mode: "shadow" });
    expect(f3(CURRENT)).toBeNull();
    expect(scoreModelF3Problem(SCORE_MODEL_F3_DEFAULTS)).toBeNull();
    expect(ScoreModelF3Input.parse(CURRENT)).toEqual(CURRENT); // nothing dropped or added
  });

  it("accepts the three modes, the rollback and partial values (a missing key keeps its default)", () => {
    for (const mode of SCORE_MODEL_F3_MODES) expect(f3({ ...CURRENT, mode })).toBeNull();
    for (const value of [{}, { mode: "off" }, { levels: { c_high: 0.84 } }, { deal: { kavak_offset: 0 } }, { rules: { seller_cap: false } },
      { mode: "shadow", fit: {}, rules: { agency_voice: false, placeholder: false, pro_deal_d: false } },
      { deal: { d_floor: 5, d_ceil: 30, d_mult: 1, cred_min: 0, cred_max: 49.9 } }]) {
      expect(f3(value), JSON.stringify(value)).toBeNull();
    }
  });

  it("holds every key inside the worker's bound, ends included (cred_max below 50)", () => {
    for (const [group, keys] of Object.entries(SCORE_MODEL_F3_BOUNDS)) {
      for (const [name, [low, high, open]] of Object.entries(keys)) {
        const ok = (n: number) => ScoreModelF3Input.safeParse({ [group]: { [name]: n } }).success;
        expect(ok(low), `${group}.${name} = ${low}`).toBe(true);
        expect(ok(high), `${group}.${name} = ${high}`).toBe(!open);
        expect(ok(low - 0.01), `${group}.${name} = ${low - 0.01}`).toBe(false);
        expect(ok(high + 0.01), `${group}.${name} = ${high + 0.01}`).toBe(false);
        expect(ok(Number.NaN), `${group}.${name} = NaN`).toBe(false);
      }
    }
    expect(f3({ deal: { cred_max: 50 } })).toBe("deal.cred_max tiene que ser un número (sin comillas) desde 20 y menor que 50 (el «sospechoso» de score_curves.guards).");
    expect(f3({ fit: { unknown_hard: 0.2 } })).toBe("fit.unknown_hard tiene que ser un número (sin comillas) entre 0 y 0,15.");
    expect(f3({ levels: { low_d: -31 } })).toBe("levels.low_d tiene que ser un número (sin comillas) entre −30 y 0.");
  });

  it("refuses strings, booleans and null where a number goes (a \"0.82\" would be dropped by the worker)", () => {
    expect(f3({ ...CURRENT, levels: { ...(CURRENT.levels as object), c_high: "0.82" } })).toBe("levels.c_high tiene que ser un número (sin comillas) entre 0,7 y 0,95.");
    expect(f3({ deal: { d_mult: true } })).toMatch(/^deal\.d_mult tiene que ser un número/);
    expect(f3({ fit: { fail: null } })).toMatch(/^fit\.fail tiene que ser un número/);
    expect(f3({ levels: { c_high: Infinity } })).toMatch(/finitos/);
  });

  it("keeps n_min_high a whole count from 5 to 100", () => {
    expect(f3({ levels: { n_min_high: 5 } })).toBeNull();
    for (const n_min_high of [4, 10.5, 101]) expect(f3({ levels: { n_min_high } })).toBe("levels.n_min_high tiene que ser un entero (sin comillas) entre 5 y 100.");
  });

  it("refuses a mode that is not off, shadow or live, and rules that are not true/false", () => {
    for (const mode of ["on", "OFF", "", 1, true, null]) expect(f3({ ...CURRENT, mode })).toBe("mode tiene que ser off, shadow o live.");
    for (const seller_cap of ["true", 1, null]) expect(f3({ rules: { seller_cap } })).toBe("rules.seller_cap tiene que ser true o false (sin comillas).");
  });

  it("refuses an unknown key, so a typo can't look applied (the worker ignores it)", () => {
    expect(f3({ ...CURRENT, levels: { ...(CURRENT.levels as object), c_hihg: 0.84 } })).toBe(
      "levels no tiene la clave «c_hihg»: revisá cómo está escrita. Sus claves son x_high, y_high, c_high, x_good, y_deal, y_good, y_min, n_min_high, fair_min_d y low_d.");
    expect(f3({ ...CURRENT, params: "3f2a9c1d07be" })).toBe("score_model_f3 no tiene la clave «params»: revisá cómo está escrita. Sus claves son mode, deal, fit, levels y rules.");
    expect(f3({ rules: { seller_cap: true, voice: true } })).toMatch(/^rules no tiene la clave «voice»/);
    expect(f3({ deal: { d_susp: 50 } })).toMatch(/^deal no tiene la clave «d_susp».*kavak_offset\.$/); // f3 reads score_curves.guards.suspicious_pct
    expect(f3({ deal: 3 })).toBe("deal tiene que ser un objeto con sus claves (d_floor, d_ceil, d_mult, cred_min, cred_max, r_model, r_noyear y kavak_offset).");
    expect(f3([])).toMatch(/object/); // the generic shape check comes first
  });

  it("applies the cross-key rules over the defaults, like the worker (which drops the whole group)", () => {
    expect(f3({ deal: { d_floor: 20, d_ceil: 20 } })).toBe("deal.d_floor tiene que ser menor que deal.d_ceil (los dos entre 5 y 30).");
    expect(f3({ deal: { d_floor: 25 } })).toMatch(/^deal\.d_floor tiene que ser menor que deal\.d_ceil/); // d_ceil's default is 20
    expect(f3({ deal: { d_floor: 25, d_ceil: 30 } })).toBeNull();
    expect(f3({ fit: { fail: 0.8 } })).toBe("fit.fail no puede ser mayor que fit.unknown: una preferencia sin dato nunca pesa menos que una que no se cumple.");
    expect(f3({ fit: { fail: 0.75 } })).toBeNull();
    expect(f3({ levels: { x_good: 0.7 } })).toMatch(/^levels\.x_good tiene que ser menor que levels\.x_high/);
    expect(f3({ levels: { y_deal: 0.7 } })).toMatch(/^levels\.y_deal tiene que ser menor que levels\.y_high/);
    expect(f3({ levels: { y_good: 0.55, y_min: 0.6 } })).toBe("levels.y_good tiene que ser mayor que levels.y_min.");
    expect(f3({ levels: { low_d: -2 } })).toBe("levels.low_d tiene que ser menor que levels.fair_min_d.");
    expect(f3({ levels: { low_d: -3 } })).toBeNull();
  });

  it("refuses a c_high the combined 🔥 rule can never reach (it would do nothing)", () => {
    expect(f3({ levels: { x_high: 0.9, y_high: 0.9, c_high: 0.85 } })).toBe(
      "levels.c_high tiene que ser al menos 0,6·x_high + 0,4·y_high (con estos valores, 0,9); si no, el mínimo combinado de 🔥 no hace nada.");
    expect(f3({ levels: { x_high: 0.9, y_high: 0.9, c_high: 0.9 } })).toBeNull(); // 0.6·0.9 + 0.4·0.9 is 0.9000000000000001
    expect(f3({ levels: { x_high: 0.95, y_high: 0.5 } })).toBeNull(); // 0.77 ≤ 0.82
    expect(f3({ levels: { x_high: 0.95, y_high: 0.95 } })).toMatch(/^levels\.c_high tiene que ser al menos/); // 0.95 > the default 0.82
  });

  it("names every key in the change preview", () => {
    const paths = ["mode", ...Object.entries(SCORE_MODEL_F3_BOUNDS).flatMap(([group, keys]) => Object.keys(keys).map((name) => `${group}.${name}`)),
      ...Object.keys(SCORE_MODEL_F3_DEFAULTS.rules).map((name) => `rules.${name}`)];
    expect(Object.keys(SCORE_MODEL_F3_LABELS).sort()).toEqual([...paths].sort());
    for (const p of paths) expect(configFieldLabel("score_model_f3", p)).not.toBe(p);
    expect(configFieldLabel("score_model_f3", "mode")).toBe("Modo de f3 (off, shadow o live)");
    expect(configFieldLabel("score_model_f3", "levels.c_high")).toContain("(c_high)");
    const after = { ...CURRENT, mode: "off", levels: { ...(CURRENT.levels as object), c_high: 0.84 } };
    expect(configDifferences(CURRENT, after).map((d) => configFieldLabel("score_model_f3", d.path))).toEqual([
      "Modo de f3 (off, shadow o live)", SCORE_MODEL_F3_LABELS["levels.c_high"],
    ]);
  });
});
