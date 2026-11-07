import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { track } from "@/lib/events";
import { queuePixel } from "@/lib/meta-pixel-server";
import { reportXConversion } from "@/lib/x-capi";
import type { Database } from "@/types/database";

/**
 * After email confirmation, password login, OAuth or the free search's email-only
 * account (lib/email-only.ts), record the first sign-in.
 * Recovery does not count as a completed registration.
 */
export async function afterSignIn(supabase: SupabaseClient<Database>, method: "email" | "google" | "email_only" | "email_code" = "email"): Promise<boolean> {
  const { data } = await supabase.auth.getClaims();
  const userId = data?.claims?.sub;
  if (!userId) return false;
  const { count } = await supabase
    .from("events")
    .select("id", { count: "exact", head: true })
    .eq("name", "signup_completed");
  if (count) return false;
  await track(supabase, userId, "signup_completed", { method });
  await queuePixel("CompleteRegistration", { content_name: method }, `signup:${userId}`);
  await reportXConversion("signup", `signup:${userId}`);
  return true;
}
