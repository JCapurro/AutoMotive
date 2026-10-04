import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { track } from "@/lib/events";
import { queuePixel } from "@/lib/meta-pixel-server";
import type { Database } from "@/types/database";

/**
 * After email confirmation or password login, record the first sign-in.
 * Recovery does not count as a completed registration.
 */
export async function afterSignIn(supabase: SupabaseClient<Database>): Promise<void> {
  const { data } = await supabase.auth.getClaims();
  const userId = data?.claims?.sub;
  if (!userId) return;
  const { count } = await supabase
    .from("events")
    .select("id", { count: "exact", head: true })
    .eq("name", "signup_completed");
  if (count) return;
  await track(supabase, userId, "signup_completed", { method: "email" });
  await queuePixel("CompleteRegistration", { content_name: "email" }, `signup:${userId}`);
}
