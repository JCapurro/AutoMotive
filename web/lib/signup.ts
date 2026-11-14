import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";

import { channelOf, ORIGIN_COOKIE, parseOrigin } from "@/lib/acquisition";

import { track } from "@/lib/events";
import { CONSENT_COOKIE } from "@/lib/meta-pixel";
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
  await track(supabase, userId, "signup_completed", { method, ...(await firstTouch()) });
  await queuePixel("CompleteRegistration", { content_name: method }, `signup:${userId}`);
  await reportXConversion("signup", `signup:${userId}`);
  return true;
}

/** The first visit the proxy kept (lib/acquisition.ts), as the event's origin and channel. */
async function firstTouch(): Promise<{ origin?: Record<string, string>; channel: string }> {
  try {
    const store = await cookies();
    if (store.get(CONSENT_COOKIE)?.value === "denied") return { channel: "unknown" };
    const origin = parseOrigin(store.get(ORIGIN_COOKIE)?.value);
    return origin ? { origin: origin as Record<string, string>, channel: channelOf(origin) } : { channel: "unknown" };
  } catch {
    return { channel: "unknown" };
  }
}
