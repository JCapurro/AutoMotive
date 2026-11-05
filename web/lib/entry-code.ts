import "server-only";

import { afterRecoveryLink } from "@/lib/account-proof";
import { accountForEmail, claimThrottle, clientIpKey, HOUR } from "@/lib/email-only";
import { RESET_PASSWORD_PATH, safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";

/**
 * «Código para entrar» (docs/AUTENTICACION.md): the email that carries the
 * link to enter (the recovery email, lib/email-only.ts sendEntryLink) also
 * shows its one-time code. Typing the code is the same proof as opening the
 * link, and it works in the browser where the person already is (Instagram's
 * doesn't share cookies with Gmail). One code per email: a new email, or
 * opening the link, replaces it.
 *
 * Six digits can be guessed with enough tries, so attempts are capped per
 * account and per IP, and here the brakes fail closed. Auth keeps its own
 * per-IP limit (token_verifications) and the code expires with the link.
 */
export const CODE_TRIES_PER_ACCOUNT_HOUR = 8;
export const CODE_TRIES_PER_IP_HOUR = 30;

export type CodeResult = { ok: true; href: string; signedUp: boolean } | { ok: false; error: string };

// Auth answers otp_expired for a mistyped code too: one message covers both.
const WRONG = "El código no es correcto o venció. Revisá el último email que te mandamos, o pedí otro.";
const TOO_MANY = "Hiciste varios intentos. Pedí un código nuevo en un rato.";
const FAILED = "No pudimos comprobar el código. Probá de nuevo en unos minutos.";

/** Digits only, between 6 and 8 (Auth's otp_length); null for anything else. */
export function normalizeCode(raw: unknown): string | null {
  const code = String(raw ?? "").replace(/\s|-/g, "");
  return /^\d{6,8}$/.test(code) ? code : null;
}

/**
 * Checks the code for `email` and signs this browser in. Where it goes next
 * follows the link's rules: an email-only account proves its inbox (other
 * sessions closed, footholds cleared, proof saved) and goes on to `next`, or
 * to choose a password before paying; a password signup that was never
 * confirmed chooses a new password, since someone else may have set the old
 * one; any other account goes straight to `next`.
 */
export async function verifyEntryCode(email: string, rawCode: unknown, next: string): Promise<CodeResult> {
  const code = normalizeCode(rawCode);
  if (!code) return { ok: false, error: "Escribí el código de 6 números que te mandamos." };
  const target = safeNext(next);
  let account: Awaited<ReturnType<typeof accountForEmail>>;
  try {
    if (!(await claimThrottle("entry_code_ip", await clientIpKey(), CODE_TRIES_PER_IP_HOUR, HOUR))) return { ok: false, error: TOO_MANY };
    account = await accountForEmail(email);
    if (account && !(await claimThrottle("entry_code_user", account.user_id, CODE_TRIES_PER_ACCOUNT_HOUR, HOUR))) {
      return { ok: false, error: TOO_MANY };
    }
  } catch (error) {
    console.error("entry code check failed:", error instanceof Error ? error.message : error);
    return { ok: false, error: FAILED };
  }
  // Same answer as a wrong code: nobody learns which emails have an account.
  if (!account) return { ok: false, error: WRONG };

  const supabase = await createClient();
  const { data, error } = await supabase.auth.verifyOtp({ email, token: code, type: "recovery" });
  if (error || data.user?.id !== account.user_id) {
    if (!error) await supabase.auth.signOut({ scope: "local" });
    return { ok: false, error: WRONG };
  }
  const reset = `${RESET_PASSWORD_PATH}?${new URLSearchParams({ next: target })}`;
  if (account.email_only) {
    const href = await afterRecoveryLink(supabase, reset);
    const signedUp = await afterSignIn(supabase, "email_code");
    return { ok: true, href, signedUp };
  }
  if (!account.confirmed) return { ok: true, href: reset, signedUp: false };
  await afterSignIn(supabase);
  return { ok: true, href: target, signedUp: false };
}
