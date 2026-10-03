import "server-only";
import { z } from "zod";
import { checkoutUrl, paymentPeriod } from "@/lib/mercadopago";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Database } from "@/types/database";

export type BillingCheckout = Database["public"]["Tables"]["billing_checkouts"]["Row"];
const providerId = z.union([z.string().regex(/^[a-z0-9-]+$/i), z.number().int().positive()]).transform(String);
const money = z.coerce.number().positive();
const paymentSchema = z.object({ id: providerId, collector_id: providerId, status: z.string(), transaction_amount: money, currency_id: z.string(), external_reference: z.string().nullable().optional(), date_approved: z.string().nullable(), date_created: z.string(), live_mode: z.boolean(), payer: z.object({ id: providerId.nullable().optional() }).nullable().optional() });
const subscriptionSchema = z.object({ id: providerId, collector_id: providerId, external_reference: z.string().nullable(), status: z.enum(["pending", "authorized", "paused", "cancelled"]), init_point: z.string().nullable().optional(), next_payment_date: z.string().nullable().optional(), auto_recurring: z.object({ frequency: z.number(), frequency_type: z.string(), transaction_amount: money, currency_id: z.string(), free_trial: z.unknown().optional() }) });
const invoiceSchema = z.object({ id: providerId, preapproval_id: providerId, transaction_amount: money, currency_id: z.string(), debit_date: z.string(), payment: z.object({ id: providerId.nullable().optional() }).nullable().optional() });

export function paymentsConfigured() {
  return Boolean(process.env.MERCADOPAGO_ACCESS_TOKEN && process.env.MERCADOPAGO_WEBHOOK_SECRET && /^\d+$/.test(process.env.MERCADOPAGO_COLLECTOR_ID ?? "") && process.env.CRON_SECRET && process.env.SITE_URL?.startsWith("https://"));
}
export function paymentsEnabled() { return process.env.MERCADOPAGO_ENABLED === "true" && paymentsConfigured(); }

/** Fixed origin, short timeout, no provider body/token in logs or browser errors. */
async function api(path: string, method = "GET", body?: unknown, key?: string): Promise<unknown> {
  if (!paymentsConfigured()) throw new Error("payments_not_configured");
  const response = await fetch(`https://api.mercadopago.com${path}`, {
    method, cache: "no-store", signal: AbortSignal.timeout(4500),
    headers: { Authorization: `Bearer ${process.env.MERCADOPAGO_ACCESS_TOKEN}`, "Content-Type": "application/json", ...(key ? { "X-Idempotency-Key": key } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) throw new Error(`mercadopago_http_${response.status}`);
  return response.json();
}
function merchant(id: string) { if (id !== process.env.MERCADOPAGO_COLLECTOR_ID) throw new Error("merchant_mismatch"); }
function checkPrice(checkout: BillingCheckout, amount: number, currency: string) {
  if (amount !== checkout.amount || currency !== checkout.currency) throw new Error("payment_mismatch");
}
async function checkoutByReference(reference: string | null | undefined) {
  if (!reference || !z.uuid().safeParse(reference).success) return null;
  const { data, error } = await createAdminClient().from("billing_checkouts").select("*").eq("id", reference).maybeSingle();
  if (error) throw new Error("billing_database_error");
  return data;
}
async function saveCheckout(id: string, update: Database["public"]["Tables"]["billing_checkouts"]["Update"], terminalGuard = false, expectedStatus?: string) {
  let query = createAdminClient().from("billing_checkouts").update(update).eq("id", id);
  if (terminalGuard) query = query.neq("status", "cancelled");
  if (expectedStatus) query = query.eq("status", expectedStatus);
  const { error } = await query;
  if (error) throw new Error("billing_database_error");
}

export async function createCheckout(userId: string, offer: "pass_30" | "pro_monthly", email: string, version: string, amount: number) {
  if (!paymentsEnabled()) throw new Error("payments_not_configured");
  const { data, error } = await createAdminClient().rpc("begin_billing_checkout", { p_user: userId, p_offer: offer, p_email: email, p_version: version, p_expected_amount: amount });
  if (error) throw new Error(error.message.includes("offer_changed") ? "offer_changed" : error.message.includes("paid_plan_already_active") ? "paid_plan_already_active" : error.message.includes("checkout_already_open") ? "checkout_already_open" : "billing_database_error");
  const checkout = data as BillingCheckout & { new: boolean };
  if (checkout.init_point && ["pending", "creating"].includes(checkout.status)) {
    const url = checkoutUrl(checkout.init_point, process.env.MERCADOPAGO_TEST_MODE === "true");
    // Older rehearsals stored sandbox_init_point. Verify the existing preference
    // before repairing its redirect; never recreate the purchase or grant access.
    if (offer === "pass_30" && new URL(url).hostname === "sandbox.mercadopago.com.ar") {
      if (!checkout.provider_id) throw new Error("creation_needs_verification");
      return refreshPreferenceUrl(checkout, checkout.provider_id);
    }
    return url;
  }
  if (!checkout.new) throw new Error("checkout_in_progress");
  const site = new URL(process.env.SITE_URL!);
  const back = new URL("/app/pro?payment=returned", site).href;
  try {
    const body = offer === "pass_30" ? {
      items: [{ id: offer, title: "Ese Auto · Particular · 30 días", quantity: 1, unit_price: checkout.amount, currency_id: checkout.currency }],
      external_reference: checkout.id, payer: { email }, back_urls: { success: back, pending: back, failure: back }, auto_return: "approved",
      notification_url: new URL("/api/mercadopago/webhook", site).href,
    } : {
      reason: "Ese Auto · Agencia", external_reference: checkout.id, payer_email: email, status: "pending", back_url: back,
      auto_recurring: { frequency: 1, frequency_type: "months", transaction_amount: checkout.amount, currency_id: checkout.currency },
    };
    const result = await api(offer === "pass_30" ? "/checkout/preferences" : "/preapproval", "POST", body, checkout.id);
    const resource = z.object({ id: providerId, init_point: z.string(), sandbox_init_point: z.string().optional(), collector_id: providerId }).parse(result);
    merchant(resource.collector_id);
    // The hosted checkout uses init_point even with the automatic test seller.
    // Test mode still validates payment.live_mode; it does not select another UI.
    const url = checkoutUrl(resource.init_point);
    await saveCheckout(checkout.id, { provider_id: resource.id, init_point: url });
    // A notification can authorize/pay before the create response arrives. Don't downgrade it to pending.
    await saveCheckout(checkout.id, { status: "pending" }, true, "creating");
    return url;
  } catch (error) {
    // An uncertain create may already exist remotely: never create a second recurring subscription on retry.
    const message = error instanceof Error ? error.message : "checkout_error";
    if (/^mercadopago_http_4\d\d$/.test(message) && !message.endsWith("429") && !message.endsWith("408")) await saveCheckout(checkout.id, { status: "failed", sync_error: "creation_rejected" });
    else await saveCheckout(checkout.id, { sync_error: "creation_needs_verification" });
    throw new Error("checkout_creation_failed");
  }
}

async function subscription(id: string, cancelling = false) {
  providerId.parse(id);
  const resource = subscriptionSchema.parse(await api(`/preapproval/${id}`));
  merchant(resource.collector_id);
  const checkout = await checkoutByReference(resource.external_reference);
  if (!checkout) return null; // Generic links/other products never activate an arbitrary account.
  if (checkout.offer !== "pro_monthly" || (checkout.provider_id && checkout.provider_id !== resource.id)) throw new Error("subscription_mismatch");
  // Owner-verified cancellation must remain possible even if someone changed the remote price.
  if (!cancelling) {
    checkPrice(checkout, resource.auto_recurring.transaction_amount, resource.auto_recurring.currency_id);
    if (resource.auto_recurring.frequency !== 1 || resource.auto_recurring.frequency_type !== "months" || resource.auto_recurring.free_trial) throw new Error("subscription_period_mismatch");
  }
  await saveCheckout(checkout.id, { provider_id: resource.id, ...(resource.init_point ? { init_point: checkoutUrl(resource.init_point) } : {}), status: resource.status, next_payment_at: resource.next_payment_date ?? null }, true);
  return { checkout, resource };
}

async function applyPayment(raw: unknown, checkout: BillingCheckout, debitDate?: string) {
  const payment = paymentSchema.parse(raw);
  merchant(payment.collector_id);
  checkPrice(checkout, payment.transaction_amount, payment.currency_id);
  const testMode = process.env.MERCADOPAGO_TEST_MODE === "true";
  if (testMode && payment.live_mode) {
    // Automatic test users can produce live_mode=true on the normal hosted URL.
    // Accept that only for a provider-verified fictitious seller and the explicit
    // buyer fixture, never merely because the token has a particular prefix.
    const buyer = process.env.MERCADOPAGO_TEST_BUYER_ID;
    if (!buyer || !/^\d+$/.test(buyer) || payment.payer?.id !== buyer) throw new Error("payment_environment_mismatch");
    const owner = z.object({ id: providerId, tags: z.array(z.string()).optional(), user_type: z.string().optional() }).parse(await api("/users/me"));
    merchant(owner.id);
    if (!owner.tags?.includes("test_user") && owner.user_type !== "test") throw new Error("payment_environment_mismatch");
  } else if (payment.live_mode !== !testMode) throw new Error("payment_environment_mismatch");
  if (checkout.offer === "pass_30" && payment.external_reference !== checkout.id) throw new Error("payment_reference_mismatch");
  if (!["approved", "refunded", "charged_back"].includes(payment.status)) return;
  if (payment.status === "approved" && !payment.date_approved) throw new Error("invalid_payment_date");
  const paidAt = payment.date_approved ?? payment.date_created;
  const period = paymentPeriod(debitDate ?? paidAt, checkout.offer === "pro_monthly");
  const { error } = await createAdminClient().rpc("apply_mercadopago_payment", {
    p_checkout: checkout.id, p_reference: payment.id, p_status: payment.status, p_amount: payment.transaction_amount,
    p_currency: payment.currency_id, p_paid_at: paidAt, p_start: period.start, p_end: period.end,
  });
  if (error) throw new Error("payment_database_error");
}
async function invoicePayment(raw: unknown, knownCheckout?: BillingCheckout, knownPayment?: unknown) {
  const invoice = invoiceSchema.parse(raw);
  const linked = knownCheckout ? null : await subscription(invoice.preapproval_id);
  const checkout = knownCheckout ?? linked?.checkout;
  if (!checkout) return;
  if ((checkout.provider_id ?? linked?.resource.id) !== invoice.preapproval_id) throw new Error("invoice_subscription_mismatch");
  checkPrice(checkout, invoice.transaction_amount, invoice.currency_id);
  if (invoice.payment?.id) {
    const payment = knownPayment && paymentSchema.parse(knownPayment).id === invoice.payment.id ? knownPayment : await api(`/v1/payments/${invoice.payment.id}`);
    await applyPayment(payment, checkout, invoice.debit_date);
  }
}

/** Paginated reads also recover approvals/refunds when the notification is missed. */
async function searchPayments(checkout: BillingCheckout, deadline = Date.now() + 40000) {
  const monthly = checkout.offer === "pro_monthly";
  const path = monthly ? `/authorized_payments/search?preapproval_id=${checkout.provider_id}` : `/v1/payments/search?external_reference=${checkout.id}&sort=date_created&criteria=desc`;
  for (let offset = 0; offset < 1000;) {
    if (Date.now() > deadline) throw new Error("reconciliation_incomplete");
    // Invoice search rejects an explicit limit; paginate its default-sized pages.
    const page = z.object({ results: z.array(z.unknown()), paging: z.object({ total: z.number() }) }).parse(await api(`${path}&${monthly ? "" : "limit=100&"}offset=${offset}`));
    for (const item of page.results) {
      if (Date.now() > deadline) throw new Error("reconciliation_incomplete");
      if (monthly) {
        const summary = z.object({ id: providerId }).parse(item);
        await invoicePayment(await api(`/authorized_payments/${summary.id}`), checkout);
      } else {
        const summary = z.object({ id: providerId }).parse(item);
        await applyPayment(await api(`/v1/payments/${summary.id}`), checkout);
      }
    }
    if (offset + page.results.length >= page.paging.total) return;
    if (!page.results.length) throw new Error("reconciliation_incomplete");
    offset += page.results.length; // Some provider endpoints cap the requested page size.
  }
  // ponytail: cap historical scan at 1000 payments; flagged for manual review above that volume.
  throw new Error("reconciliation_incomplete");
}

async function refreshPreferenceUrl(checkout: BillingCheckout, id: string) {
  providerId.parse(id);
  const resource = z.object({ id: providerId, collector_id: providerId, external_reference: z.string(), init_point: z.string(), sandbox_init_point: z.string().optional(),
    items: z.array(z.object({ id: z.string(), quantity: z.number().int(), unit_price: money, currency_id: z.string() })) })
    .parse(await api(`/checkout/preferences/${id}`));
  merchant(resource.collector_id);
  if (resource.id !== id || resource.external_reference !== checkout.id || resource.items.length !== 1
    || resource.items[0].id !== "pass_30" || resource.items[0].quantity !== 1) throw new Error("preference_mismatch");
  checkPrice(checkout, resource.items[0].unit_price, resource.items[0].currency_id);
  const url = checkoutUrl(resource.init_point);
  await saveCheckout(checkout.id, { provider_id: resource.id, init_point: url });
  return url;
}

async function recoverPreference(checkout: BillingCheckout) {
  const page = z.object({ elements: z.array(z.object({ id: providerId, external_reference: z.string().nullable() })), total: z.number().int().nonnegative() })
    .parse(await api(`/checkout/preferences/search?external_reference=${encodeURIComponent(checkout.id)}`));
  const matches = page.elements.filter((item) => item.external_reference === checkout.id);
  if (matches.length !== 1 || page.total !== page.elements.length) throw new Error("creation_needs_verification");
  await refreshPreferenceUrl(checkout, matches[0].id);
  await saveCheckout(checkout.id, { status: "pending" }, true, "creating");
}

export async function syncCheckout(checkout: BillingCheckout, deadline?: number) {
  try {
    if (checkout.offer === "pass_30" && !checkout.provider_id) await recoverPreference(checkout);
    if (checkout.offer === "pro_monthly") {
      if (!checkout.provider_id) {
        // external_reference is not a documented preapproval search filter; verify exact references locally.
        const found = z.object({ results: z.array(z.object({ id: providerId, external_reference: z.string().nullable() })), paging: z.object({ total: z.number() }) })
          .parse(await api(`/preapproval/search?payer_email=${encodeURIComponent(checkout.billing_email)}&limit=100`));
        const matches = found.results.filter((item) => item.external_reference === checkout.id);
        if (matches.length !== 1 || found.paging.total > found.results.length) throw new Error("creation_needs_verification");
        const linked = await subscription(matches[0].id);
        if (!linked || linked.checkout.id !== checkout.id) throw new Error("subscription_mismatch");
        checkout = { ...checkout, provider_id: linked.resource.id };
      } else await subscription(checkout.provider_id);
    }
    await searchPayments(checkout, deadline);
    await saveCheckout(checkout.id, { last_synced_at: new Date().toISOString(), sync_error: null });
  } catch {
    await saveCheckout(checkout.id, { last_synced_at: new Date().toISOString(), sync_error: "verification_pending" });
    throw new Error("verification_pending");
  }
}

export async function handleNotification(topic: string, id: string) {
  providerId.parse(id);
  if (topic === "subscription_preapproval") { await subscription(id); return; }
  if (topic === "subscription_authorized_payment") { await invoicePayment(await api(`/authorized_payments/${id}`)); return; }
  if (topic === "payment") {
    const raw = await api(`/v1/payments/${id}`);
    const payment = paymentSchema.parse(raw);
    merchant(payment.collector_id);
    const checkout = await checkoutByReference(payment.external_reference);
    if (checkout?.offer === "pass_30") { await applyPayment(raw, checkout); return; }
    // Subscription payments may omit external_reference. The invoice supplies the verified ownership link.
    const found = z.object({ results: z.array(z.object({ id: providerId })), paging: z.object({ total: z.number() }) })
      .parse(await api(`/authorized_payments/search?payment_id=${payment.id}`));
    if (found.paging.total > found.results.length) throw new Error("reconciliation_incomplete");
    for (const item of found.results) await invoicePayment(await api(`/authorized_payments/${item.id}`), undefined, raw);
  }
}

export async function cancelSubscription(checkout: BillingCheckout) {
  if (checkout.offer !== "pro_monthly") throw new Error("not_a_subscription");
  if (!checkout.provider_id) { await syncCheckout(checkout); const fresh = await checkoutByReference(checkout.id); if (!fresh?.provider_id) throw new Error("verification_pending"); checkout = fresh; }
  const linked = await subscription(checkout.provider_id!, true);
  if (!linked || linked.checkout.user_id !== checkout.user_id) throw new Error("subscription_mismatch");
  if (linked.resource.status !== "cancelled") await api(`/preapproval/${checkout.provider_id}`, "PUT", { status: "cancelled" });
  const confirmed = await subscription(checkout.provider_id!, true);
  if (confirmed?.resource.status !== "cancelled") throw new Error("cancellation_unconfirmed");
}
