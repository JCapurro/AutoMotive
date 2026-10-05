import { beforeEach, expect, it, vi } from "vitest";

vi.mock("next/cache", () => ({ refresh: vi.fn() }));
const mocks = vi.hoisted(() => ({ requireUser: vi.fn(), createCheckout: vi.fn(), readAttribution: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: mocks.requireUser }));
vi.mock("@/lib/meta-capi", () => ({ readAttribution: mocks.readAttribution }));
vi.mock("@/lib/mercadopago-server", () => ({ createCheckout: mocks.createCheckout, cancelSubscription: vi.fn(), syncCheckout: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: vi.fn() }));

import { startPayment } from "@/app/app/pro/billing-actions";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.requireUser.mockResolvedValue({ id: "account", email: "account@example.com" });
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
  mocks.requireUser.mockResolvedValue({ id: "account", email: undefined });
  expect(await startPayment("pass_30", true, "ars-launch-2026-10", 15000)).toHaveProperty("error");
  expect(mocks.createCheckout).not.toHaveBeenCalled();
});
