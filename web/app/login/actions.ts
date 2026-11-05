"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { callbackUrl } from "@/lib/auth-links";
import { webConfig } from "@/lib/config";
import { accountForEmail, claimThrottle, clientIpKey, createEmailOnlyUser, DAY, type ExistingAccount, hasPassword, HOUR, linkError, sendEntryLink } from "@/lib/email-only";
import { verifyEntryCode } from "@/lib/entry-code";
import { HEALTH_OWNER_EMAIL } from "@/lib/health-access";
import { safeNext } from "@/lib/navigation";
import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";

/**
 * One screen to enter (docs/AUTENTICACION.md), email first (option A, Juan
 * 05/11): «Continuar» looks the email up and goes on with what that account
 * uses: its password if it has one, the code otherwise (a new email gets an
 * account with it). Google is the other way. This shows whether an email has a
 * password; Juan accepted that, with the lookups braked per IP.
 * `step` is the screen to show; `notice` says why we sent a code the person
 * didn't ask for (the email has no password yet, or was never confirmed).
 * `signedUp`: the code went to an account created right here (the client
 * counts the signup when the code is used).
 */
export type LoginStep = "email" | "code" | "password";
export type LoginState = { step: LoginStep; email?: string; error?: string; notice?: string; signedUp?: boolean; next: string };

const Email = z.email({ error: "Ingresá un email válido." }).max(254);
const FAILED = "No pudimos mandarte el código. Probá de nuevo en unos minutos.";

function parseEmail(form: FormData): string | null {
  const parsed = Email.safeParse(String(form.get("email") ?? "").trim().toLowerCase());
  return parsed.success ? parsed.data : null;
}

export async function login(prev: LoginState, form: FormData): Promise<LoginState> {
  const next = safeNext(String(form.get("next") ?? prev.next));
  const intent = String(form.get("intent") ?? "");
  if (intent === "change-email") return { step: "email", email: prev.email, next };
  const email = parseEmail(form);
  if (!email) return { step: intent === "password" ? "password" : "email", email: String(form.get("email") ?? ""), next, error: "Ingresá un email válido." };
  if (intent === "continue") return continueWith(email, next);
  if (intent === "send-code") return requestCode(email, next);
  if (intent === "verify") return verify(email, form.get("code"), next, prev);
  if (intent === "password") return withPassword(email, String(form.get("password") ?? ""), next);
  return { step: "email", email, next, error: "Acción inválida." };
}

/** «Continuar»: the password step for an account that has one, the code for the rest. */
async function continueWith(email: string, next: string): Promise<LoginState> {
  let account: ExistingAccount | null;
  try {
    // «Continuar» says which emails have a password: braked like the landing's lookups.
    const { lookupsPerIpHour } = (await webConfig()).emailOnlySignup;
    if (!(await claimThrottle("login_lookup_ip", await clientIpKey(), lookupsPerIpHour, HOUR))) {
      return { step: "email", email, next, error: "Probaste varios emails seguidos. Esperá un rato y volvé a intentar." };
    }
    account = await accountForEmail(email);
    if (account && await hasPassword(account)) return { step: "password", email, next };
  } catch (error) {
    console.error("login lookup failed:", error instanceof Error ? error.message : error);
    return { step: "email", email, next, error: "No pudimos seguir. Probá de nuevo en unos minutos." };
  }
  return requestCode(email, next, account);
}

/**
 * Sends the code. An email with no account gets one first, email-only like
 * the landing's (no session until the code proves the inbox), under the same
 * switch and brakes; past them, or with the switch off, the answer is the
 * same as for an existing email, so the screen never says which emails exist.
 */
async function requestCode(email: string, next: string, known?: ExistingAccount | null): Promise<LoginState> {
  const state: LoginState = { step: "code", email, next };
  let account: ExistingAccount | null;
  let signedUp = false;
  try {
    account = known === undefined ? await accountForEmail(email) : known;
    if (!account) {
      const created = await newAccount(email);
      if (created) {
        account = created;
        signedUp = true;
      }
    }
  } catch (error) {
    console.error("login code request failed:", error instanceof Error ? error.message : error);
    return { step: "email", email, next, error: FAILED };
  }
  // Exactly the shape an existing email gets.
  if (!account) return { ...state, signedUp: false };
  const result = await sendEntryLink(email, next, account);
  if (result !== "sent") return { step: "email", email, next, error: linkError(result) };
  return { ...state, signedUp };
}

async function newAccount(email: string): Promise<ExistingAccount | null> {
  // The health dashboard trusts this address: it never becomes an unproven account.
  if (email === HEALTH_OWNER_EMAIL) return null;
  const cfg = (await webConfig()).emailOnlySignup;
  if (!cfg.enabled) return null;
  const ip = await clientIpKey();
  if (!(await claimThrottle("free_search_signup_ip", ip, cfg.perIpHour, HOUR))) return null;
  if (!(await claimThrottle("free_search_signup_day", "global", cfg.perDay, DAY))) return null;
  const created = await createEmailOnlyUser(email);
  if ("existing" in created) return created.existing;
  return { user_id: created.userId, email_only: true, confirmed: true };
}

async function verify(email: string, code: FormDataEntryValue | null, next: string, prev: LoginState): Promise<LoginState> {
  const result = await verifyEntryCode(email, code, next);
  if (!result.ok) return { step: "code", email, next, error: result.error, notice: prev.notice };
  redirect(result.href);
}

/**
 * The password, for accounts that have one. An email-only account, or a
 * password signup that was never confirmed, gets the code instead: that's how
 * it enters (and the code confirms the email).
 */
async function withPassword(email: string, password: string, next: string): Promise<LoginState> {
  if (!password) return { step: "password", email, next, error: "Ingresá tu contraseña." };
  try {
    if (!(await claimThrottle("login_password", await clientIpKey(), 20, HOUR))) {
      return { step: "password", email, next, error: "Hiciste varios intentos. Entrá con un código por email." };
    }
  } catch (error) {
    console.error("password throttle failed:", error instanceof Error ? error.message : error);
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (!error) {
    await afterSignIn(supabase);
    redirect(next);
  }
  if (error.code === "invalid_credentials" || error.code === "email_not_confirmed") {
    let account: ExistingAccount | null = null;
    try {
      account = await accountForEmail(email);
    } catch (lookupError) {
      console.error("account lookup failed:", lookupError instanceof Error ? lookupError.message : lookupError);
    }
    if (account && (account.email_only || !account.confirmed)) {
      const result = await sendEntryLink(email, next, account);
      if (result !== "sent") return { step: "password", email, next, error: linkError(result) };
      return {
        step: "code", email, next,
        notice: account.email_only ? "Ese email todavía no tiene contraseña: entrás con el código que te mandamos." : "Ese email todavía no está confirmado: el código que te mandamos lo confirma.",
      };
    }
  }
  return { step: "password", email, next, error: "La contraseña no es correcta. Probá de nuevo o entrá con un código por email." };
}

export async function signInWithGoogle(prev: { next: string; error?: string }, form: FormData): Promise<{ next: string; error?: string }> {
  const next = safeNext(String(form.get("next") ?? prev.next));
  let url: string;
  try {
    // The SDK builds an authorization URL even when the provider is disabled.
    // Check first so users get feedback here instead of a raw Auth error page.
    const settings = await fetch(`${supabaseUrl}/auth/v1/settings`, {
      headers: { apikey: supabaseAnonKey }, cache: "no-store", signal: AbortSignal.timeout(10_000),
    });
    if (!settings.ok) return { next, error: "No pudimos conectar con Google. Probá de nuevo o entrá con un código por email." };
    const config = await settings.json();
    if (!config.external?.google) return { next, error: "El ingreso con Google todavía no está disponible. Entrá con un código por email." };
    const supabase = await createClient();
    const callback = new URL(await callbackUrl(next));
    callback.searchParams.set("provider", "google");
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: callback.toString(), skipBrowserRedirect: true },
    });
    if (error || !data.url) return { next, error: "No pudimos iniciar el ingreso con Google. Probá de nuevo." };
    url = data.url;
  } catch {
    return { next, error: "No pudimos conectar con Google. Probá de nuevo o entrá con un código por email." };
  }
  redirect(url);
}
