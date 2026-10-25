"use server";

import { redirect } from "next/navigation";

import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

/** The button of /app/bonus: starts the extra 7 days (public.start_my_bonus_trial). */
export async function startBonusTrial(): Promise<void> {
  await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.rpc("start_my_bonus_trial");
  if (error) throw new Error(error.message);
  redirect("/app/bonus");
}
