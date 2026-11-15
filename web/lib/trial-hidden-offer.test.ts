import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

// Oferta cuando la prueba oculta autos (docs/OFERTA_PRUEBA.md): what each piece says.
// What opens, when and how often is the browser's (e2e and the manual check).
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: vi.fn() }));
vi.mock("@/app/app/pro/actions", () => ({ trackTrialOffer: vi.fn() }));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));

import { TrialHiddenCard, TrialHiddenOffer, TrialPassChoice } from "@/components/app/trial-hidden-offer";
import { DEFAULT_PRO_OFFER, PASS_GUARANTEE, planPrice } from "./pro";
import { trialOffer } from "./trial-offer";

const offer = trialOffer(30, 48)!;
const checkout = { offer: DEFAULT_PRO_OFFER, automatic: true };

it("puts the strip on the page and keeps the sheet closed until the browser opens it", () => {
  const html = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer, autoOpen: true, checkout }));
  expect(html).toContain('data-testid="trial-offer-strip"');
  expect(html).toContain('Tu prueba muestra <b class="font-semibold">30</b> de los <b class="font-semibold">78</b> autos que coinciden.');
  expect(html).toContain(">Ver todos</button>");
  // Closed on the server: it opens after hydration, once (localStorage), never in the HTML.
  expect(html).not.toContain("Encontramos 78 autos");
  expect(html).not.toContain('data-testid="trial-offer-sheet"');
});

it("offers the 7 days first, the 30 one tap away, with the price from the offer and the guarantee once", () => {
  const prices = { ...DEFAULT_PRO_OFFER, pass_7: { ...DEFAULT_PRO_OFFER.pass_7, amount: 6789 } };
  const html = renderToStaticMarkup(createElement(TrialPassChoice, { offer, checkout: { offer: prices, automatic: true }, pending: false, error: null, onPay: vi.fn() }));
  expect(html).toMatch(/aria-pressed="true"[^>]*>7 días<\/button>/);
  expect(html).toMatch(/aria-pressed="false"[^>]*>30 días<\/button>/);
  expect(html).toContain(planPrice(6789));
  expect(html).toContain("pago único por 7 días");
  expect(html).toContain(`>Ver los 78 · 7 días por ${planPrice(6789)}</button>`);
  expect(html.split(PASS_GUARANTEE)).toHaveLength(2);
  expect(html).not.toContain(planPrice(15000));
});

it("shows the wait and the error where the button is", () => {
  const waiting = renderToStaticMarkup(createElement(TrialPassChoice, { offer, checkout, pending: true, error: null, onPay: vi.fn() }));
  expect(waiting).toContain(">Abriendo…</button>");
  expect(waiting).toMatch(/<button[^>]*disabled=""[^>]*>Abriendo…/);
  const failed = renderToStaticMarkup(createElement(TrialPassChoice, { offer, checkout, pending: false, error: "La oferta cambió.", onPay: vi.fn() }));
  expect(failed).toContain('<p role="alert" class="mt-2 text-sm text-destructive">La oferta cambió.</p>');
});

it("ends the list with what the trial doesn't show and both passes one tap from paying", () => {
  const html = renderToStaticMarkup(createElement(TrialHiddenCard, { profileId: 7, offer, checkout }));
  expect(html).toContain('data-testid="trial-hidden"');
  expect(html).toContain('Y <b class="mark">48</b> más que coinciden');
  expect(html).toContain("Tu prueba muestra los primeros 30 que encontramos. Con Particular ves los 78, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.");
  expect(html).toContain(`>Ver los 78 · 7 días por ${planPrice(5000)}</button>`);
  expect(html).toContain(`>30 días por ${planPrice(15000)}</button>`);
  expect(html.indexOf("7 días por")).toBeLessThan(html.indexOf("30 días por"));
  expect(html.split(PASS_GUARANTEE)).toHaveLength(2);
  expect(html).toContain('href="/terminos"');
  // Never a link to the plans page in place of the checkout (the grey line it replaces had one).
  expect(html).not.toContain("/app/pro");
});

it("doesn't promise Mercado Pago while payments are coordinated by hand", () => {
  const html = renderToStaticMarkup(createElement(TrialHiddenCard, { profileId: 7, offer, checkout: { offer: DEFAULT_PRO_OFFER, automatic: false } }));
  expect(html).not.toContain("Mercado Pago");
  expect(html).not.toContain("Términos y condiciones");
  expect(html).toContain("Coordinamos el pago y la activación.");
});

it("says it right with nothing shown: an empty list whose matches the trial hides", () => {
  const empty = trialOffer(0, 12)!;
  const card = renderToStaticMarkup(createElement(TrialHiddenCard, { profileId: 7, offer: empty, checkout }));
  expect(card).toContain('Hay <b class="mark">12</b> autos que coinciden');
  expect(card).toContain("Tu prueba no muestra ninguno.");
  const strip = renderToStaticMarkup(createElement(TrialHiddenOffer, { profileId: 7, offer: empty, autoOpen: true, checkout }));
  expect(strip).toContain('Tu prueba no muestra ninguno de los <b class="font-semibold">12</b> autos que coinciden.');
});
