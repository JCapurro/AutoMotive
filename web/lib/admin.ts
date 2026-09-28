import "server-only";

import { notFound, redirect } from "next/navigation";
import { cache } from "react";

import { currentUser, type SessionUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

/** Whether the signed-in user is an admin (profiles.role, read through RLS). Once per request. */
export const isAdmin = cache(async (): Promise<boolean> => {
  const user = await currentUser();
  if (!user) return false;
  const supabase = await createClient();
  const { data } = await supabase.from("profiles").select("role").eq("id", user.id).maybeSingle();
  return data?.role === "admin";
});

/**
 * For every page and action under /admin (sección 10). The proxy already
 * filters, this is the server-side check: anything else is a 404, so /admin
 * doesn't announce itself. Only after it may the service role client be used.
 */
export async function requireAdmin(): Promise<SessionUser> {
  const user = await currentUser();
  if (!user) redirect("/login?next=/admin");
  if (!(await isAdmin())) notFound();
  return user;
}
