import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { track } from "@/lib/events";
import type { Database } from "@/types/database";

/**
 * After a successful magic link or code: the first sign-in of an account is
 * its registration (§36, signup_completed). Magic link sign-in creates the
 * user, so "first" means no signup_completed yet.
 */
export async function afterSignIn(supabase: SupabaseClient<Database>): Promise<void> {
  const { data } = await supabase.auth.getClaims();
  const userId = data?.claims?.sub;
  if (!userId) return;
  const { count } = await supabase
    .from("events")
    .select("id", { count: "exact", head: true })
    .eq("name", "signup_completed");
  if (!count) await track(supabase, userId, "signup_completed", { method: "email" });
}
