import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: vi.fn() }));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { ExpiredMissed } from "@/components/app/expired-missed";
import { paymentPeriod } from "@/lib/mercadopago";
import { DEFAULT_PRO_OFFER, OFFER_TIER, planPrice, proOffer } from "@/lib/pro";
import { validateConfigChange } from "@/lib/admin-config";

const missed = { ended_at: "2026-10-29T15:00:00Z", found: 12, below: 3 };

it("tells an expired account what its searches found since, with both passes one click from paying", () => {
  const html = renderToStaticMarkup(createElement(ExpiredMissed, { missed, offer: DEFAULT_PRO_OFFER, automatic: true }));
  expect(html).toContain("Desde que venció tu acceso aparecieron 12 autos nuevos de tus búsquedas");
  expect(html).toContain("<b class=\"mark text-foreground\">3</b> están por debajo del precio de autos comparables.");
  expect(html).toContain(`Volver 7 días · ${planPrice(5000)}`);
  expect(html).toContain(`Volver 30 días · ${planPrice(15000)}`);
  expect(html).toContain("te devolvemos el 100 %");
  expect(html).toContain("Términos y condiciones");
});

it("says one car, and leaves out the comparables line with none below", () => {
  const html = renderToStaticMarkup(createElement(ExpiredMissed, { missed: { ...missed, found: 1, below: 0 }, offer: DEFAULT_PRO_OFFER, automatic: false }));
  expect(html).toContain("aparecieron 1 auto nuevo de tus búsquedas");
  expect(html).not.toContain("comparables");
  expect(html).not.toContain("Términos y condiciones");
});

it("reads the 7-day pass from app_config.pro_offer, only with its 7 days", () => {
  expect(OFFER_TIER.pass_7).toBe("pass");
  const offer = proOffer({ version: "v2", pass_7: { amount: 6000, currency: "ARS", days: 7 } });
  expect(offer.pass_7).toEqual({ amount: 6000, currency: "ARS", days: 7 });
  expect(proOffer({ pass_7: { amount: 6000, currency: "ARS", days: 30 } }).pass_7).toEqual(DEFAULT_PRO_OFFER.pass_7);
  expect(paymentPeriod("2026-11-05T12:00:00.000Z", false, 7).end).toBe("2026-11-12T12:00:00.000Z");
});

it("asks for a new offer version when the 7-day amount changes", () => {
  const current = { version: "v1", pass_30: DEFAULT_PRO_OFFER.pass_30, pass_7: DEFAULT_PRO_OFFER.pass_7, pro_monthly: DEFAULT_PRO_OFFER.pro_monthly };
  expect(validateConfigChange("pro_offer", { ...current, pass_7: { ...current.pass_7, amount: 6000 } }, current)).toMatch(/Cambiá la versión/);
  expect(validateConfigChange("pro_offer", { ...current, version: "v2", pass_7: { ...current.pass_7, amount: 6000 } }, current)).toBeNull();
  expect(validateConfigChange("pro_offer", { ...current, pass_7: { ...current.pass_7, days: 30 } }, current)).toMatch(/7 en el pase de 7 días/);
});
