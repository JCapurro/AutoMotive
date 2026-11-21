import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

// «40 + N» (docs/PRUEBA_COMPLETA.md): the switch's new fields, the quota's
// completion, the complete variant's copy and components, and the texts that
// say both numbers. What opens and when is the browser's (manual check).
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: vi.fn() }));
vi.mock("@/app/app/pro/actions", () => ({ trackTrialOffer: vi.fn() }));
vi.mock("@/app/app/feedback/actions", () => ({ submitProductFeedback: vi.fn() }));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));

import { SearchPreparation } from "@/components/app/search-preparation";
import { TrialHiddenCard, TrialHiddenOffer, TrialPassChoice } from "@/components/app/trial-hidden-offer";
import { TRIAL_RESERVE_CONFIG_MESSAGE, validateConfigChange, configFieldLabel } from "./admin-config";
import { forbiddenTermsIn } from "./copy";
import { DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER, freeResultQuota, planPrice, resultsText, type PlanLimits } from "./pro";
import { cardLead, COMPLETE_BADGE, COMPLETE_STRIP_BUTTON, completeLead, completePayLabel, completeStripText, completeTitle, keepLabel, type Segment, trialCompleteText, trialOffer, type TrialOffer } from "./trial-offer";
import { trialReserveConfig } from "./trial-reserve";

const text = (segments: Segment[]) => segments.map((s) => (typeof s === "string" ? s : s.mark)).join("");
const counts = (shown: number, hidden: number): TrialOffer => ({ shown, hidden, total: shown + hidden });

describe("trial_reserve's new fields", () => {
  it("reads the cap, the sample and the notice only with the reserve on", () => {
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, new_max: 5, random_stock: true, notice_since: "2026-11-21T12:00:00Z" }))
      .toEqual({ enabled: true, backfillMax: 40, newMax: 5, randomStock: true, noticeSince: "2026-11-21T12:00:00Z" });
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, new_max: 5.9 }).newMax).toBe(5);
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, new_max: 0 }).newMax).toBe(0);
    expect(trialReserveConfig({ enabled: false, backfill_max: 40, new_max: 5, random_stock: true, notice_since: "2026-11-21T12:00:00Z" }))
      .toEqual({ enabled: false, backfillMax: 40, newMax: null, randomStock: false, noticeSince: null });
  });
  it.each([{ new_max: "5" }, { new_max: -1 }, { new_max: null }, { new_max: Number.NaN }])("has no cap for %j", (extra) => {
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, ...extra }).newMax).toBeNull();
  });
  it("is off for a random_stock that isn't true, and has no notice for an unreadable date", () => {
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, random_stock: "true" }).randomStock).toBe(false);
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, new_max: 5, notice_since: "mañana" }).noticeSince).toBeNull();
    expect(trialReserveConfig({ enabled: true, backfill_max: 40, notice_since: "2026-11-21T12:00:00Z" }).noticeSince).toBeNull();
  });
  it("is accepted in /admin/config with the three fields, and each field is named", () => {
    const seeded = { enabled: true, backfill_max: 30 };
    expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 40, new_max: 5, random_stock: true, notice_since: "2026-11-21T12:00:00Z" }, seeded)).toBeNull();
    expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 40, notice_since: "2026-11-21T09:00:00-03:00" }, seeded)).toBeNull();
    for (const bad of [{ new_max: 2.5 }, { new_max: -1 }, { new_max: "5" }, { random_stock: "true" }, { notice_since: "mañana" }, { notice_since: "2026-11-21" }]) {
      expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 40, ...bad }, seeded)).toBe(TRIAL_RESERVE_CONFIG_MESSAGE);
    }
    expect(configFieldLabel("trial_reserve", "new_max")).toContain("Autos nuevos");
    expect(configFieldLabel("trial_reserve", "random_stock")).toContain("al azar");
    expect(configFieldLabel("trial_reserve", "notice_since")).toContain("desde");
  });
});

describe("freeResultQuota in new mode", () => {
  const trial: PlanLimits = { plan: "free", enforced: true, state: "trial", limits: {}, free_results_used: 42, free_results_limit: 50 };
  it("has no cap and never completes in legacy mode: the full quota is `reached`", () => {
    expect(freeResultQuota({ ...trial, free_new_used: 7, free_new_max: null })).toMatchObject({ newUsed: 7, newMax: null, complete: false });
    expect(freeResultQuota(trial)).toMatchObject({ newUsed: 0, newMax: null, complete: false });
    expect(freeResultQuota({ ...trial, free_results_used: 50 })).toMatchObject({ reached: true, complete: false });
  });
  it("completes at the cap on new results", () => {
    expect(freeResultQuota({ ...trial, free_new_used: 4, free_new_max: 5 })).toMatchObject({ newUsed: 4, newMax: 5, complete: false, reached: false });
    expect(freeResultQuota({ ...trial, free_new_used: 5, free_new_max: 5 })).toMatchObject({ complete: true, reached: false });
    // The quota filled before the cap was used (e.g. before the switch-on): reached, not complete.
    expect(freeResultQuota({ ...trial, free_results_used: 50, free_new_used: 1, free_new_max: 5 })).toMatchObject({ complete: false, reached: true });
    expect(freeResultQuota({ ...trial, free_results_used: 50, free_new_used: 5, free_new_max: 5 })).toMatchObject({ complete: true, reached: true });
    expect(freeResultQuota({ ...trial, free_new_used: 12, free_new_max: 5 })).toMatchObject({ complete: true, newUsed: 12 });
    // A cap of 0 never completes by itself: there is no «0 autos nuevos» to announce.
    expect(freeResultQuota({ ...trial, free_new_used: 0, free_new_max: 0 })?.complete).toBe(false);
  });
});

describe("the complete variant's copy", () => {
  it("says the cap, in the singular too", () => {
    expect(completeTitle(5)).toBe("Tu prueba ya te mostró 5 autos nuevos.");
    expect(completeTitle(1)).toBe("Tu prueba ya te mostró 1 auto nuevo.");
    expect(trialCompleteText(5)).toBe("Tu prueba ya te mostró sus 5 autos nuevos");
    expect(trialCompleteText(1)).toBe("Tu prueba ya te mostró su auto nuevo");
  });
  it("leads with what is hidden, or with what stops", () => {
    expect(text(completeLead(counts(45, 23)))).toBe("Desde ahora tu prueba no suma autos nuevos. Hay 23 más que coinciden con lo que pediste y siguen publicados.");
    expect(completeLead(counts(45, 23))).toContainEqual({ mark: "23" });
    expect(text(completeLead(counts(45, 1)))).toBe("Desde ahora tu prueba no suma autos nuevos. Hay 1 más que coincide con lo que pediste y sigue publicado.");
    expect(text(completeLead(counts(45, 0)))).toBe("Desde ahora tu prueba no suma autos nuevos.");
  });
  it("pays to see them all, or to keep receiving", () => {
    const price = planPrice(5000);
    expect(completePayLabel(counts(45, 23), 7, price)).toBe(`Ver los 68 · 7 días por ${price}`);
    expect(completePayLabel(counts(45, 0), 7, price)).toBe(`Seguir recibiendo · 7 días por ${price}`);
    expect(keepLabel(counts(45, 0))).toBe("Seguir con mis 45");
  });
  it("puts the cap and what is hidden on the strip", () => {
    expect(text(completeStripText(counts(45, 23), 5))).toBe("Tu prueba ya te mostró sus 5 autos nuevos. Hay 23 más que coinciden.");
    expect(text(completeStripText(counts(45, 1), 5))).toBe("Tu prueba ya te mostró sus 5 autos nuevos. Hay 1 más que coincide.");
    expect(text(completeStripText(counts(45, 0), 1))).toBe("Tu prueba ya te mostró su auto nuevo.");
    expect(COMPLETE_STRIP_BUTTON).toBe("Seguir recibiendo");
    expect(COMPLETE_BADGE).toBe("Prueba gratis completa");
  });
  it("doesn't call a random sample «los primeros»", () => {
    expect(cardLead(counts(45, 23), true)).toBe("Tu prueba muestra 45 de los 68. Con Particular los ves todos, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.");
    expect(cardLead(counts(1, 3), true)).toBe("Tu prueba muestra 1 de los 4. Con Particular los ves todos, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.");
    expect(cardLead(counts(0, 3), true)).toBe(cardLead(counts(0, 3)));
    expect(cardLead(counts(30, 48))).toContain("los primeros 30 que encontramos");
  });
  it("pass the copy rules", () => {
    const all = [completeTitle(5), completeTitle(1), trialCompleteText(5), trialCompleteText(1), COMPLETE_BADGE, COMPLETE_STRIP_BUTTON,
      text(completeLead(counts(45, 23))), text(completeLead(counts(45, 1))), text(completeLead(counts(45, 0))),
      text(completeStripText(counts(45, 23), 5)), completePayLabel(counts(45, 0), 7, "$ 5.000"), cardLead(counts(40, 38), true)];
    expect(forbiddenTermsIn(all.join(" "))).toEqual([]);
  });
});

describe("the complete variant's components", () => {
  const checkout = { offer: DEFAULT_PRO_OFFER, automatic: true };
  it("puts the complete strip on the page, with the sheet closed until the browser opens it", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer: counts(45, 23), autoOpen: true, checkout, complete: 5 }));
    expect(html).toContain('data-testid="trial-offer-strip"');
    expect(html).toContain('Tu prueba ya te mostró sus <b class="font-semibold">5</b> autos nuevos. Hay <b class="font-semibold">23</b> más que coinciden.');
    expect(html).toContain(">Seguir recibiendo</button>");
    expect(html).not.toContain("Ver todos");
    expect(html).not.toContain('data-testid="trial-offer-sheet"');
  });
  it("keeps the strip as it was without complete", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer: trialOffer(40, 38)!, autoOpen: false, checkout }));
    expect(html).toContain(">Ver todos</button>");
    expect(html).not.toContain("autos nuevos");
  });
  it("pays with the complete label when nothing is hidden", () => {
    const html = renderToStaticMarkup(createElement(TrialPassChoice, { offer: counts(45, 0), checkout, pending: false, error: null, onPay: vi.fn(), label: completePayLabel }));
    expect(html).toContain(`>Seguir recibiendo · 7 días por ${planPrice(DEFAULT_PRO_OFFER.pass_7.amount)}</button>`);
  });
  it("ends the list without «los primeros» with a random sample", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenCard, { profileId: 7, offer: trialOffer(40, 38)!, checkout, randomStock: true }));
    expect(html).toContain("Tu prueba muestra 40 de los 78.");
    expect(html).not.toContain("los primeros");
  });
  it("tells the preparation notice what happened, without «50 resultados»", () => {
    const html = renderToStaticMarkup(SearchPreparation({ email: "a@b.com", trialEnds: "5 nov 2026", trialComplete: 5 }));
    expect(html).toContain("tu prueba ya te mostró sus 5 autos nuevos, así que no vamos a avisarte de otros.");
    expect(html).not.toContain("50 resultados");
  });
});

describe("Planes and Términos in new mode", () => {
  it("say both numbers", () => {
    expect(resultsText(DEFAULT_PLAN_LIMITS.free, 40, 5)).toBe("Hasta 40 autos ya publicados y los próximos 5 autos nuevos que aparezcan durante la prueba");
    expect(resultsText(DEFAULT_PLAN_LIMITS.free, 40, 1)).toBe("Hasta 40 autos ya publicados y el próximo auto nuevo que aparezca durante la prueba");
    // Legacy: as before.
    expect(resultsText(DEFAULT_PLAN_LIMITS.free, 30, null)).toBe("Hasta 50 resultados en total durante la prueba, hasta 30 ya publicados y el resto, autos nuevos");
    expect(resultsText(DEFAULT_PLAN_LIMITS.pass, 40, 5)).toBe(resultsText(DEFAULT_PLAN_LIMITS.pass));
  });
});
