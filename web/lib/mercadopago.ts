import { createHmac, timingSafeEqual } from "node:crypto";

export function sameSecret(a: string, b: string) {
  return Boolean(a && b) && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));
}

export function validWebhook(id: string, requestId: string, signature: string, secret: string) {
  const parts = Object.fromEntries(signature.split(",").map((part) => part.trim().split("=")));
  if (!/^[a-z0-9-]+$/i.test(id) || !requestId || !/^\d+$/.test(parts.ts ?? "") || !/^[a-f0-9]{64}$/i.test(parts.v1 ?? "") || !secret) return false;
  const digest = createHmac("sha256", secret).update(`id:${id.toLowerCase()};request-id:${requestId};ts:${parts.ts};`).digest("hex");
  return sameSecret(digest, parts.v1.toLowerCase());
}

export function checkoutUrl(value: string) {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || !["www.mercadopago.com.ar", "www.mercadopago.com"].includes(url.hostname)) throw new Error("invalid_checkout_url");
  return url.href;
}

/** Calendar month in the provider's billing timezone, clamping January 31 to February's last day. */
export function paymentPeriod(value: string, monthly: boolean) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) throw new Error("invalid_payment_date");
  if (!monthly) return { start: date.toISOString(), end: new Date(date.getTime() + 30 * 86400000).toISOString() };
  const offset = value.match(/([+-])(\d{2}):(\d{2})$/);
  const minutes = offset ? (offset[1] === "+" ? 1 : -1) * (Number(offset[2]) * 60 + Number(offset[3])) : 0;
  const local = new Date(date.getTime() + minutes * 60000);
  const day = local.getUTCDate();
  local.setUTCDate(1);
  local.setUTCMonth(local.getUTCMonth() + 1);
  local.setUTCDate(Math.min(day, new Date(Date.UTC(local.getUTCFullYear(), local.getUTCMonth() + 1, 0)).getUTCDate()));
  return { start: date.toISOString(), end: new Date(local.getTime() - minutes * 60000).toISOString() };
}
