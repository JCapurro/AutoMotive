import { beforeEach, expect, it, vi } from "vitest";

vi.mock("next/cache", () => ({ refresh: vi.fn() }));
const mocks = vi.hoisted(() => ({ requireUser: vi.fn(), liveAccount: vi.fn(), createCheckout: vi.fn(), readAttribution: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: mocks.requireUser, liveAccount: mocks.liveAccount }));
vi.mock("@/lib/meta-capi", () => ({ readAttribution: mocks.readAttribution }));
vi.mock("@/lib/mercadopago-server", () => ({ createCheckout: mocks.createCheckout, cancelSubscription: vi.fn(), syncCheckout: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: vi.fn() }));

import { startPayment } from "@/app/app/pro/billing-actions";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.requireUser.mockResolvedValue({ id: "account", email: "account@example.com" });
  mocks.liveAccount.mockResolvedValue({ id: "account", email: "account@example.com", sessionId: "session", emailOnly: false });
  mocks.readAttribution.mockResolvedValue({ consent: false });
  mocks.createCheckout.mockResolvedValue("https://www.mercadopago.com.ar/checkout");
});

it.each([ ["pass_30", 15000], ["pro_monthly", 75000] ] as const)("uses the signed-in account email for %s", async (offer, amount) => {
  await expect(startPayment(offer, true, "ars-launch-2026-10", amount)).resolves.toHaveProperty("url");
  expect(mocks.createCheckout).toHaveBeenCalledWith("account", offer, "account@example.com", "ars-launch-2026-10", amount, { consent: false });
});

it("requires consent before creating a checkout", async () => {
  expect(await startPayment("pass_30", false, "ars-launch-2026-10", 15000)).toHaveProperty("error");
  expect(mocks.createCheckout).not.toHaveBeenCalled();
});

it("does not start checkout when the account has no usable email", async () => {
  mocks.liveAccount.mockResolvedValue({ id: "account", email: null, sessionId: "session", emailOnly: false });
  expect(await startPayment("pass_30", true, "ars-launch-2026-10", 15000)).toHaveProperty("error");
  expect(mocks.createCheckout).not.toHaveBeenCalled();
});

it("does not start checkout for a revoked session", async () => {
  mocks.liveAccount.mockResolvedValue(null);
  expect(await startPayment("pass_30", true, "ars-launch-2026-10", 15000)).toHaveProperty("error");
  expect(mocks.createCheckout).not.toHaveBeenCalled();
});

it("sends an email-only account (free search) to create its account before paying", async () => {
  mocks.liveAccount.mockResolvedValue({ id: "account", email: "account@example.com", sessionId: "session", emailOnly: true });
  expect(await startPayment("pass_30", true, "ars-launch-2026-10", 15000)).toEqual({ needsAccount: true });
  expect(mocks.createCheckout).not.toHaveBeenCalled();
});

it("maps the database's account_required backstop to the same step", async () => {
  mocks.createCheckout.mockRejectedValue(new Error("account_required"));
  expect(await startPayment("pass_30", true, "ars-launch-2026-10", 15000)).toEqual({ needsAccount: true });
});
