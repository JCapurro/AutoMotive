import { expect, it } from "vitest";
import { CommercialOfferInput, PaymentInput, commercialError } from "./commercial";
import { DEFAULT_PRO_OFFER } from "./pro";

it("requires external verification and accepts only the two peso offers", () => {
  const payment = { userId: "00000000-0000-4000-8000-000000000001", offer: "pass_30", provider: "Mercado Pago", reference: "tx-123", paidAt: "2026-10-02T12:00:00Z", verified: true };
  expect(PaymentInput.safeParse(payment).success).toBe(true);
  expect(PaymentInput.safeParse({ ...payment, verified: false }).success).toBe(false);
  expect(PaymentInput.safeParse({ ...payment, offer: "pass_90" }).success).toBe(false);
  expect(PaymentInput.safeParse({ ...payment, userId: "otro" }).success).toBe(false);
  expect(commercialError("database password secret error")).not.toContain("secret");
  expect(CommercialOfferInput.safeParse(DEFAULT_PRO_OFFER).success).toBe(true);
  expect(CommercialOfferInput.safeParse({ ...DEFAULT_PRO_OFFER, pass_30: { amount: 15, currency: "USD", days: 30 } }).success).toBe(false);
});
