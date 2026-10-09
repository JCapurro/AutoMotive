import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ config: vi.fn(), waitlist: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: mocks.config }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn().mockResolvedValue({
    from: (table: string) => ({
      select: () => table === "pro_waitlist"
        ? { maybeSingle: mocks.waitlist }
        : { order: () => ({ limit: () => Promise.resolve({ data: [] }) }) },
    }),
  }),
}));
vi.mock("@/app/app/pro/actions", () => ({ joinWaitlist: vi.fn() }));
vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: vi.fn() }));
vi.mock("@/components/app/billing-status", () => ({ BillingStatus: () => null }));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));

import ProPage from "@/app/app/pro/page";
import { ProPlans } from "@/components/app/pro-plans";
import { PublicPlans } from "@/components/public-plans";
import { CUSTOM_PLAN, DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER, planPrice } from "@/lib/pro";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.waitlist.mockResolvedValue({ data: null });
});

const modes = [
  { automaticPayments: false, commercialPilot: false },
  { automaticPayments: false, commercialPilot: true },
  { automaticPayments: true, commercialPilot: true },
];

it.each(modes)("offers exactly the three paid plans from Adquirir plan in mode %j", async (mode) => {
  mocks.config.mockResolvedValue({ proOffer: DEFAULT_PRO_OFFER, planLimits: DEFAULT_PLAN_LIMITS, ...mode });
  const page = await ProPage({ searchParams: Promise.resolve({}), params: Promise.resolve({}) });
  const html = renderToStaticMarkup(page);
  expect(html.match(/type="radio"/g)).toHaveLength(3);
  for (const name of ["Particular", "Agencia", "Custom"]) expect(html).toContain(`>${name}</span>`);
  expect(html).toContain("A convenir");
  expect(html).not.toContain("Prueba gratis");
  expect(html).not.toContain('value="free"');
});

it.each(modes)("routes a selected Custom plan to a consultation in mode %j", async (mode) => {
  mocks.config.mockResolvedValue({ proOffer: DEFAULT_PRO_OFFER, planLimits: DEFAULT_PLAN_LIMITS, ...mode });
  mocks.waitlist.mockResolvedValue({ data: { plan: "pass_30" } });
  const page = await ProPage({ searchParams: Promise.resolve({ plan: "custom" }), params: Promise.resolve({}) });
  const html = renderToStaticMarkup(page);
  expect(html).toContain('checked="" value="custom"');
  expect(html).toContain('href="mailto:contacto@eseauto.com.ar?subject=');
  expect(html).toContain("Consultar Custom");
  expect(html).not.toContain('type="submit"');
  expect(html).not.toContain("Continuar en Mercado Pago");
  expect(html).not.toContain('data-testid="waitlist-joined"');
});

it("keeps Particular and Agencia prices tied to the configured offer", () => {
  const offer = { ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: 18000 } };
  const html = renderToStaticMarkup(createElement(ProPlans, { offer, limits: DEFAULT_PLAN_LIMITS, current: null, placement: "plans", automatic: true, recommended: "pro_monthly" }));
  expect(html).toContain(planPrice(18000));
  expect(html).toContain(planPrice(75000));
  expect(html).toContain('checked="" value="pro_monthly"');
  expect(html).toContain("Continuar en Mercado Pago");
});

it("describes the same negotiated Custom scope on public and acquisition pages", () => {
  const internal = renderToStaticMarkup(createElement(ProPlans, { offer: DEFAULT_PRO_OFFER, limits: DEFAULT_PLAN_LIMITS, current: null, placement: "plans", recommended: "custom" }));
  const publicHtml = renderToStaticMarkup(createElement(PublicPlans, { cfg: { proOffer: DEFAULT_PRO_OFFER, planLimits: DEFAULT_PLAN_LIMITS, automaticPayments: false, commercialPilot: true }, signedIn: false }));
  for (const html of [internal, publicHtml]) {
    for (const copy of [CUSTOM_PLAN.price, CUSTOM_PLAN.period, CUSTOM_PLAN.terms, ...CUSTOM_PLAN.features]) expect(html).toContain(copy);
  }
});

it("shows the phase 1 plan cards with the limits the backend applies", () => {
  const html = renderToStaticMarkup(createElement(PublicPlans, { cfg: { proOffer: DEFAULT_PRO_OFFER, planLimits: DEFAULT_PLAN_LIMITS, automaticPayments: true, commercialPilot: true }, signedIn: false }));
  for (const copy of [
    "por 3 días · sin tarjeta", "1 búsqueda activa", "Hasta 100 resultados", "Hasta 3 avisos inmediatos por día y resumen diario",
    "Las 72 horas empiezan al activar tu búsqueda. Una prueba por cuenta, sin cobro automático.",
    "por 30 días · pago único", "Seguí hasta tres opciones a la vez y recibí avisos para encontrar tu próximo auto.",
    "Hasta 3 búsquedas activas", "Hasta 10 avisos inmediatos por día y resumen diario", "Sin renovación automática.",
    "Para agencias y revendedores. Monitoreá más modelos y oportunidades de compra desde una misma cuenta.",
    "Hasta 20 búsquedas activas", "Hasta 50 avisos inmediatos por día y resumen diario",
    "Renovación mensual automática. Cancelás desde Ajustes y conservás el período pagado.",
    "Una búsqueda es un modelo, con sus versiones, años, kilómetros, presupuesto y zona. Si querés seguir varios modelos, cada uno cuenta como una búsqueda.",
    "Los avisos que pasan el tope del día van al resumen.",
    "Los precios pueden actualizarse. Si tu plan se renueva solo, te avisamos por mail 30 días antes.",
  ]) expect(html).toContain(copy);
  expect(html.match(/Todos los resultados disponibles/g)).toHaveLength(2);
  expect(html).not.toContain("Pricing");
});

it("follows app_config.plan_limits instead of fixed numbers", () => {
  const planLimits = { ...DEFAULT_PLAN_LIMITS, pro: { ...DEFAULT_PLAN_LIMITS.pro, maxProfiles: 15 }, free: { ...DEFAULT_PLAN_LIMITS.free, immediateAlertsPerDay: 0 } };
  const cfg = { proOffer: DEFAULT_PRO_OFFER, planLimits, automaticPayments: true, commercialPilot: true };
  const html = renderToStaticMarkup(createElement(PublicPlans, { cfg, signedIn: true }));
  expect(html).toContain("Hasta 15 búsquedas activas");
  expect(html).not.toContain("Hasta 20 búsquedas activas");
  expect(html).toContain("Resumen diario de coincidencias");
  const internal = renderToStaticMarkup(createElement(ProPlans, { offer: DEFAULT_PRO_OFFER, limits: planLimits, current: null, placement: "plans" }));
  expect(internal).toContain("Hasta 15 búsquedas activas · una cuenta");
  expect(internal).toContain("Hasta 3 búsquedas activas · una cuenta");
});
