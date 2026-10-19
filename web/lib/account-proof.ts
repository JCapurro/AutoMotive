import "server-only";

import type { SupabaseClient, User } from "@supabase/supabase-js";

import { recordProof } from "@/lib/email-only";
import { afterRecovery, RESET_PASSWORD_PATH } from "@/lib/navigation";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Database } from "@/types/database";

/**
 * Right after a recovery link was used, on the client that verified it. The
 * link proved the inbox, so for an email-only account whoever got a session
 * by typing this email loses it (and anything they left behind), and this
 * session may choose a password (account_proofs, keyed by the session: Auth
 * marks every link session the same way). Returns where to go next.
 */
export async function afterRecoveryLink(supabase: SupabaseClient<Database>, next: string): Promise<string> {
  const destination = afterRecovery(next);
  const { data } = await supabase.auth.getClaims();
  const userId = data?.claims?.sub;
  const sessionId = data?.claims?.session_id as string | undefined;
  if (!userId) return `${RESET_PASSWORD_PATH}?${new URLSearchParams({ next: destination })}`;
  const { data: profile } = await supabase.from("profiles").select("email_only").eq("id", userId).maybeSingle();
  if (!profile?.email_only) return `${RESET_PASSWORD_PATH}?${new URLSearchParams({ next: destination })}`;
  await supabase.auth.signOut({ scope: "others" });
  await secureFootholds(userId);
  if (sessionId) await recordProof(userId, sessionId, "email_link");
  // "Sin contraseña": only paying (or asking for it) needs the password step; anyone else goes straight on.
  const wantsPassword = destination.startsWith("/app/pro") || destination.startsWith("/app/cuenta");
  return wantsPassword ? `/app/cuenta?${new URLSearchParams({ next: destination })}` : destination;
}

/**
 * Google signed in an email-only account: Google vouches for the address only
 * when its identity carries the same verified email (manual linking is off, so
 * no other identity can land here). Every other session closes first, so
 * nobody can slip a password in once the account stops being email-only;
 * then the account is completed.
 */
export async function completeWithGoogle(supabase: SupabaseClient<Database>, user: User): Promise<void> {
  const email = user.email?.trim().toLowerCase();
  const vouched = user.identities?.some((identity) => identity.provider === "google"
    && String(identity.identity_data?.email ?? "").trim().toLowerCase() === email
    && [true, "true"].includes(identity.identity_data?.email_verified));
  if (!email || !vouched) return;
  const [{ data: claims }, { data: profile }] = await Promise.all([
    supabase.auth.getClaims(),
    supabase.from("profiles").select("email_only").eq("id", user.id).maybeSingle(),
  ]);
  const sessionId = claims?.claims?.session_id as string | undefined;
  if (!profile?.email_only || !sessionId) return;
  const { error: signOutError } = await supabase.auth.signOut({ scope: "others" });
  if (signOutError) {
    console.error("google account completion skipped, other sessions still open:", signOutError.message);
    return;
  }
  await secureFootholds(user.id);
  await recordProof(user.id, sessionId, "google");
  const { error } = await createAdminClient().rpc("complete_email_only_account", { p_user: user.id, p_session: sessionId, p_method: "google" });
  if (error) console.error("google account completion failed:", error.message);
}

/** MFA factors and the Telegram link someone may have left while the account was email-only. */
async function secureFootholds(userId: string): Promise<void> {
  const { error } = await createAdminClient().rpc("secure_email_only_account", { p_user: userId });
  if (error) console.error("email-only footholds not cleared:", error.message);
}
