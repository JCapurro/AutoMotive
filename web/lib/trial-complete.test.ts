import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

// Prueba de 50 publicaciones (docs/PRUEBA_COMPLETA.md): the switch's fields in
// /admin/config, the notice-mode copy and components before and after the
// quota fills. What opens and when is the browser's (manual check).
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: vi.fn() }));
vi.mock("@/app/app/pro/actions", () => ({ trackTrialOffer: vi.fn() }));
vi.mock("@/app/app/feedback/actions", () => ({ submitProductFeedback: vi.fn() }));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));

import { TrialHiddenCard, TrialHiddenOffer, TrialPassChoice } from "@/components/app/trial-hidden-offer";
import { TRIAL_RESERVE_CONFIG_MESSAGE, validateConfigChange, configFieldLabel } from "./admin-config";
import { forbiddenTermsIn } from "./copy";
import { DEFAULT_PRO_OFFER, freeResultQuota, planPrice, type PlanLimits } from "./pro";
import {
  cardLead, cardTitle, COMPLETE_BADGE, COMPLETE_STRIP_BUTTON, completeKeepLabel, completeLead, completePayLabel, completeStripText, completeTitle,
  keepLabel, NOTICE_KEEP_LABEL, noticeSheetLead, noticeSheetTitle, noticeStripText, payLabel, seeAllLabel, type Segment, trialOffer, type TrialOffer,
} from "./trial-offer";

const text = (segments: Segment[]) => segments.map((s) => (typeof s === "string" ? s : s.mark)).join("");
const counts = (shown: number, hidden: number): TrialOffer => ({ shown, hidden, total: shown + hidden });
const checkout = { offer: DEFAULT_PRO_OFFER, automatic: true };
const price = planPrice(DEFAULT_PRO_OFFER.pass_7.amount);

describe("trial_reserve in /admin/config", () => {
  it("takes random_stock and notice_since, and no new_max", () => {
    const seeded = { enabled: true, backfill_max: 30 };
    expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 45, random_stock: true, notice_since: "2026-11-21T12:00:00Z" }, seeded)).toBeNull();
    expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 45, notice_since: "2026-11-21T09:00:00-03:00" }, seeded)).toBeNull();
    for (const bad of [{ random_stock: "true" }, { notice_since: "mañana" }, { notice_since: "2026-11-21" }]) {
      expect(validateConfigChange("trial_reserve", { enabled: true, backfill_max: 45, ...bad }, seeded)).toBe(TRIAL_RESERVE_CONFIG_MESSAGE);
    }
    expect(TRIAL_RESERVE_CONFIG_MESSAGE).not.toContain("new_max");
    expect(configFieldLabel("trial_reserve", "random_stock")).toContain("al azar");
    expect(configFieldLabel("trial_reserve", "notice_since")).toContain("50 publicaciones");
  });
});

describe("freeResultQuota", () => {
  it("is used, limit, reached and stockLeft only: no count of new results", () => {
    const trial: PlanLimits = { plan: "free", enforced: true, state: "trial", limits: {}, free_results_used: 50, free_results_limit: 50 };
    expect(freeResultQuota(trial)).toEqual({ used: 50, limit: 50, reached: true, stockLeft: 0 });
  });
});

describe("notice mode before the quota fills", () => {
  it("says how many match, never what the trial shows", () => {
    expect(text(noticeStripText(counts(30, 48)))).toBe("Encontramos 78 autos que coinciden.");
    expect(noticeStripText(counts(30, 48))).toContainEqual({ mark: "78" });
    expect(text(noticeStripText(counts(0, 1)))).toBe("Encontramos 1 auto que coincide.");
    expect(noticeSheetTitle(counts(30, 48))).toBe("Encontramos 78 autos.");
    expect(noticeSheetTitle(counts(0, 1))).toBe("Encontramos 1 auto.");
    expect(text(noticeSheetLead(counts(30, 48)))).toBe("Con Particular los ves todos y te avisamos de los nuevos.");
    expect(text(noticeSheetLead(counts(0, 1)))).toBe("Con Particular lo ves y te avisamos de los nuevos.");
    expect(NOTICE_KEEP_LABEL).toBe("Ahora no");
    // Unchanged: the strip's button, the pay button and the card's title.
    expect(seeAllLabel(counts(30, 48))).toBe("Ver todos");
    expect(payLabel(counts(30, 48), 7, "$ 5.000")).toBe("Ver los 78 · 7 días por $ 5.000");
    expect(text(cardTitle(counts(30, 48)))).toBe("Y 48 más que coinciden");
  });
  it("leads the card with what Particular gives, in notice mode and with a random sample", () => {
    expect(cardLead(counts(45, 23), true)).toBe("Con Particular los ves todos y te avisamos de los nuevos.");
    expect(cardLead(counts(0, 1), true)).toBe("Con Particular lo ves y te avisamos de los nuevos.");
    // Legacy without a random sample: as on main.
    expect(cardLead(counts(30, 48))).toBe("Tu prueba muestra los primeros 30 que encontramos. Con Particular ves los 78, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.");
  });
  it("renders the strip with its texts and never opens by itself", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer: trialOffer(30, 48)!, autoOpen: true, checkout, notice: true }));
    expect(html).toContain('Encontramos <b class="font-semibold">78</b> autos que coinciden.');
    expect(html).toContain(">Ver todos</button>");
    expect(html).not.toContain("Tu prueba muestra");
    expect(html).not.toContain('data-testid="trial-offer-sheet"');
  });
  it("keeps the legacy strip without notice", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer: trialOffer(30, 48)!, autoOpen: false, checkout }));
    expect(html).toContain("Tu prueba muestra <b");
    expect(html).toContain(">Ver todos</button>");
    expect(keepLabel(counts(30, 48))).toBe("Seguir con mis 30");
  });
  it("ends the list with the plain lead", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenCard, { profileId: 7, offer: trialOffer(40, 38)!, checkout, plain: true }));
    expect(html).toContain("Con Particular los ves todos y te avisamos de los nuevos.");
    expect(html).not.toContain("Tu prueba muestra");
    expect(html).not.toContain("los primeros");
  });
});

describe("the complete variant (version A)", () => {
  it("says the limit, never a count of new cars or the stock", () => {
    expect(completeTitle(50)).toBe("Ya recibiste tus 50 publicaciones.");
    expect(text(completeLead())).toBe("¿Querés seguir recibiendo?");
    expect(completePayLabel(counts(45, 23), 7, "$ 5.000")).toBe("Seguir recibiendo · 7 días por $ 5.000");
    expect(completePayLabel(counts(45, 0), 7, "$ 5.000")).toBe("Seguir recibiendo · 7 días por $ 5.000");
    expect(completeKeepLabel()).toBe("Ahora no");
    expect(text(completeStripText(50))).toBe("Ya recibiste tus 50 publicaciones.");
    expect(COMPLETE_STRIP_BUTTON).toBe("Seguir recibiendo");
    expect(COMPLETE_BADGE).toBe("Prueba gratis completa");
  });
  it("puts the complete strip on the page, with the sheet closed until the browser opens it", () => {
    const html = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer: counts(45, 23), autoOpen: true, checkout, complete: 50 }));
    expect(html).toContain('Ya recibiste tus <b class="font-semibold">50</b> publicaciones.');
    expect(html).toContain(">Seguir recibiendo</button>");
    expect(html).not.toContain("Ver todos");
    expect(html).not.toContain("nuevos");
    expect(html).not.toContain('data-testid="trial-offer-sheet"');
  });
  it("pays with the complete label, hidden matches or not", () => {
    for (const offer of [counts(45, 23), counts(50, 0)]) {
      const html = renderToStaticMarkup(createElement(TrialPassChoice, { offer, checkout, pending: false, error: null, onPay: vi.fn(), label: completePayLabel }));
      expect(html).toContain(`>Seguir recibiendo · 7 días por ${price}</button>`);
    }
  });
  it("pass the copy rules", () => {
    const all = [completeTitle(50), text(completeLead()), completePayLabel(counts(45, 0), 7, "$ 5.000"), completeKeepLabel(), text(completeStripText(50)),
      COMPLETE_BADGE, COMPLETE_STRIP_BUTTON, text(noticeStripText(counts(30, 48))), noticeSheetTitle(counts(30, 48)), text(noticeSheetLead(counts(30, 48))),
      cardLead(counts(40, 38), true)];
    expect(forbiddenTermsIn(all.join(" "))).toEqual([]);
  });
});
