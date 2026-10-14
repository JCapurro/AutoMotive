import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/app/app/pro/billing-actions", () => ({ checkPayment: vi.fn(), stopSubscription: vi.fn() }));

import { BillingStatus } from "@/components/app/billing-status";
import { founderNote } from "./pro";

/** Precio fundador: the first Agencia subscriptions keep their price for six months. */
const subscription = {
  id: "c1", offer: "pro_monthly", amount: 75000, status: "authorized", init_point: null, next_payment_at: null,
  sync_error: null, created_at: "2026-10-14T15:00:00Z", founder_number: 3, founder_price_until: "2027-04-14T15:00:00Z",
};

describe("founderNote", () => {
  it("says the amount that stays fixed and until when, in Argentine time", () => {
    expect(founderNote(subscription)).toBe("Precio fundador: $ 75.000 por mes, fijo hasta el 14 de abril de 2027.");
    // 01:30 UTC is still the day before in Buenos Aires.
    expect(founderNote({ ...subscription, founder_price_until: "2027-04-15T01:30:00Z" })).toContain("14 de abril de 2027");
  });
  it("says nothing for other subscriptions", () => {
    expect(founderNote({ amount: 75000 })).toBeNull();
    expect(founderNote({ ...subscription, founder_number: null, founder_price_until: null })).toBeNull();
  });
});

describe("BillingStatus", () => {
  const render = (checkout: typeof subscription) => renderToStaticMarkup(createElement(BillingStatus, { checkout }));

  it("shows a founder its fixed price", () => {
    expect(render(subscription)).toContain("Precio fundador: $ 75.000 por mes, fijo hasta el 14 de abril de 2027.");
  });
  it("shows nothing to other subscriptions or after cancelling", () => {
    expect(render({ ...subscription, founder_number: null as unknown as number, founder_price_until: null as unknown as string })).not.toContain("Precio fundador");
    expect(render({ ...subscription, status: "cancelled" })).not.toContain("Precio fundador");
  });
});
