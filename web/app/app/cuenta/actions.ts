"use server";

import { redirect } from "next/navigation";

import { liveAccount } from "@/lib/auth";
import { linkError, sendEntryLink } from "@/lib/email-only";
import { safeNext } from "@/lib/navigation";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/** `expired`: the link's proof is gone (over an hour, or another session); a new link is needed. */
export type AccountState = { error?: string; sent?: boolean; expired?: boolean };

/** The email-only account asks for the link that proves its inbox. */
export async function sendAccountLink(next: string): Promise<AccountState> {
  const target = safeNext(next);
  const account = await liveAccount();
  if (!account?.email) return { error: "Tu sesión venció. Volvé a entrar con un link desde el login." };
  if (!account.emailOnly) redirect(target);
  const result = await sendEntryLink(account.email, target, { user_id: account.id, email_only: true, confirmed: true });
  return result === "sent" ? { sent: true } : { error: linkError(result) };
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
  if (!account?.sessionId) return { error: "Tu sesión venció. Volvé a entrar con un link desde el login." };
  if (!account.emailOnly) redirect(target);
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
