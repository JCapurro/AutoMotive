import "server-only";

import { notFound, redirect } from "next/navigation";
import { cache } from "react";

import { currentUser } from "@/lib/auth";
import { HEALTH_OWNER_EMAIL, isHealthOwner } from "@/lib/health-access";
import { createClient } from "@/lib/supabase/server";

export const canViewHealth = cache(async (): Promise<boolean> => {
  const session = await currentUser();
  if (session?.email?.toLowerCase() !== HEALTH_OWNER_EMAIL) return false;
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getUser();
  return !error && isHealthOwner(data.user);
});

/** Call before creating the service role client or reading any health data. */
export async function requireHealthOwner(): Promise<void> {
  if (!(await currentUser())) redirect("/login?next=/app/health");
  if (!(await canViewHealth())) notFound();
}
