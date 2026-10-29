import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: vi.fn() }));
vi.mock("@/app/app/pro/actions", () => ({ joinWaitlist: vi.fn() }));
vi.mock("@/app/app/feedback/actions", () => ({ submitProductFeedback: vi.fn() }));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));

import { FreeResultPlans } from "@/components/app/free-result-limit";
import { CUSTOM_PLAN, DEFAULT_PRO_OFFER, planPrice } from "./pro";

it("offers a direct action for each plan with its current price and payment terms", () => {
  const offer = { ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: 23456 } };
  const html = renderToStaticMarkup(createElement(FreeResultPlans, { offer, automatic: true, pilot: true }));
  expect(html).toContain('aria-label="Elegir Particular"');
  expect(html).toContain('aria-label="Elegir Pro"');
  expect(html).toContain(planPrice(23456));
  expect(html).toContain("Pago único por 30 días");
  expect(html).toContain("Renovación mensual automática");
  expect(html).toContain('href="/terminos"');
  expect(html).not.toContain("Ver planes");
  expect(html).not.toContain('type="radio"');
  expect(html).toContain(`href="${CUSTOM_PLAN.href.replaceAll("&", "&amp;")}"`);
  expect(html).toContain("Consultar Custom");
});

it("offers requests when automatic payments are disabled", () => {
  const html = renderToStaticMarkup(createElement(FreeResultPlans, { offer: DEFAULT_PRO_OFFER, automatic: false, pilot: true }));
  expect(html).toContain('aria-label="Solicitar Particular"');
  expect(html).toContain('aria-label="Solicitar Pro"');
  expect(html).not.toContain("Renovación mensual automática");
  expect(html).toContain("La solicitud no genera un cobro");
});

it("does not promise immediate enrollment while plans are still on the waitlist", () => {
  const html = renderToStaticMarkup(createElement(FreeResultPlans, { offer: DEFAULT_PRO_OFFER, automatic: false, pilot: false }));
  expect(html).toContain('aria-label="Anotarme en Particular"');
  expect(html).toContain('aria-label="Anotarme en Pro"');
  expect(html).toContain("lista de espera");
});
