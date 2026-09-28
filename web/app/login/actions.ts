"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import { safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";

export type LoginState = { step: "email" | "code"; email?: string; error?: string; next: string };

const Email = z.email({ error: "Ingresá un email válido." });

async function siteUrl(): Promise<string> {
  if (process.env.SITE_URL) return process.env.SITE_URL.replace(/\/$/, "");
  const h = await headers();
  return h.get("origin") ?? `http://${h.get("host")}`;
}

/** Sends the magic link (sign-in and sign-up are the same step). */
export async function sendMagicLink(prev: LoginState, form: FormData): Promise<LoginState> {
  const next = safeNext(String(form.get("next") ?? prev.next));
  const parsed = Email.safeParse(String(form.get("email") ?? "").trim().toLowerCase());
  if (!parsed.success) return { step: "email", next, error: parsed.error.issues[0].message };

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithOtp({
    email: parsed.data,
    options: {
      emailRedirectTo: `${await siteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
      shouldCreateUser: true,
    },
  });
  if (error) {
    const wait = error.status === 429 || /rate limit|seconds/i.test(error.message);
    return {
      step: "email",
      email: parsed.data,
      next,
      error: wait
        ? "Pediste varios links seguidos. Esperá un minuto y probá de nuevo."
        : "No pudimos mandar el email. Probá de nuevo.",
    };
  }
  return { step: "code", email: parsed.data, next };
}

/** The 6-digit code of the same email, for when the link opens on another device. */
export async function verifyCode(prev: LoginState, form: FormData): Promise<LoginState> {
  const email = String(form.get("email") ?? prev.email ?? "");
  const next = safeNext(String(form.get("next") ?? prev.next));
  const token = String(form.get("code") ?? "").replace(/\s/g, "");
  if (!email || !/^\d{6}$/.test(token)) {
    return { step: "code", email, next, error: "El código tiene 6 números." };
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.verifyOtp({ email, token, type: "email" });
  if (error) return { step: "code", email, next, error: "El código no es válido o venció. Pedí uno nuevo." };
  await afterSignIn(supabase);
  redirect(next);
}
