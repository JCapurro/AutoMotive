/** Uses the real billing code against a local, disposable Supabase stack.
 * Run with --env-file=.env.mercadopago-test.local --conditions=react-server --import tsx.
 * No card data, login secrets or provider response bodies are written to the report.
 */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { createAdminClient } from "../lib/supabase/admin";
import { cancelSubscription, createCheckout, syncCheckout } from "../lib/mercadopago-server";

const [command = "inspect", id] = process.argv.slice(2);
const accounts = ["particular@e2e.automotive.test", "agencia@e2e.automotive.test"];

function localOnly() {
  assert.equal(process.env.MERCADOPAGO_TEST_MODE, "true", "Set test mode in the isolated environment");
  const db = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "");
  assert.equal(db.hostname, "127.0.0.1", "Sandbox requires the dedicated local database");
  assert.equal(db.port, "55321", "Sandbox requires the dedicated test stack on 55321");
  const site = new URL(process.env.SITE_URL ?? "");
  assert(!["eseauto.com.ar", "www.eseauto.com.ar"].includes(site.hostname), "Production is not a test target");
}

async function provider(path: string, method = "GET", body?: unknown) {
  const res = await fetch(`https://api.mercadopago.com${path}`, {
    method, signal: AbortSignal.timeout(15000),
    headers: { Authorization: `Bearer ${process.env.MERCADOPAGO_ACCESS_TOKEN}`, "Content-Type": "application/json", "X-Idempotency-Key": randomUUID() },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  assert(res.ok, `Mercado Pago returned HTTP ${res.status}`);
  return res.json();
}

async function testMerchant() {
  const owner = await provider("/users/me");
  assert.equal(String(owner.id), process.env.MERCADOPAGO_COLLECTOR_ID, "Collector must match the credential owner");
  assert(owner.user_type === "test" || owner.tags?.includes("test_user"), "This credential does not belong to a test seller");
  return String(owner.id);
}

async function main() {
  localOnly();
  const db = createAdminClient();
  if (command === "prepare") {
    // Only this dedicated test stack is modified; the normal pilot stays disabled.
    const { error: configError } = await db.from("app_config").update({ value: { enabled: true } }).eq("key", "commercial_pilot");
    assert(!configError, "Could not enable the isolated commercial fixture");
    // The disposable stack intentionally does not load the market seed.
    const { error } = await db.from("app_config").upsert({ key: "plan_limits", value: {
      enforced: true,
      free: { max_profiles: 1, max_visible_results: 50, immediate_alerts: false },
      pass: { max_profiles: 3, immediate_alerts: true },
      pro: { max_profiles: 10, immediate_alerts: true },
    } });
    assert(!error, "Could not enable test limits");
    const { data: users, error: usersError } = await db.auth.admin.listUsers({ perPage: 1000 });
    assert(!usersError, "Could not read test accounts");
    for (const email of accounts) {
      if (!users.users.some((user) => user.email === email)) {
        const { error } = await db.auth.admin.createUser({ email, email_confirm: true });
        assert(!error, "Could not create the isolated account");
      }
    }
    console.log(JSON.stringify({ prepared: true, testAccounts: accounts }));
    return;
  }
  if (command === "inspect") {
    const { data: profiles, error: profilesError } = await db.from("profiles").select("id,email,plan,plan_expires_at");
    const { data: checkouts, error: checkoutError } = await db.from("billing_checkouts").select("id,user_id,offer,status,provider_id,last_synced_at,sync_error");
    const { data: payments, error: paymentError } = await db.from("commercial_payments").select("checkout_id,reference,amount,currency,period_start,period_end,refunded_at");
    assert(!profilesError && !checkoutError && !paymentError, "Could not inspect test billing");
    console.log(JSON.stringify({ profiles, checkouts, payments }, null, 2));
    return;
  }
  const collector = await testMerchant(); // Mandatory before every provider mutation or reconciliation.
  if (command === "checkout") {
    assert(id === "pass_30" || id === "pro_monthly", "Choose pass_30 or pro_monthly");
    const buyerEmail = process.env.MERCADOPAGO_TEST_BUYER_EMAIL;
    assert(buyerEmail && buyerEmail.endsWith("@testuser.com"), "Use the buyer's actual test email from Mercado Pago");
    const email = accounts[id === "pass_30" ? 0 : 1];
    const { data: user, error } = await db.from("profiles").select("id").eq("email", email).single();
    const { data: config, error: configError } = await db.from("app_config").select("value").eq("key", "pro_offer").single();
    assert(!error && user && !configError && config, "Run prepare first");
    const offer = config.value as { version: string; pass_30: { amount: number }; pro_monthly: { amount: number } };
    const url = await createCheckout(user.id, id, buyerEmail, offer.version, offer[id].amount);
    console.log(JSON.stringify({ offer: id, checkoutUrl: url }));
    return;
  }
  assert(id && /^[0-9a-f-]{36}$/i.test(id), "Supply a local checkout UUID");
  const { data: checkout, error } = await db.from("billing_checkouts").select("*").eq("id", id).single();
  assert(!error && checkout, "Checkout is missing from the isolated database");
  if (command === "reconcile") await syncCheckout(checkout);
  else if (command === "cancel") {
    await cancelSubscription(checkout);
    const { data, error } = await db.from("billing_checkouts").select("status").eq("id", id).single();
    assert(!error && data?.status === "cancelled", "Cancellation was not confirmed");
  } else if (command === "refund") {
    const paymentId = process.argv[4];
    assert(paymentId && /^\d+$/.test(paymentId), "Supply the approved test payment ID");
    const { data: paid, error } = await db.from("commercial_payments").select("id").eq("checkout_id", id).eq("reference", paymentId).maybeSingle();
    assert(!error && paid, "Payment must already belong to this checkout");
    const payment = await provider(`/v1/payments/${paymentId}`);
    assert.equal(String(payment.collector_id), collector);
    assert.equal(payment.live_mode, false, "Refusing to refund a live payment");
    assert.equal(payment.transaction_amount, checkout.amount);
    assert.equal(payment.currency_id, checkout.currency);
    assert.equal(payment.status, "approved");
    await provider(`/v1/payments/${paymentId}/refunds`, "POST", {});
    await syncCheckout(checkout);
    const { data: refunded, error: refundError } = await db.from("commercial_payments").select("refunded_at").eq("checkout_id", id).eq("reference", paymentId).single();
    assert(!refundError && refunded?.refunded_at, "Refund has not reached the local access ledger yet");
  } else if (command === "verify") {
    await syncCheckout(checkout);
    const { data: payments, error } = await db.from("commercial_payments").select("reference,period_start,period_end,refunded_at").eq("checkout_id", id);
    assert(!error && payments?.length, "No approved test payment has been recorded");
    for (const paid of payments) {
      const remote = await provider(`/v1/payments/${paid.reference}`);
      assert.equal(String(remote.collector_id), collector);
      assert.equal(remote.live_mode, false);
      assert.equal(Boolean(paid.refunded_at), ["refunded", "charged_back"].includes(remote.status));
      assert(["approved", "refunded", "charged_back"].includes(remote.status), "Payment is not approved or reversed");
      assert(new Date(paid.period_end) > new Date(paid.period_start), "Recorded access period must be positive");
    }
  } else throw new Error("Use prepare, inspect, checkout, reconcile, verify, cancel or refund");
  console.log(JSON.stringify({ action: command, checkoutId: id, verified: true }));
}

main().catch((error) => {
  // Assertions have fixed messages. Never dump SDK errors, provider bodies or tokens.
  console.error(error instanceof assert.AssertionError ? error.message : "Sandbox operation failed; inspect the local configuration and provider status");
  process.exitCode = 1;
});
