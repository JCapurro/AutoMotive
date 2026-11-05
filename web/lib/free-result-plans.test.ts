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
import { CUSTOM_PLAN, DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER, PASS_GUARANTEE, planPrice, proSummary } from "./pro";

const pro = DEFAULT_PLAN_LIMITS.pro;

it("offers Particular and Pro side by side, each with its price, terms and own button", () => {
  const offer = { ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: 23456 } };
  const html = renderToStaticMarkup(createElement(FreeResultPlans, { offer, automatic: true, pilot: true, pro }));
  // Particular opens on 30 days; the 7-day pass is one tap away on the duration toggle.
  expect(html).toContain(">Elegir Particular 30 días</button>");
  expect(html).toContain(">Elegir Pro</button>");
  expect(html).toMatch(/aria-pressed="true"[^>]*>30 días<\/button>/);
  expect(html).toMatch(/aria-pressed="false"[^>]*>7 días<\/button>/);
  expect(html).toContain(planPrice(23456));
  expect(html).toContain(planPrice(100000));
  expect(html).toContain("Pago único por 30 días");
  expect(html).toContain("Renovación mensual automática");
  expect(html).toContain("Para encontrar tu auto");
  expect(html).toContain("Para revender");
  expect(html).toContain("Hasta 20 búsquedas activas, margen estimado de reventa y filtro estricto de vendedor.");
  // The guarantee once, and both buttons on the last row of two boxes of the same subgrid.
  expect(html.split(PASS_GUARANTEE)).toHaveLength(2);
  expect(html.match(/row-span-7 grid grid-rows-subgrid/g)).toHaveLength(2);
  expect(html).toContain('href="/terminos"');
  expect(html).not.toContain("Ver planes");
  expect(html).not.toContain('type="radio"');
  expect(html).toContain(`href="${CUSTOM_PLAN.href.replaceAll("&", "&amp;")}"`);
  expect(html).toContain("Consultar Custom");
});

it("describes Pro from plan_limits, not fixed copy", () => {
  expect(proSummary({ ...pro, maxProfiles: 15, dealerMargin: false })).toBe("Hasta 15 búsquedas activas y filtro estricto de vendedor.");
  expect(proSummary({ ...pro, dealerMargin: false, sellerFilter: false })).toBe("Hasta 20 búsquedas activas.");
});

it("offers requests when automatic payments are disabled", () => {
  const html = renderToStaticMarkup(createElement(FreeResultPlans, { offer: DEFAULT_PRO_OFFER, automatic: false, pilot: true, pro }));
  expect(html).toContain(">Solicitar Particular 30 días</button>");
  expect(html).toContain(">Solicitar Pro</button>");
  expect(html).toContain("30 días · renovación manual");
  expect(html).not.toContain("Renovación mensual automática");
  expect(html).toContain("La solicitud no genera un cobro");
});

it("does not promise immediate enrollment while plans are still on the waitlist", () => {
  const html = renderToStaticMarkup(createElement(FreeResultPlans, { offer: DEFAULT_PRO_OFFER, automatic: false, pilot: false, pro }));
  expect(html).toContain(">Anotarme en Particular 30 días</button>");
  expect(html).toContain(">Anotarme en Pro</button>");
  expect(html).toContain("lista de espera");
});
