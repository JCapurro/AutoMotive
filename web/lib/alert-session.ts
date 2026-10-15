import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";

import { webConfig } from "@/lib/config";
import { claimThrottle, HOUR } from "@/lib/email-only";
import { track } from "@/lib/events";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Signed email links (docs/AUTENTICACION.md, «Links firmados»). An email-only
 * account has no password, and the browser it signed up in (often Instagram's)
 * doesn't share cookies with Gmail or Chrome. The worker signs the email links
 * that lead into the app (/r/<id>?to=detail, /m/<id>) with ALERT_LINK_SECRET
 * (worker/notifications/links.py), and those links sign the owner in here:
 * only a signed-out browser, only an email-only account, only an email sent
 * less than ALERT_LINK_MAX_AGE_DAYS ago. Everything else behaves as before.
 */

export const ALERT_LINK_MAX_AGE_DAYS = 7;
const MIN_SECRET_LENGTH = 32;
const SIGNATURE = /^[A-Za-z0-9_-]{22}$/;

/** "r": a notifications row (/r/<id>); "m": a lifecycle_emails row (/m/<id>). */
export type AlertLinkScope = "r" | "m";
export type AlertLink = { scope: AlertLinkScope; id: number; signature: string | null };

/** ALERT_LINK_SECRET, plus ALERT_LINK_SECRET_PREVIOUS while rotating. Shorter than 32 characters: ignored. */
export function alertLinkSecrets(env: Record<string, string | undefined> = process.env): string[] {
  return [env.ALERT_LINK_SECRET, env.ALERT_LINK_SECRET_PREVIOUS]
    .map((secret) => (secret ?? "").trim())
    .filter((secret) => secret.length >= MIN_SECRET_LENGTH);
}

/** HMAC-SHA256 of v1:<scope>:<id>:<user_id>, 128 bits, base64url: the same as worker/notifications/links.py. */
export function alertLinkSignature(secret: string, scope: AlertLinkScope, id: number, userId: string): string {
  return createHmac("sha256", secret).update(`v1:${scope}:${id}:${userId}`).digest().subarray(0, 16).toString("base64url");
}

export function validAlertLinkSignature(link: AlertLink, userId: string, secrets: string[] = alertLinkSecrets()): boolean {
  if (!link.signature || !SIGNATURE.test(link.signature)) return false;
  const given = Buffer.from(link.signature);
  return secrets.some((secret) => timingSafeEqual(given, Buffer.from(alertLinkSignature(secret, link.scope, link.id, userId))));
}

/** A path inside the app, the only place a signed link needs a session for. */
export function isAppPath(path: string): boolean {
  return /^\/app(?:[/?#]|$)/.test(path);
}

/** Within ALERT_LINK_MAX_AGE_DAYS of when the email went out (the database's clock, not the link's). */
export function recentlySent(sentAt: string | null, now = Date.now()): boolean {
  const sent = sentAt ? Date.parse(sentAt) : NaN;
  return Number.isFinite(sent) && now - sent < ALERT_LINK_MAX_AGE_DAYS * 86_400_000;
}

/** Who an email went to and when, if this row is one that went out by email. */
async function sentEmail(link: AlertLink): Promise<{ userId: string; sentAt: string | null } | null> {
  const admin = createAdminClient();
  if (link.scope === "r") {
    const { data } = await admin.from("notifications").select("user_id, channel, status, sent_at").eq("id", link.id).maybeSingle();
    return data?.channel === "email" && data.status === "sent" ? { userId: data.user_id, sentAt: data.sent_at } : null;
  }
  const { data } = await admin.from("lifecycle_emails").select("user_id, status, sent_at, target").eq("id", link.id).maybeSingle();
  return data?.status === "sent" && isAppPath(data.target) ? { userId: data.user_id, sentAt: data.sent_at } : null;
}

async function isEmailOnlyAccount(userId: string): Promise<boolean> {
  const { data } = await createAdminClient().from("profiles").select("email_only").eq("id", userId).maybeSingle();
  return data?.email_only === true;
}

/**
 * The email-only account this signed, recent email link may sign in on this
 * browser, or null: then the link behaves as it always did. Never for a
 * browser that already has a session, nor for a full account.
 */
export async function alertLinkOwner(link: AlertLink): Promise<string | null> {
  const secrets = alertLinkSecrets();
  if (!link.signature || !secrets.length) return null;
  const sent = await sentEmail(link);
  if (!sent || !recentlySent(sent.sentAt) || !validAlertLinkSignature(link, sent.userId, secrets)) return null;
  const { data: claims } = await (await createClient()).auth.getClaims();
  if (claims?.claims?.sub) return null;
  return (await isEmailOnlyAccount(sent.userId)) ? sent.userId : null;
}

/**
 * Signs this browser in as the link's owner the way the free search does
 * (generateLink + verifyOtp on the cookie client, no email goes out). It
 * records no inbox proof (account_proofs): this session can't choose a
 * password nor pay, and it closes nobody else's session. False, and the link
 * behaves as before, past the per-account brake or when anything doesn't add up.
 */
export async function signInFromAlertLink(userId: string, link: AlertLink): Promise<boolean> {
  try {
    const cfg = (await webConfig()).emailOnlySignup;
    if (!(await claimThrottle("alert_link_session", userId, cfg.alertSessionsPerUserHour, HOUR))) return false;
    const admin = createAdminClient();
    const { data: owner, error: ownerError } = await admin.auth.admin.getUserById(userId);
    const email = owner?.user?.email;
    if (ownerError || !email) throw new Error(`getUserById: ${ownerError?.message ?? "no email"}`);
    // Replaces the account's pending recovery token: a link to enter asked for earlier stops working.
    const generated = await admin.auth.admin.generateLink({ type: "magiclink", email });
    const tokenHash = generated.data?.properties?.hashed_token;
    if (generated.error || !tokenHash || generated.data.user?.id !== userId) throw new Error(`generateLink: ${generated.error?.message ?? "unexpected user"}`);
    const supabase = await createClient();
    const { data: verified, error } = await supabase.auth.verifyOtp({ type: "magiclink", token_hash: tokenHash });
    // Completed in between: a full account keeps going through the login.
    if (error || verified.user?.id !== userId || !(await isEmailOnlyAccount(userId))) {
      await supabase.auth.signOut({ scope: "local" });
      throw new Error(`verifyOtp: ${error?.message ?? "not an email-only session"}`);
    }
    await track(supabase, userId, "alert_link_signin", { link: link.scope, id: link.id });
    return true;
  } catch (error) {
    console.error("alert link sign-in skipped:", error instanceof Error ? error.message : error);
    return false;
  }
}

const escapeHtml = (value: string) =>
  value.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/**
 * What a signed link opens instead of a redirect: a page that posts itself
 * back to `action`, where the session starts. Link scanners that fetch the
 * URL without running scripts sign nobody in; the POST only counts from this
 * site (Origin). Without scripts, the button does it.
 */
export function continuePage(action: string): Response {
  const html = `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Ese Auto</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:16px;font-family:system-ui,sans-serif;text-align:center}button{font:inherit;margin-top:12px;padding:10px 20px;border:0;border-radius:8px;background:#111;color:#fff}</style>
</head><body><form method="post" action="${escapeHtml(action)}"><p>Abriendo Ese Auto…</p><button type="submit">Continuar</button></form>
<script>document.forms[0].submit()</script></body></html>`;
  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "private, no-store",
      // Same-origin keeps the signature out of other sites' logs and still lets the POST carry its Origin.
      "Referrer-Policy": "same-origin",
      "X-Robots-Tag": "noindex",
    },
  });
}

/** `path` plus the link's query, from parsed values only: the action of continuePage. */
export function signedAction(path: string, query: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value != null) params.set(key, String(value));
  return `${path}?${params}`;
}
