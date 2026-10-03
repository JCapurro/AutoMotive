import { createHmac } from "node:crypto";
import { afterEach, expect, it, vi } from "vitest";
import { checkoutUrl, paymentPeriod, sameSecret, validWebhook } from "./mercadopago";

vi.mock("server-only", () => ({}));
const state = vi.hoisted(() => ({ checkout: { id: "00000000-0000-4000-8000-000000000001", user_id: "owner", offer: "pass_30", amount: 15000, currency: "ARS", provider_id: null as string | null, status: "pending", init_point: null }, updates: [] as unknown[], rpc: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: () => ({
  rpc: state.rpc,
  from: () => {
    const query = { select: () => query, eq: () => query, neq: () => query, update: (value: unknown) => { state.updates.push(value); return query; }, maybeSingle: async () => ({ data: state.checkout, error: null }), then: (resolve: (value: unknown) => void) => resolve({ error: null }) };
    return query;
  },
}) }));

function setup() {
  vi.stubEnv("MERCADOPAGO_ENABLED", "true"); vi.stubEnv("MERCADOPAGO_ACCESS_TOKEN", "private-test-token");
  vi.stubEnv("MERCADOPAGO_WEBHOOK_SECRET", "test-secret"); vi.stubEnv("MERCADOPAGO_COLLECTOR_ID", "200367138");
  vi.stubEnv("CRON_SECRET", "test-cron"); vi.stubEnv("SITE_URL", "https://eseauto.com.ar"); vi.stubEnv("MERCADOPAGO_TEST_MODE", "false");
  state.rpc.mockResolvedValue({ error: null, data: 1 }); state.updates.length = 0;
  state.checkout.offer = "pass_30"; state.checkout.amount = 15000; state.checkout.provider_id = null; state.checkout.status = "pending";
}
const payment = { id: 111, collector_id: 200367138, status: "approved", transaction_amount: 15000, currency_id: "ARS", external_reference: state.checkout.id, date_approved: "2026-10-02T10:00:00-03:00", date_created: "2026-10-02T09:00:00-03:00", live_mode: true };
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.clearAllMocks(); });

it("authenticates the signed ID/request and handles calendar month boundaries", () => {
  const manifest = "id:abc123;request-id:req-1;ts:1780000000000;";
  const signature = `ts=1780000000000,v1=${createHmac("sha256", "secret").update(manifest).digest("hex")}`;
  expect(validWebhook("ABC123", "req-1", signature, "secret")).toBe(true);
  expect(validWebhook("abc124", "req-1", signature, "secret")).toBe(false);
  expect(validWebhook("abc123", "req-2", signature, "secret")).toBe(false);
  expect(validWebhook("abc123", "req-1", signature, "wrong")).toBe(false);
  expect(sameSecret("", "")).toBe(false);
  expect(() => checkoutUrl("https://www.mercadopago.com.ar.evil.test/pay")).toThrow();
  expect(() => checkoutUrl("javascript:alert(1)")).toThrow();
  expect(paymentPeriod("2028-01-31T23:30:00-03:00", true).end).toBe("2028-03-01T02:30:00.000Z");
  expect(paymentPeriod("2027-01-31T23:30:00-03:00", true).end).toBe("2027-03-01T02:30:00.000Z");
  expect(paymentPeriod(payment.date_approved, false).end).toBe("2026-11-01T13:00:00.000Z");
});

it("uses the provider init_point with automatic test credentials and reuses it", async () => {
  setup(); vi.stubEnv("MERCADOPAGO_TEST_MODE", "true");
  const sandbox = "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref";
  const init = "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref";
  state.rpc.mockResolvedValueOnce({ error: null, data: { ...state.checkout, new: true } });
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ id: "test-pref", collector_id: 200367138, init_point: init, sandbox_init_point: sandbox }));
  vi.stubGlobal("fetch", fetcher);
  const { createCheckout } = await import("./mercadopago-server");
  await expect(createCheckout("owner", "pass_30", "buyer@example.com", "ars-launch-2026-10", 15000)).resolves.toBe(init);
  state.rpc.mockResolvedValueOnce({ error: null, data: { ...state.checkout, new: false, init_point: init } });
  await expect(createCheckout("owner", "pass_30", "buyer@example.com", "ars-launch-2026-10", 15000)).resolves.toBe(init);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(() => checkoutUrl(sandbox)).toThrow();
  expect(() => checkoutUrl("https://sandbox.mercadopago.com.ar.evil.test/pay", true)).toThrow();
});

it.each(["valid", "foreign seller", "foreign reference", "changed amount"])("verifies a cached sandbox preference before repairing the redirect: %s", async (scenario) => {
  setup(); vi.stubEnv("MERCADOPAGO_TEST_MODE", "true");
  const sandbox = "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref";
  const init = "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref";
  state.rpc.mockResolvedValueOnce({ error: null, data: { ...state.checkout, provider_id: "test-pref", new: false, init_point: sandbox } });
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({
    id: "test-pref", collector_id: scenario === "foreign seller" ? 99 : 200367138,
    external_reference: scenario === "foreign reference" ? "another-checkout" : state.checkout.id,
    init_point: init, sandbox_init_point: sandbox,
    items: [{ id: "pass_30", quantity: 1, unit_price: scenario === "changed amount" ? 1 : 15000, currency_id: "ARS" }],
  }));
  vi.stubGlobal("fetch", fetcher);
  const { createCheckout } = await import("./mercadopago-server");
  const result = createCheckout("owner", "pass_30", "buyer@example.com", "ars-launch-2026-10", 15000);
  if (scenario === "valid") {
    await expect(result).resolves.toBe(init);
    expect(state.updates).toEqual([{ provider_id: "test-pref", init_point: init }]);
  } else {
    await expect(result).rejects.toThrow();
    expect(state.updates).toHaveLength(0);
  }
  expect(fetcher).toHaveBeenCalledExactlyOnceWith("https://api.mercadopago.com/checkout/preferences/test-pref", expect.objectContaining({ method: "GET" }));
  expect(state.rpc).toHaveBeenCalledTimes(1); // Only reserves/reuses the local checkout; never applies payment.
});

it("fetches current payment; rejects foreign money, currency, environment and unsigned notifications", async () => {
  setup();
  const { handleNotification } = await import("./mercadopago-server");
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  for (const invalid of [{ collector_id: 9 }, { transaction_amount: 1 }, { currency_id: "USD" }, { live_mode: false }]) {
    fetcher.mockResolvedValueOnce(Response.json({ ...payment, ...invalid }));
    await expect(handleNotification("payment", "111")).rejects.toThrow();
  }
  expect(state.rpc).not.toHaveBeenCalled();
  fetcher.mockResolvedValueOnce(Response.json({ ...payment, status: "pending" }));
  await handleNotification("payment", "111"); expect(state.rpc).not.toHaveBeenCalled();
  fetcher.mockResolvedValueOnce(Response.json(payment)); await handleNotification("payment", "111");
  expect(state.rpc).toHaveBeenCalledWith("apply_mercadopago_payment", expect.objectContaining({ p_checkout: state.checkout.id, p_reference: "111", p_status: "approved", p_end: "2026-11-01T13:00:00.000Z" }));
  const { POST } = await import("@/app/api/mercadopago/webhook/route");
  fetcher.mockClear();
  expect((await POST(new Request("https://eseauto.com.ar/api/mercadopago/webhook?data.id=111", { method: "POST", body: JSON.stringify({ type: "payment", data: { id: 111 } }) }))).status).toBe(401);
  expect(fetcher).not.toHaveBeenCalled();
});

it("authorization grants nothing; invoice approval grants one calendar month; cancellation confirms remotely", async () => {
  setup(); state.checkout.offer = "pro_monthly"; state.checkout.amount = 75000; state.checkout.provider_id = "abc123";
  const sub = { id: "abc123", collector_id: 200367138, external_reference: state.checkout.id, status: "authorized", init_point: "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=abc123", auto_recurring: { frequency: 1, frequency_type: "months", transaction_amount: 75000, currency_id: "ARS" } };
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json(sub)); vi.stubGlobal("fetch", fetcher);
  const { handleNotification, cancelSubscription } = await import("./mercadopago-server");
  await handleNotification("subscription_preapproval", "abc123"); expect(state.rpc).not.toHaveBeenCalled();
  fetcher.mockResolvedValueOnce(Response.json({ id: 333, preapproval_id: "abc123", transaction_amount: "75000", currency_id: "ARS", debit_date: "2026-10-02T10:00:00-03:00", payment: { id: 111 } }))
    .mockResolvedValueOnce(Response.json(sub)).mockResolvedValueOnce(Response.json({ ...payment, transaction_amount: 75000, external_reference: null }));
  await handleNotification("subscription_authorized_payment", "333");
  expect(state.rpc).toHaveBeenCalledWith("apply_mercadopago_payment", expect.objectContaining({ p_end: "2026-11-02T13:00:00.000Z" }));
  fetcher.mockResolvedValueOnce(Response.json(sub)).mockResolvedValueOnce(Response.json({ status: "cancelled" })).mockResolvedValueOnce(Response.json({ ...sub, status: "cancelled" }));
  await cancelSubscription(state.checkout as Parameters<typeof cancelSubscription>[0]);
  expect(fetcher).toHaveBeenCalledWith("https://api.mercadopago.com/preapproval/abc123", expect.objectContaining({ method: "PUT", body: '{"status":"cancelled"}' }));
  expect(state.updates).toContainEqual(expect.objectContaining({ status: "cancelled" }));
  fetcher.mockResolvedValueOnce(Response.json(sub)).mockResolvedValueOnce(new Response(null, { status: 500 }));
  await expect(cancelSubscription(state.checkout as Parameters<typeof cancelSubscription>[0])).rejects.toThrow();
});

it("binds checkout to the authenticated owner and reuses it without a second remote subscription", async () => {
  setup(); state.checkout.offer = "pro_monthly"; state.checkout.amount = 75000; state.checkout.status = "creating";
  state.rpc.mockResolvedValueOnce({ error: null, data: { ...state.checkout, new: true } });
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ id: "abc123", collector_id: 200367138, init_point: "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=abc123" }));
  vi.stubGlobal("fetch", fetcher);
  const { createCheckout } = await import("./mercadopago-server");
  await createCheckout("owner", "pro_monthly", "buyer@example.com", "ars-launch-2026-10", 75000);
  expect(state.rpc).toHaveBeenCalledWith("begin_billing_checkout", { p_user: "owner", p_offer: "pro_monthly", p_email: "buyer@example.com", p_version: "ars-launch-2026-10", p_expected_amount: 75000 });
  const body = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(body).toMatchObject({ status: "pending", external_reference: state.checkout.id, auto_recurring: { frequency: 1, frequency_type: "months", transaction_amount: 75000, currency_id: "ARS" } });
  expect(body).not.toHaveProperty("card_token_id");
  state.rpc.mockResolvedValueOnce({ error: null, data: { ...state.checkout, status: "pending", new: false, init_point: "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=abc123" } });
  await createCheckout("owner", "pro_monthly", "buyer@example.com", "ars-launch-2026-10", 75000);
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("recovers an existing preference after an uncertain create without charging or granting access", async () => {
  setup(); vi.stubEnv("MERCADOPAGO_TEST_MODE", "true"); state.checkout.status = "creating";
  const preference = { id: "test-pref", collector_id: 200367138, external_reference: state.checkout.id,
    init_point: "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref", sandbox_init_point: "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref",
    items: [{ id: "pass_30", quantity: 1, unit_price: 15000, currency_id: "ARS" }] };
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ elements: [{ id: preference.id, external_reference: state.checkout.id }], total: 1 }))
    .mockResolvedValueOnce(Response.json(preference)).mockResolvedValueOnce(Response.json({ results: [], paging: { total: 0 } }));
  vi.stubGlobal("fetch", fetcher);
  const { syncCheckout } = await import("./mercadopago-server");
  await syncCheckout(state.checkout as Parameters<typeof syncCheckout>[0]);
  expect(state.updates).toContainEqual({ provider_id: "test-pref", init_point: preference.init_point });
  expect(state.updates).toContainEqual({ status: "pending" });
  expect(state.rpc).not.toHaveBeenCalled();
  expect(fetcher.mock.calls.every((call) => !call[1].method || call[1].method === "GET")).toBe(true);
});

it.each(["valid", "real seller", "different seller", "different buyer", "missing buyer fixture"])("checks provider identity for modern fictitious payments reported as live: %s", async (scenario) => {
  setup(); vi.stubEnv("MERCADOPAGO_TEST_MODE", "true");
  vi.stubEnv("MERCADOPAGO_TEST_BUYER_ID", scenario === "missing buyer fixture" ? "" : "3735031842");
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ ...payment, payer: { id: scenario === "different buyer" ? "99" : "3735031842" } }))
    .mockResolvedValueOnce(Response.json({ id: scenario === "different seller" ? 99 : 200367138, user_type: "normal", tags: scenario === "real seller" ? ["normal"] : ["test_user"] }));
  vi.stubGlobal("fetch", fetcher);
  const { handleNotification } = await import("./mercadopago-server");
  const result = handleNotification("payment", "111");
  if (scenario === "valid") {
    await expect(result).resolves.toBeUndefined();
    expect(state.rpc).toHaveBeenCalledWith("apply_mercadopago_payment", expect.objectContaining({ p_reference: "111", p_status: "approved" }));
    expect(fetcher).toHaveBeenCalledWith("https://api.mercadopago.com/users/me", expect.objectContaining({ method: "GET" }));
  } else {
    await expect(result).rejects.toThrow();
    expect(state.rpc).not.toHaveBeenCalled();
  }
});

it.each([
  { collector_id: 99, external_reference: "00000000-0000-4000-8000-000000000001", price: 15000 },
  { collector_id: 200367138, external_reference: "00000000-0000-4000-8000-000000000002", price: 15000 },
  { collector_id: 200367138, external_reference: "00000000-0000-4000-8000-000000000001", price: 1 },
])("does not recover a foreign preference or a changed offer: %j", async (invalid) => {
  setup(); state.checkout.status = "creating";
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ elements: [{ id: "test-pref", external_reference: state.checkout.id }], total: 1 }))
    .mockResolvedValueOnce(Response.json({ id: "test-pref", ...invalid,
      init_point: "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=test-pref",
      items: [{ id: "pass_30", quantity: 1, unit_price: invalid.price, currency_id: "ARS" }] }));
  vi.stubGlobal("fetch", fetcher);
  const { syncCheckout } = await import("./mercadopago-server");
  await expect(syncCheckout(state.checkout as Parameters<typeof syncCheckout>[0])).rejects.toThrow("verification_pending");
  expect(state.rpc).not.toHaveBeenCalled();
  expect(state.updates).not.toContainEqual(expect.objectContaining({ provider_id: "test-pref" }));
});

it("recovers a missed invoice and revokes refunded payments with no external reference", async () => {
  setup(); state.checkout.offer = "pro_monthly"; state.checkout.amount = 75000; state.checkout.provider_id = "abc123";
  const sub = { id: "abc123", collector_id: 200367138, external_reference: state.checkout.id, status: "authorized", init_point: null, auto_recurring: { frequency: 1, frequency_type: "months", transaction_amount: 75000, currency_id: "ARS" } };
  const invoice = { id: 333, preapproval_id: "abc123", transaction_amount: 75000, currency_id: "ARS", debit_date: payment.date_approved, payment: { id: 111 } };
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json(sub)).mockResolvedValueOnce(Response.json({ results: [{ id: 333 }], paging: { total: 1 } }))
    .mockResolvedValueOnce(Response.json(invoice)).mockResolvedValueOnce(Response.json({ ...payment, transaction_amount: 75000, external_reference: null }));
  vi.stubGlobal("fetch", fetcher);
  const { syncCheckout, handleNotification } = await import("./mercadopago-server");
  await syncCheckout(state.checkout as Parameters<typeof syncCheckout>[0]);
  expect(state.rpc).toHaveBeenCalledWith("apply_mercadopago_payment", expect.objectContaining({ p_reference: "111", p_status: "approved" }));
  state.rpc.mockClear();
  fetcher.mockResolvedValueOnce(Response.json({ ...payment, transaction_amount: 75000, external_reference: null, status: "refunded" }))
    .mockResolvedValueOnce(Response.json({ results: [{ id: 333 }], paging: { total: 1 } })).mockResolvedValueOnce(Response.json(invoice)).mockResolvedValueOnce(Response.json(sub));
  await handleNotification("payment", "111");
  expect(state.rpc).toHaveBeenCalledWith("apply_mercadopago_payment", expect.objectContaining({ p_reference: "111", p_status: "refunded" }));
  expect(fetcher).toHaveBeenCalledWith("https://api.mercadopago.com/authorized_payments/search?payment_id=111", expect.anything());
});

it("paginates invoice search with the provider default and never grants access for unpaid invoices", async () => {
  setup(); state.checkout.offer = "pro_monthly"; state.checkout.amount = 75000; state.checkout.provider_id = "abc123";
  const offsets: number[] = [];
  const fetcher = vi.fn(async (input: string) => {
    const url = new URL(input);
    if (url.pathname === "/preapproval/abc123") return Response.json({ id: "abc123", collector_id: 200367138, external_reference: state.checkout.id, status: "authorized", auto_recurring: { frequency: 1, frequency_type: "months", transaction_amount: 75000, currency_id: "ARS" } });
    if (url.pathname === "/authorized_payments/search") {
      if (url.searchParams.has("limit")) return Response.json({ message: "Invalid value for limit" }, { status: 400 });
      const offset = Number(url.searchParams.get("offset")); offsets.push(offset);
      return Response.json({ results: Array.from({ length: offset === 0 ? 12 : 1 }, (_, i) => ({ id: `invoice-${offset + i}` })), paging: { total: 13, limit: 12 } });
    }
    return Response.json({ id: url.pathname.split("/").at(-1), preapproval_id: "abc123", transaction_amount: 75000, currency_id: "ARS", debit_date: payment.date_approved, payment: null });
  });
  vi.stubGlobal("fetch", fetcher);
  const { syncCheckout } = await import("./mercadopago-server");
  await syncCheckout(state.checkout as Parameters<typeof syncCheckout>[0]);
  expect(offsets).toEqual([0, 12]);
  expect(fetcher).toHaveBeenCalledTimes(16); // Subscription, two pages, thirteen unpaid invoices.
  expect(state.rpc).not.toHaveBeenCalled();
});
