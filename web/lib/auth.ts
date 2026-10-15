import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { createClient } from "@/lib/supabase/server";

export type SessionUser = { id: string; email: string | null };

/** The signed-in user (claims verified by Supabase), or null. Once per request. */
export const currentUser = cache(async (): Promise<SessionUser | null> => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (!claims?.sub) return null;
  return { id: claims.sub, email: (claims.email as string | undefined) ?? null };
});

/** For pages and actions under /app: the proxy already redirects, this is the backstop. */
export async function requireUser(): Promise<SessionUser> {
  const user = await currentUser();
  if (!user) redirect("/login");
  return user;
}

/**
 * Free searches start with an email-only account: no password, email not
 * proven. profiles.email_only says so (users can't write it). Paying needs a
 * full account (docs/AUTENTICACION.md).
 */
export const isEmailOnly = cache(async (): Promise<boolean> => {
  const supabase = await createClient();
  const { data } = await supabase.from("profiles").select("email_only").maybeSingle();
  return data?.email_only === true;
});

export type LiveAccount = { id: string; email: string | null; sessionId: string | null; emailOnly: boolean };

/**
 * For decisions that must not trust a revoked session: getUser() asks Auth
 * whether the session still exists (getClaims verifies ES256 tokens locally
 * and accepts a revoked one until it expires).
 */
export async function liveAccount(): Promise<LiveAccount | null> {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return null;
  const [{ data: claims }, { data: profile }] = await Promise.all([
    supabase.auth.getClaims(),
    supabase.from("profiles").select("email_only").eq("id", data.user.id).maybeSingle(),
  ]);
  return {
    id: data.user.id,
    email: data.user.email ?? null,
    sessionId: (claims?.claims?.session_id as string | undefined) ?? null,
    emailOnly: profile?.email_only === true,
  };
}
