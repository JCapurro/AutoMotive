"use server";

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

export type FreeSearchInput = { prompt: string; email: string; company?: string };
/**
 * `signedUp`: a new account (the client counts it as a signup).
 * `existing_email_only` also covers a password signup that was never
 * confirmed (`unconfirmed`): the link confirms it and asks for a new password.
 */
export type FreeSearchResult =
  | { status: "created"; href: string; signedUp: boolean }
  | { status: "signup"; href: string }
  | { status: "existing_email_only"; email: string; unconfirmed?: boolean; error?: string }
  | { status: "existing_account"; href: string }
  | { status: "error"; error: string; field?: "prompt" | "email" };

const Email = z.email().max(254);
const FAILED = "No pudimos crear tu búsqueda. Probá de nuevo en unos minutos.";

/**
 * The free search's only step before the product: an email, no password and
 * no confirmation (docs/AUTENTICACION.md). A new email becomes an email-only
 * account signed in right here; an email that already exists never gets a
 * session from this form — it gets a link to its inbox, or the login.
 */
export async function startFreeSearch(input: FreeSearchInput): Promise<FreeSearchResult> {
  const prompt = String(input?.prompt ?? "").trim();
  const href = searchStartHref(true, prompt);
  // Bots fill every field; people never see this one.
  if (input?.company) return { status: "error", error: FAILED };
  if (prompt.length < ASSISTED_MIN_CHARS || prompt.length > ASSISTED_MAX_CHARS) {
    return { status: "error", field: "prompt", error: "Contanos qué auto buscás." };
  }
  const parsed = Email.safeParse(String(input?.email ?? "").trim().toLowerCase());
  if (!parsed.success) return { status: "error", field: "email", error: "Revisá tu email." };
  const email = parsed.data;
  if (await currentUser()) return { status: "created", href, signedUp: false };

  const cfg = (await webConfig()).emailOnlySignup;
  const signup = `/login?${new URLSearchParams({ mode: "signup", next: href })}`;
  if (!cfg.enabled) return { status: "signup", href: signup };

  try {
    const ip = await clientIpKey();
    // Many people share one mobile IP: past the brake, the regular signup still lets them in.
    if (!(await claimThrottle("free_search_lookup", ip, cfg.lookupsPerIpHour, HOUR))) return { status: "signup", href: signup };
    const existing = await accountForEmail(email);
    if (existing) return await existingAccount(existing, email, href);
    // The health dashboard trusts this address: it never becomes an unproven account.
    if (email === HEALTH_OWNER_EMAIL) return { status: "existing_account", href: `/login?${new URLSearchParams({ next: href })}` };
    // Past the brakes the free path closes and the regular signup takes over.
    if (!(await claimThrottle("free_search_signup_ip", ip, cfg.perIpHour, HOUR))
      || !(await claimThrottle("free_search_signup_day", "global", cfg.perDay, DAY))) {
      return { status: "signup", href: signup };
    }
    return await createEmailOnlyAccount(email, href);
  } catch (error) {
    console.error("free search failed:", error instanceof Error ? error.message : error);
    return { status: "error", error: FAILED };
  }
}

async function existingAccount(account: ExistingAccount, email: string, href: string): Promise<FreeSearchResult> {
  // A confirmed account with a password (or Google) logs in as usual.
  if (!account.email_only && account.confirmed) return { status: "existing_account", href: `/login?${new URLSearchParams({ next: href })}` };
  const unconfirmed = account.email_only ? {} : { unconfirmed: true };
  const result = await sendEntryLink(email, href, account);
  return result === "sent" ? { status: "existing_email_only", email, ...unconfirmed } : { status: "existing_email_only", email, ...unconfirmed, error: linkError(result) };
}

/**
 * Creates the account and signs this browser in without an email round trip.
 * The account is marked email-only before any session exists; if anything
 * fails before the session, the fresh account is deleted so a retry starts clean.
 */
async function createEmailOnlyAccount(email: string, href: string): Promise<FreeSearchResult> {
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
  const link = await admin.auth.admin.generateLink({ type: "magiclink", email });
  const tokenHash = link.data?.properties?.hashed_token;
  if (link.error || !tokenHash || link.data.user?.id !== userId) return discard(`generateLink: ${link.error?.message ?? "unexpected user"}`);
  const supabase = await createClient();
  const { data: verified, error: verifyError } = await supabase.auth.verifyOtp({ type: "magiclink", token_hash: tokenHash });
  if (verifyError || verified.user?.id !== userId) {
    await supabase.auth.signOut({ scope: "local" });
    return discard(`verifyOtp: ${verifyError?.message ?? "unexpected user"}`);
  }
  await afterSignIn(supabase, "email_only");
  return { status: "created", href, signedUp: true };
}
