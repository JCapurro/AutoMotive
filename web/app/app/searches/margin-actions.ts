"use server";

import { requireUser } from "@/lib/auth";
import { track } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

/**
 * PRO-02: the user ordered a search's results by «Mayor margen estimado»
 * (results_sorted_margin). Only an event: the order itself is the ?s= of the page.
 */
export async function trackMarginSort(profileId: number): Promise<void> {
  const user = await requireUser();
  if (!Number.isSafeInteger(profileId) || profileId <= 0) return;
  await track(await createClient(), user.id, "results_sorted_margin", { profile_id: profileId });
}
