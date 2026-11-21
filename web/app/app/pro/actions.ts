"use server";

import { refresh } from "next/cache";

import { requireUser } from "@/lib/auth";
import { track } from "@/lib/events";
import { isPlacement, isWaitlistPlan, type Placement, type WaitlistPlan } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";
import { TRIAL_OFFER_SURFACES, type TrialOfferSurface } from "@/lib/trial-offer";

/** §52: the CTA was shown (pro_cta_viewed) or clicked (pro_cta_clicked), and where. */
export async function trackProCta(action: "viewed" | "clicked", placement: Placement): Promise<void> {
  const user = await requireUser();
  if (!isPlacement(placement)) return;
  const supabase = await createClient();
  await track(supabase, user.id, action === "viewed" ? "pro_cta_viewed" : "pro_cta_clicked", { placement });
}

const QUOTA_POPUP_EVENTS = {
  viewed: "quota_popup_viewed",
  dismissed: "quota_popup_dismissed",
  plan_selected: "quota_plan_selected",
} as const;

/**
 * The pop-up shown after the free 50 results (FreeResultLimit): it was opened,
 * closed without choosing, or a plan was picked. Never throws: a failed event
 * must not get in the way of the checkout.
 */
export async function trackQuotaPopup(
  action: keyof typeof QUOTA_POPUP_EVENTS,
  profileId: number,
  plan?: WaitlistPlan,
): Promise<void> {
  if (!(action in QUOTA_POPUP_EVENTS) || !Number.isInteger(profileId)) return;
  try {
    const user = await requireUser();
    const supabase = await createClient();
    await track(supabase, user.id, QUOTA_POPUP_EVENTS[action], {
      search_profile_id: profileId,
      ...(plan && isWaitlistPlan(plan) ? { plan } : {}),
    });
  } catch (error) {
    console.error("quota popup event not recorded:", error);
  }
}

const TRIAL_OFFER_EVENTS = {
  viewed: "trial_offer_viewed",
  dismissed: "trial_offer_dismissed",
  plan_selected: "trial_offer_plan_selected",
} as const;

/**
 * Oferta cuando la prueba oculta autos (docs/OFERTA_PRUEBA.md): a surface was
 * seen, the sheet was closed without choosing, or a pass was picked. With the
 * counts the person saw, to read conversion by how much the trial hid. Never
 * throws: a failed event must not get in the way of the checkout.
 */
export async function trackTrialOffer(
  action: keyof typeof TRIAL_OFFER_EVENTS,
  profileId: number,
  surface: TrialOfferSurface,
  /** `complete`: the complete variant of «40 + N» (docs/PRUEBA_COMPLETA.md); only `true` is recorded. */
  counts: { shown: number; hidden: number; complete?: boolean },
  plan?: WaitlistPlan,
): Promise<void> {
  const count = (n: unknown) => typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= 100_000;
  if (!(action in TRIAL_OFFER_EVENTS) || !Number.isInteger(profileId) || !TRIAL_OFFER_SURFACES.includes(surface)
    || !counts || !count(counts.shown) || !count(counts.hidden)
    || (counts.complete !== undefined && typeof counts.complete !== "boolean")) return;
  try {
    const user = await requireUser();
    const supabase = await createClient();
    await track(supabase, user.id, TRIAL_OFFER_EVENTS[action], {
      search_profile_id: profileId,
      surface,
      shown: counts.shown,
      hidden: counts.hidden,
      ...(counts.complete === true ? { complete: true } : {}),
      ...(plan && isWaitlistPlan(plan) ? { plan } : {}),
    });
  } catch (error) {
    console.error("trial offer event not recorded:", error);
  }
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
