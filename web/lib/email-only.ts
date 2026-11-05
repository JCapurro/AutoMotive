import "server-only";

import { createHmac } from "node:crypto";

import { headers } from "next/headers";

import { callbackUrl } from "@/lib/auth-links";
import { webConfig } from "@/lib/config";
import { RESET_PASSWORD_PATH, safeNext } from "@/lib/navigation";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Email-only accounts (docs/AUTENTICACION.md): the free search asks only for
 * an email. Everything here runs on the server with the service role; none of
 * it may ever give a session for an email that already exists.
 */

export const HOUR = 3600;
export const DAY = 86400;

export type ExistingAccount = { user_id: string; email_only: boolean; confirmed: boolean };

/** The auth account that owns this email (any case), or null. Service role only. */
export async function accountForEmail(email: string): Promise<ExistingAccount | null> {
  const { data, error } = await createAdminClient().rpc("auth_account_for_email", { p_email: email });
  if (error) throw new Error(`auth_account_for_email: ${error.message}`);
  return data?.[0] ?? null;
}

/**
 * Whether /login should ask this account for its password (option A,
 * 05/11): a confirmed full account that signed up with email and password.
 * Email-only accounts, unconfirmed signups and Google-only accounts enter with
 * the code. GoTrue doesn't say whether a password is set; the `email`
 * identity is what a password signup leaves (Google gives a `google` one).
 */
export async function hasPassword(account: ExistingAccount): Promise<boolean> {
  if (account.email_only || !account.confirmed) return false;
  const { data, error } = await createAdminClient().auth.admin.getUserById(account.user_id);
  if (error || !data.user) throw new Error(`getUserById: ${error?.message ?? "no user"}`);
  return (data.user.identities ?? []).some((identity) => identity.provider === "email");
}

/**
 * A new email-only account, marked before any session can exist. When the
 * email got an account in between, that one comes back as `existing` (the
 * caller treats it as an existing email). `discard` deletes the new one, for a
 * caller that fails before handing it over.
 */
export async function createEmailOnlyUser(email: string): Promise<{ userId: string; discard: (reason: string) => Promise<never> } | { existing: ExistingAccount }> {
  const admin = createAdminClient();
  const created = await admin.auth.admin.createUser({ email, email_confirm: true });
  const userId = created.data?.user?.id;
  if (created.error || !userId) {
    const existing = await accountForEmail(email);
    if (existing) return { existing };
    throw new Error(`createUser: ${created.error?.message ?? "no user"}`);
  }
  const discard = async (reason: string): Promise<never> => {
    await admin.auth.admin.deleteUser(userId);
    throw new Error(reason);
  };
  const { data: marked, error: markError } = await admin.rpc("mark_email_only_account", { p_user: userId });
  if (markError || marked !== true) return discard(`mark_email_only_account: ${markError?.message ?? "not marked"}`);
  return { userId, discard };
}

/** One more attempt of `kind` for `key` inside the window, or false past the limit (app_config.email_only_signup). */
export async function claimThrottle(kind: string, key: string, limit: number, windowSeconds: number): Promise<boolean> {
  const { data, error } = await createAdminClient().rpc("claim_auth_throttle", {
    p_kind: kind, p_key: key, p_limit: limit, p_window_seconds: windowSeconds,
  });
  if (error) throw new Error(`claim_auth_throttle: ${error.message}`);
  return data === true;
}

/**
 * The visitor's IP as a keyed hash: enough to rate-limit, nothing to store.
 * Vercel overwrites x-forwarded-for and x-real-ip. IPv6 is bucketed by /64,
 * the block one connection can rotate inside.
 */
export async function clientIpKey(): Promise<string> {
  const h = await headers();
  const ip = h.get("x-real-ip")?.trim() || (h.get("x-forwarded-for") ?? "").split(",")[0].trim();
  return ip ? createHmac("sha256", process.env.SUPABASE_SERVICE_ROLE_KEY ?? "").update(ipBucket(ip)).digest("hex").slice(0, 32) : "unknown";
}

export function ipBucket(ip: string): string {
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(ip);
  if (mapped) return mapped[1];
  if (!ip.includes(":")) return ip;
  const [head, tail = ""] = ip.toLowerCase().split("::");
  const left = head ? head.split(":") : [];
  const right = tail ? tail.split(":") : [];
  const groups = ip.includes("::") ? [...left, ...Array(Math.max(0, 8 - left.length - right.length)).fill("0"), ...right] : left;
  return `${groups.slice(0, 4).map((g) => g.replace(/^0+(?=.)/, "")).join(":")}::/64`;
}

export type LinkResult = "sent" | "throttled" | "busy" | "error";

/**
 * "Link para entrar": the recovery email, the one Auth template that works
 * from another browser. It proves the inbox; /auth/confirm then sends an
 * email-only account to /app/cuenta and a full account to the new password
 * form, both with `next`. Throttled per IP and per account (per hour, so
 * nobody can lock someone else out for long) to protect the shared email
 * quota and other people's inboxes. With no account behind the email nothing
 * is sent, and the caller answers as if it had been. If the brakes can't be
 * read the link still goes out: Auth's own per-email limit remains, and a
 * database hiccup must not lock people out of their accounts.
 */
export async function sendEntryLink(email: string, next: string, known?: ExistingAccount | null): Promise<LinkResult> {
  const cfg = (await webConfig()).emailOnlySignup;
  try {
    if (!(await claimThrottle("entry_link_ip", await clientIpKey(), cfg.linksPerIpHour, HOUR))) return "throttled";
    const account = known === undefined ? await accountForEmail(email) : known;
    if (!account) return "sent";
    if (!(await claimThrottle("entry_link_user", account.user_id, cfg.linksPerUserHour, HOUR))) return "throttled";
  } catch (error) {
    console.error("entry link throttle failed, sending anyway:", error instanceof Error ? error.message : error);
  }
  const reset = `${RESET_PASSWORD_PATH}?${new URLSearchParams({ next: safeNext(next) })}`;
  const supabase = await createClient();
  const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: await callbackUrl(reset) });
  if (!error) return "sent";
  return error.status === 429 ? "busy" : "error";
}

/** User-facing text for a link that could not be sent. A 429 doesn't mean one went out (Auth also limits right after signing up). */
export function linkError(result: Exclude<LinkResult, "sent">): string {
  if (result === "busy") return "Por seguridad no podemos mandarte emails tan seguido. Esperá un minuto y probá de nuevo; si ya te llegó uno, usá el último.";
  if (result === "throttled") return "Pediste varios códigos seguidos. Revisá tu email (y Spam) o probá de nuevo en una hora.";
  return "Estamos con demora para mandar emails. Probá de nuevo en unos minutos.";
}

/** Whether this session proved the inbox (or Google) in the last hour: the step before choosing a password. */
export async function hasFreshProof(userId: string, sessionId: string): Promise<boolean> {
  const since = new Date(Date.now() - HOUR * 1000).toISOString();
  const { data } = await createAdminClient()
    .from("account_proofs")
    .select("session_id")
    .eq("session_id", sessionId)
    .eq("user_id", userId)
    .gt("created_at", since)
    .maybeSingle();
  return Boolean(data);
}

/** Records that this session proved the inbox or Google; failures only cost the user one more link. */
export async function recordProof(userId: string, sessionId: string, method: "email_link" | "google"): Promise<void> {
  const { error } = await createAdminClient()
    .from("account_proofs")
    .upsert({ session_id: sessionId, user_id: userId, method, created_at: new Date().toISOString() });
  if (error) console.error("account proof not recorded:", error.message);
}
