"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { callbackUrl } from "@/lib/auth-links";
import { accountForEmail, linkError, sendEntryLink } from "@/lib/email-only";
import { safeNext } from "@/lib/navigation";
import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";

export type AuthMode = "login" | "signup" | "recover";
/**
 * `entry`: we sent the link to enter instead of what the form asked for —
 * "password" when the email has no password yet (email-only account),
 * "signup" when it already has a free search.
 */
export type LoginState = { email?: string; error?: string; sent?: boolean; entry?: "password" | "signup"; confirmationRequired?: boolean; next: string };
const Email = z.email({ error: "Ingresá un email válido." });
function emailError(error: { status?: number }): string {
  return error.status === 429 ? "Pediste varios emails seguidos. Esperá un minuto y probá de nuevo." : "No pudimos mandar el email. Probá de nuevo.";
}
/** An email-only account (the free search) has no password: it enters with the link. */
async function emailOnly(email: string) {
  try {
    const account = await accountForEmail(email);
    return account?.email_only ? account : null;
  } catch (error) {
    console.error("account lookup failed:", error instanceof Error ? error.message : error);
    return null;
  }
}
export async function authenticate(mode: AuthMode, prev: LoginState, form: FormData): Promise<LoginState> {
  const next = safeNext(String(form.get("next") ?? prev.next));
  const parsed = Email.safeParse(String(form.get("email") ?? "").trim().toLowerCase());
  if (!parsed.success) return { next, error: parsed.error.issues[0].message };
  const email = parsed.data;
  const state = { next, email };
  if (!["login", "signup", "recover"].includes(mode)) return { ...state, error: "Acción inválida." };
  const password = String(form.get("password") ?? "");
  if (mode !== "recover" && !password) return { ...state, error: "Ingresá tu contraseña." };
  if (mode === "signup") {
    if (password.length < 8) return { ...state, error: "Usá al menos 8 caracteres." };
    if (password !== form.get("confirmPassword")) return { ...state, error: "Las contraseñas no coinciden." };
  }
  const supabase = await createClient();
  if (mode === "recover") {
    // Neutral on purpose: the same link serves a forgotten password and an email-only account.
    const result = await sendEntryLink(email, next);
    return result === "sent" ? { ...state, sent: true } : { ...state, error: linkError(result) };
  }
  if (mode === "signup") {
    // The email already has a free search: Auth would refuse the signup, the link
    // proves the inbox and lets them choose a password.
    const existing = await emailOnly(email);
    if (existing) {
      const result = await sendEntryLink(email, next, existing);
      return result === "sent" ? { ...state, sent: true, entry: "signup" } : { ...state, error: linkError(result) };
    }
    const { data, error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: await callbackUrl(next) } });
    if (error) return { ...state, error: error.code === "weak_password" ? "Elegí una contraseña más segura." : emailError(error) };
    // A misconfigured provider must not leave an unconfirmed signup signed in.
    if (data.session) {
      await supabase.auth.signOut();
      return { ...state, error: "La confirmación de email no está habilitada. Contactá a soporte para completar el registro." };
    }
    return { ...state, sent: true };
  }
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    if (error.code === "invalid_credentials") {
      const existing = await emailOnly(email);
      if (existing) {
        const result = await sendEntryLink(email, next, existing);
        return result === "sent" ? { ...state, sent: true, entry: "password" } : { ...state, error: linkError(result) };
      }
    }
    return { ...state, confirmationRequired: error.code === "email_not_confirmed", error: error.code === "email_not_confirmed" ? "Confirmá tu email antes de ingresar. Revisá tu bandeja de entrada y spam." : "No pudimos ingresar. Revisá tu email y contraseña, o pedí un link para entrar." };
  }
  await afterSignIn(supabase);
  redirect(next);
}
export async function resendConfirmation(prev: LoginState, form: FormData): Promise<LoginState> {
  const next = safeNext(String(form.get("next") ?? prev.next));
  const parsed = Email.safeParse(String(form.get("email") ?? "").trim().toLowerCase());
  if (!parsed.success) return { next, error: parsed.error.issues[0].message };
  const supabase = await createClient();
  const { error } = await supabase.auth.resend({ type: "signup", email: parsed.data, options: { emailRedirectTo: await callbackUrl(next) } });
  return { next, email: parsed.data, sent: !error, error: error ? emailError(error) : undefined };
}

export async function signInWithGoogle(prev: LoginState, form: FormData): Promise<LoginState> {
  const next = safeNext(String(form.get("next") ?? prev.next));
  let url: string;
  try {
    // The SDK builds an authorization URL even when the provider is disabled.
    // Check first so users get feedback here instead of a raw Auth error page.
    const settings = await fetch(`${supabaseUrl}/auth/v1/settings`, {
      headers: { apikey: supabaseAnonKey }, cache: "no-store", signal: AbortSignal.timeout(10_000),
    });
    if (!settings.ok) return { next, error: "No pudimos conectar con Google. Probá de nuevo o ingresá con email y contraseña." };
    const config = await settings.json();
    if (!config.external?.google) return { next, error: "El ingreso con Google todavía no está disponible. Ingresá con email y contraseña." };
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
    return { next, error: "No pudimos conectar con Google. Probá de nuevo o ingresá con email y contraseña." };
  }
  redirect(url);
}
