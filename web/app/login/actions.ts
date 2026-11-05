"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { callbackUrl } from "@/lib/auth-links";
import { webConfig } from "@/lib/config";
import { accountForEmail, claimThrottle, clientIpKey, createEmailOnlyUser, DAY, type ExistingAccount, HOUR, linkError, sendEntryLink } from "@/lib/email-only";
import { verifyEntryCode } from "@/lib/entry-code";
import { HEALTH_OWNER_EMAIL } from "@/lib/health-access";
import { safeNext } from "@/lib/navigation";
import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";

/**
 * One screen to enter (docs/AUTENTICACION.md): the email, then the code we
 * mail to it. A password, for whoever has one, and Google are the other ways.
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
  if (intent === "use-password") return { step: "password", email: String(form.get("email") ?? prev.email ?? "").trim(), next };
  const email = parseEmail(form);
  if (!email) return { step: intent === "password" ? "password" : "email", email: String(form.get("email") ?? ""), next, error: "Ingresá un email válido." };
  if (intent === "send-code") return requestCode(email, next);
  if (intent === "verify") return verify(email, form.get("code"), next, prev);
  if (intent === "password") return withPassword(email, String(form.get("password") ?? ""), next);
  return { step: "email", email, next, error: "Acción inválida." };
}

/**
 * Sends the code. An email with no account gets one first, email-only like
 * the landing's (no session until the code proves the inbox), under the same
 * switch and brakes; past them, or with the switch off, the answer is the
 * same as for an existing email, so the screen never says which emails exist.
 */
async function requestCode(email: string, next: string): Promise<LoginState> {
  const state: LoginState = { step: "code", email, next };
  let account: ExistingAccount | null;
  let signedUp = false;
  try {
    account = await accountForEmail(email);
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
      return { step: "password", email, next, error: "Hiciste varios intentos. Pedí un código para entrar." };
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
  return { step: "password", email, next, error: "No pudimos ingresar. Revisá la contraseña o pedí un código para entrar." };
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
