"use server";

import { createHash } from "node:crypto";

import { z } from "zod";

import { ASSISTED_MAX_CHARS, ASSISTED_MIN_CHARS } from "@/lib/assisted";
import { currentUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { accountForEmail, claimThrottle, clientIpKey, DAY, type ExistingAccount, HOUR, linkError, sendEntryLink } from "@/lib/email-only";
import { HEALTH_OWNER_EMAIL } from "@/lib/health-access";
import { searchStartHref } from "@/lib/search-intent";
import { afterSignIn } from "@/lib/signup";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/** `resume`: the browser's random signup code (20261101130000_email_only_resume). */
export type FreeSearchInput = { prompt: string; email: string; company?: string; resume?: string };
/**
 * `signedUp`: a new account (the client counts it as a signup).
 * `existing_email_only` also covers a password signup that was never
 * confirmed (`unconfirmed`): the link confirms it and asks for a new password.
 * `existing_account`: the email has a password; the same pop-up asks for it.
 * `unavailable`: the brakes are on (or the switch is off). Nothing here opens the login.
 */
export type FreeSearchResult =
  | { status: "created"; href: string; signedUp: boolean }
  | { status: "unavailable"; error: string }
  | { status: "existing_email_only"; email: string; unconfirmed?: boolean; error?: string }
  | { status: "existing_account"; email: string }
  | { status: "error"; error: string; field?: "prompt" | "email" | "password" };

const Email = z.email().max(254);
const FAILED = "No pudimos crear tu búsqueda. Probá de nuevo en unos minutos.";
const UNAVAILABLE = "Ahora no podemos crear búsquedas nuevas. Probá de nuevo en unos minutos.";
/** The per-IP brakes count an hour; a shared connection (a phone carrier, an office) can hit them. */
const THROTTLED = "Hubo muchos intentos desde tu conexión en la última hora. Probá de nuevo más tarde o desde otra red (por ejemplo, Wi-Fi o datos del celular).";
const BAD_EMAIL = "Ese email no parece válido. Revisalo (por ejemplo: nombre@gmail.com).";
/** How long a reload during signup can still pick its session up (email_only_resume). */
const RESUME_WINDOW_SECONDS = 30 * 60;
/** Password attempts from the landing's pop-up, per IP and hour. */
const PASSWORD_TRIES_PER_HOUR = 10;

type Validated = { ok: true; email: string; href: string } | { ok: false; result: FreeSearchResult };

function validate(input: { prompt?: string; email?: string }): Validated {
  const prompt = String(input?.prompt ?? "").trim();
  if (prompt.length < ASSISTED_MIN_CHARS) return { ok: false, result: { status: "error", field: "prompt", error: "Contanos qué auto buscás." } };
  if (prompt.length > ASSISTED_MAX_CHARS) {
    return { ok: false, result: { status: "error", field: "prompt", error: `Usá menos de ${ASSISTED_MAX_CHARS} caracteres.` } };
  }
  const parsed = Email.safeParse(String(input?.email ?? "").trim().toLowerCase());
  if (!parsed.success) return { ok: false, result: { status: "error", field: "email", error: BAD_EMAIL } };
  return { ok: true, email: parsed.data, href: searchStartHref(true, prompt) };
}

/**
 * The free search's only step before the product: an email in a pop-up, no
 * password and no confirmation (docs/AUTENTICACION.md). A new email becomes
 * an email-only account signed in right here. An email that already exists
 * never gets a session from this alone: it gets a link to its inbox, or the
 * same pop-up asks for its password.
 */
export async function startFreeSearch(input: FreeSearchInput): Promise<FreeSearchResult> {
  // Bots fill every field; people never see this one.
  if (input?.company) return { status: "error", error: FAILED };
  const valid = validate(input);
  if (!valid.ok) return valid.result;
  const { email, href } = valid;
  const user = await currentUser();
  // A tab left open before signing in elsewhere: never drop the email typed here without saying so.
  if (user && user.email && user.email !== email) {
    return { status: "error", field: "email", error: `Ya entraste como ${user.email}. Para usar otro email, salí de esa cuenta desde Ajustes.` };
  }
  if (user) return { status: "created", href, signedUp: false };

  const cfg = (await webConfig()).emailOnlySignup;
  if (!cfg.enabled) return { status: "unavailable", error: UNAVAILABLE };

  try {
    const ip = await clientIpKey();
    if (!(await claimThrottle("free_search_lookup", ip, cfg.lookupsPerIpHour, HOUR))) return { status: "unavailable", error: THROTTLED };
    const existing = await accountForEmail(email);
    if (existing) {
      // The same browser coming back after a reload ate the signup's answer: its session, not a link.
      const resumed = existing.email_only ? await resumeSignup(existing.user_id, email, href, input.resume) : null;
      return resumed ?? await existingAccount(existing, email, href);
    }
    // The health dashboard trusts this address: it never becomes an unproven account.
    if (email === HEALTH_OWNER_EMAIL) return { status: "existing_account", email };
    if (!(await claimThrottle("free_search_signup_ip", ip, cfg.perIpHour, HOUR))) return { status: "unavailable", error: THROTTLED };
    if (!(await claimThrottle("free_search_signup_day", "global", cfg.perDay, DAY))) return { status: "unavailable", error: UNAVAILABLE };
    return await createEmailOnlyAccount(email, href, input.resume);
  } catch (error) {
    console.error("free search failed:", error instanceof Error ? error.message : error);
    return { status: "error", error: FAILED };
  }
}

/**
 * The email already has an account with a password: it signs in from the
 * same pop-up and the search goes on. Throttled per IP, on top of Auth's limits.
 */
export async function enterForFreeSearch(input: { prompt: string; email: string; password: string }): Promise<FreeSearchResult> {
  const valid = validate(input);
  if (!valid.ok) return valid.result;
  const password = String(input?.password ?? "");
  if (!password) return { status: "error", field: "password", error: "Escribí tu contraseña." };
  try {
    if (!(await claimThrottle("free_search_password", await clientIpKey(), PASSWORD_TRIES_PER_HOUR, HOUR))) {
      return { status: "error", field: "password", error: "Hiciste varios intentos. Pedí un link para entrar." };
    }
  } catch (error) {
    console.error("password throttle failed:", error instanceof Error ? error.message : error);
    return { status: "error", error: FAILED };
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email: valid.email, password });
  if (error) return { status: "error", field: "password", error: "La contraseña no coincide. Probá de nuevo o pedí un link para entrar." };
  await afterSignIn(supabase);
  return { status: "created", href: valid.href, signedUp: false };
}

/** "No me acuerdo la contraseña": the link to enter, from the same pop-up. Same answer whether or not the email has an account. */
export async function linkForFreeSearch(input: { prompt: string; email: string }): Promise<FreeSearchResult> {
  const valid = validate(input);
  if (!valid.ok) return valid.result;
  const result = await sendEntryLink(valid.email, valid.href);
  return result === "sent" ? { status: "existing_email_only", email: valid.email } : { status: "existing_email_only", email: valid.email, error: linkError(result) };
}

async function existingAccount(account: ExistingAccount, email: string, href: string): Promise<FreeSearchResult> {
  // A confirmed account with a password (or Google) signs in from the same pop-up.
  if (!account.email_only && account.confirmed) return { status: "existing_account", email };
  const unconfirmed = account.email_only ? {} : { unconfirmed: true };
  const result = await sendEntryLink(email, href, account);
  return result === "sent" ? { status: "existing_email_only", email, ...unconfirmed } : { status: "existing_email_only", email, ...unconfirmed, error: linkError(result) };
}

/** sha256 of the browser's signup code, or null for anything that isn't one. */
function resumeHash(code: unknown): string | null {
  return typeof code === "string" && /^[A-Za-z0-9_-]{22,64}$/.test(code) ? createHash("sha256").update(code).digest("hex") : null;
}

/** Signs this browser in as `userId` (a magic link verified right here, never mailed). */
async function startSession(email: string, userId: string): Promise<string | null> {
  const link = await createAdminClient().auth.admin.generateLink({ type: "magiclink", email });
  const tokenHash = link.data?.properties?.hashed_token;
  if (link.error || !tokenHash || link.data.user?.id !== userId) return `generateLink: ${link.error?.message ?? "unexpected user"}`;
  const supabase = await createClient();
  const { data: verified, error: verifyError } = await supabase.auth.verifyOtp({ type: "magiclink", token_hash: tokenHash });
  if (verifyError || verified.user?.id !== userId) {
    await supabase.auth.signOut({ scope: "local" });
    return `verifyOtp: ${verifyError?.message ?? "unexpected user"}`;
  }
  await afterSignIn(supabase, "email_only");
  return null;
}

/** The signup's own browser, back within the window with its code: the session again (once). Null otherwise. */
async function resumeSignup(userId: string, email: string, href: string, code: unknown): Promise<FreeSearchResult | null> {
  const hash = resumeHash(code);
  if (!hash) return null;
  const { data: claimed, error } = await createAdminClient().rpc("claim_email_only_resume", {
    p_user: userId, p_code_hash: hash, p_window_seconds: RESUME_WINDOW_SECONDS,
  });
  if (error || claimed !== true) return null;
  const failed = await startSession(email, userId);
  if (failed) {
    console.error("signup resume failed:", failed);
    return null;
  }
  return { status: "created", href, signedUp: true };
}

/**
 * Creates the account and signs this browser in without an email round trip.
 * The account is marked email-only before any session exists; if anything
 * fails before the session, the fresh account is deleted so a retry starts clean.
 * The browser's code (if any) is kept so a reload can pick the session up.
 */
async function createEmailOnlyAccount(email: string, href: string, code?: unknown): Promise<FreeSearchResult> {
  const admin = createAdminClient();
  const created = await admin.auth.admin.createUser({ email, email_confirm: true });
  const userId = created.data?.user?.id;
  if (created.error || !userId) {
    // Someone created it in between: from here on it's an existing email.
    const again = await accountForEmail(email);
    if (again) return existingAccount(again, email, href);
    throw new Error(`createUser: ${created.error?.message ?? "no user"}`);
  }
  const discard = async (reason: string) => {
    await admin.auth.admin.deleteUser(userId);
    throw new Error(reason);
  };
  const { data: marked, error: markError } = await admin.rpc("mark_email_only_account", { p_user: userId });
  if (markError || marked !== true) return discard(`mark_email_only_account: ${markError?.message ?? "not marked"}`);
  const hash = resumeHash(code);
  if (hash) {
    // Without it a reload only costs the inbox round trip it always did.
    const { error: saveError } = await admin.rpc("save_email_only_resume", { p_user: userId, p_code_hash: hash });
    if (saveError) console.error("save_email_only_resume failed:", saveError.message);
  }
  const failed = await startSession(email, userId);
  if (failed) return discard(failed);
  return { status: "created", href, signedUp: true };
}
