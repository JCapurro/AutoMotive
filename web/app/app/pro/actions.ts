"use server";

import { refresh } from "next/cache";

import { requireUser } from "@/lib/auth";
import { track } from "@/lib/events";
import { isPlacement, isWaitlistPlan, type Placement, type WaitlistPlan } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";

/** §52: the CTA was shown (pro_cta_viewed) or clicked (pro_cta_clicked), and where. */
export async function trackProCta(action: "viewed" | "clicked", placement: Placement): Promise<void> {
  const user = await requireUser();
  if (!isPlacement(placement)) return;
  const supabase = await createClient();
  await track(supabase, user.id, action === "viewed" ? "pro_cta_viewed" : "pro_cta_clicked", { placement });
}

/** "Sumarme a la lista de espera": the waitlist row and waitlist_joined with the plan (join_waitlist). */
export async function joinWaitlist(plan: WaitlistPlan, placement: Placement | null): Promise<{ error?: string }> {
  await requireUser();
  if (!isWaitlistPlan(plan)) return { error: "Elegí un plan." };
  const supabase = await createClient();
  const { error } = await supabase.rpc("join_waitlist", {
    p_plan: plan,
    p_placement: placement && isPlacement(placement) ? placement : undefined,
  });
  if (error) return { error: "No pudimos sumarte. Probá de nuevo." };
  refresh();
  return {};
}

/**
 * The free plan's visible results (§33): the database records plan_limit_hit
 * (once a day per search) and says whether the limit applies.
 */
export async function reportVisibleResults(profileId: number, total: number): Promise<void> {
  await requireUser();
  const supabase = await createClient();
  await supabase.rpc("record_plan_limit_hit", {
    p_limit: "max_visible_results",
    p_props: { search_profile_id: profileId, total },
  });
}
