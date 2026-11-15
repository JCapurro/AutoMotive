"use server";

import { redirect } from "next/navigation";

import { startPayment } from "@/app/app/pro/billing-actions";
import { liveAccount } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { hasFreshProof, linkError, sendEntryLink } from "@/lib/email-only";
import { verifyEntryCode } from "@/lib/entry-code";
import { safeNext } from "@/lib/navigation";
import { payPlan } from "@/lib/pro";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/** `expired`: the link's proof is gone (over an hour, or another session); a new link is needed. */
export type AccountState = { error?: string; sent?: boolean; expired?: boolean };

/** The email-only account asks for the link that proves its inbox. */
export async function sendAccountLink(next: string): Promise<AccountState> {
  const target = safeNext(next);
  const account = await liveAccount();
  if (!account?.email) return { error: "Tu sesión venció. Volvé a entrar con un código desde el login." };
  if (!account.emailOnly) redirect(target);
  const result = await sendEntryLink(account.email, target, { user_id: account.id, email_only: true, confirmed: true });
  return result === "sent" ? { sent: true } : { error: linkError(result) };
}

/**
 * The code from that same email, typed here: the same proof as the link, and
 * then this page asks for the password.
 */
export async function confirmAccountCode(next: string, _prev: AccountState, form: FormData): Promise<AccountState> {
  const target = safeNext(next);
  const account = await liveAccount();
  if (!account?.email) return { error: "Tu sesión venció. Volvé a entrar con un código desde el login." };
  if (!account.emailOnly) redirect(target);
  const result = await verifyEntryCode(account.email, form.get("code"), target);
  if (!result.ok) return { sent: true, error: result.error };
  // A cleanup that couldn't finish comes back here with its own error.
  if (result.href.startsWith("/app/cuenta")) {
    // «Confirmar y pagar»: typed on the way to the checkout, so the page goes on by itself (continueToPayment).
    redirect(target.startsWith("/app/pro") && !result.href.includes("error=") ? `${result.href}&pagar=1` : result.href);
  }
  redirect(`/app/cuenta?${new URLSearchParams({ next: target })}`);
}

/**
 * `url`: the checkout to open. `href`: no plan to charge here (the founder
 * link, or payments off), go on there. `password`: the database doesn't complete an account with the
 * code alone yet, so the page asks for the password as before. `expired`: the
 * proof is gone and a new code is needed.
 */
export type PaymentStep = { url?: string; href?: string; error?: string; expired?: boolean; password?: boolean };

/**
 * Camino al pago (docs/PAGO_CON_CODIGO.md): the session that proved its inbox
 * goes on to the checkout without choosing a password. The account is
 * completed with the code alone (complete_email_only_account 'code', which
 * also marks it as having no password: it signs in with a code by email, like
 * a Google account), under the same guards as the password step: a fresh proof
 * for this session and every other session closed first. A full account (the
 * code completed it a moment ago, or it came back from the checkout) only
 * starts the payment.
 */
export async function continueToPayment(next: string, version: string, amount: number): Promise<PaymentStep> {
  const target = safeNext(next);
  const account = await liveAccount();
  if (!account?.sessionId) return { error: "Tu sesión venció. Volvé a entrar con un código desde el login." };
  if (account.emailOnly) {
    const expired = { expired: true, error: "El código ya venció. Pedí uno nuevo para seguir." };
    // A direct action call must prove ownership before it can revoke anyone else's session.
    if (!(await hasFreshProof(account.id, account.sessionId))) return expired;
    const supabase = await createClient();
    // Nobody else may still be signed in when the account stops being email-only.
    const { error: signOutError } = await supabase.auth.signOut({ scope: "others" });
    if (signOutError) return { error: "No pudimos seguir. Probá de nuevo." };
    const { error } = await createAdminClient().rpc("complete_email_only_account", {
      p_user: account.id, p_session: account.sessionId, p_method: "code",
    });
    if (error) {
      // A database without the migration (20261223120000): the password step, as before.
      if (error.message.includes("invalid_method")) return { password: true };
      return error.message.includes("proof_required") ? expired : { error: "No pudimos seguir. Probá de nuevo." };
    }
  }
  const plan = payPlan(target);
  // No offer to charge here (the founder link, /app/pro alone, or payments off): its own page goes on.
  if (!plan || !(await webConfig()).automaticPayments) return { href: target };
  const payment = await startPayment(plan, true, version, amount);
  // The account was just completed: this can only be a profile read that lagged.
  if (payment.needsAccount) return { error: "No pudimos iniciar el pago. Probá de nuevo en unos segundos." };
  return { url: payment.url, error: payment.error };
}

/**
 * The session that used the link chooses a password: the account is completed
 * first (the database refuses a password on an email-only account), then the
 * password is set, and every other session is closed.
 */
export async function completeAccount(next: string, _prev: AccountState, form: FormData): Promise<AccountState> {
  const target = safeNext(next);
  const password = String(form.get("password") ?? "");
  if (password.length < 8) return { error: "Usá al menos 8 caracteres." };
  if (password !== form.get("confirmPassword")) return { error: "Las contraseñas no coinciden." };
  const account = await liveAccount();
  if (!account?.sessionId) return { error: "Tu sesión venció. Volvé a entrar con un código desde el login." };
  if (!account.emailOnly) redirect(target);
  // A direct action call must prove ownership before it can revoke anyone else's session.
  // The completion RPC rechecks this proof and the live session in its own transaction.
  if (!(await hasFreshProof(account.id, account.sessionId))) {
    return { expired: true, error: "El link ya venció. Pedí uno nuevo para elegir tu contraseña." };
  }
  const supabase = await createClient();
  // Nobody else may still be signed in when the account stops being email-only.
  const { error: signOutError } = await supabase.auth.signOut({ scope: "others" });
  if (signOutError) return { error: "No pudimos guardar la contraseña. Probá de nuevo." };
  const { error: completeError } = await createAdminClient().rpc("complete_email_only_account", {
    p_user: account.id, p_session: account.sessionId, p_method: "password",
  });
  if (completeError) {
    return completeError.message.includes("proof_required")
      ? { expired: true, error: "El link ya venció. Pedí uno nuevo para elegir tu contraseña." }
      : { error: "No pudimos guardar la contraseña. Probá de nuevo." };
  }
  const { error } = await supabase.auth.updateUser({ password });
  // The account is complete already: the regular form can still set the password.
  if (error) redirect(`/auth/reset-password?${new URLSearchParams({ next: target })}`);
  await supabase.auth.signOut({ scope: "others" });
  redirect(target);
}
