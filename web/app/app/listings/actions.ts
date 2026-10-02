"use server";

import { refresh } from "next/cache";
import { z } from "zod";

import { requireUser } from "@/lib/auth";
import { type InteractionStatus, type RejectionReason } from "@/lib/copy";
import { track } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";
import { Constants } from "@/types/database";

const STATUSES = Constants.public.Enums.interaction_status;
const REASONS = Constants.public.Enums.rejection_reason;
const INFLUENCES = Constants.public.Enums.purchase_influence;

type Supabase = Awaited<ReturnType<typeof createClient>>;

async function currentStatus(supabase: Supabase, listingId: number) {
  const { data } = await supabase
    .from("user_listing_interactions")
    .select("status, saved")
    .eq("listing_id", listingId)
    .maybeSingle();
  return data;
}

/** Opening the detail: "Nuevo" → "Visto" (§26) and listing_detail_viewed. */
export async function markSeen(listingId: number, notificationId: number | null): Promise<void> {
  const user = await requireUser();
  const supabase = await createClient();
  await supabase
    .from("user_listing_interactions")
    .upsert({ user_id: user.id, listing_id: listingId, status: "seen" }, { onConflict: "user_id,listing_id", ignoreDuplicates: true });
  await supabase.from("user_listing_interactions").update({ status: "seen" }).eq("listing_id", listingId).eq("status", "new");
  await track(supabase, user.id, "listing_detail_viewed", {
    listing_id: listingId,
    via: notificationId ? "alert" : "web",
    notification_id: notificationId ?? undefined,
  });
}

/** §26 states; a discard may carry a §27 reason. Purchases go through recordPurchase. */
export async function setStatus(listingId: number, status: InteractionStatus, reason?: RejectionReason | null) {
  const user = await requireUser();
  if (!STATUSES.includes(status) || status === "purchased") throw new Error("invalid status");
  const rejection = status === "discarded" && reason && REASONS.includes(reason) ? reason : null;
  const supabase = await createClient();
  const before = await currentStatus(supabase, listingId);
  const { error } = await supabase
    .from("user_listing_interactions")
    .upsert({ user_id: user.id, listing_id: listingId, status, rejection_reason: rejection }, { onConflict: "user_id,listing_id" });
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "listing_status_changed", {
    listing_id: listingId,
    status,
    from: before?.status ?? "new",
    via: "web",
  });
  if (status === "discarded") {
    await track(supabase, user.id, "listing_discarded", { listing_id: listingId, reason: rejection });
  }
  refresh();
}

/** The §27 reason of a listing already discarded. */
export async function setDiscardReason(listingId: number, reason: RejectionReason | null) {
  const user = await requireUser();
  const value = reason && REASONS.includes(reason) ? reason : null;
  const supabase = await createClient();
  const { error } = await supabase
    .from("user_listing_interactions")
    .update({ rejection_reason: value })
    .eq("listing_id", listingId)
    .eq("status", "discarded");
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "listing_discarded", { listing_id: listingId, reason: value });
  refresh();
}

/** Watchlist (§30): Ese Auto keeps checking a saved listing. */
export async function setSaved(listingId: number, saved: boolean) {
  const user = await requireUser();
  const supabase = await createClient();
  const { error } = await supabase
    .from("user_listing_interactions")
    .upsert({ user_id: user.id, listing_id: listingId, saved }, { onConflict: "user_id,listing_id" });
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "listing_saved", { listing_id: listingId, saved });
  refresh();
}

const Purchase = z.object({
  listingId: z.number().int().positive(),
  profileId: z.number().int().positive().nullable(),
  price: z.number().positive().max(1e12).nullable(),
  currency: z.enum(["USD", "ARS"]).nullable(),
  date: z.iso.date().nullable(),
});

/** "Compré este vehículo" (§38–39): the OwnedVehicle, the status and vehicle_purchased, in one call. */
export async function recordPurchase(input: z.input<typeof Purchase>): Promise<{ ownedId?: number; error?: string }> {
  await requireUser();
  const parsed = Purchase.safeParse(input);
  if (!parsed.success) return { error: "Revisá el precio y la fecha." };
  const p = parsed.data;
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("record_purchase", {
    p_listing_id: p.listingId,
    p_search_profile_id: p.profileId ?? undefined,
    p_price: p.price ?? undefined,
    p_currency: p.currency ?? undefined,
    p_date: p.date ?? undefined,
  });
  if (error || data == null) return { error: "No pudimos registrar la compra. Probá de nuevo." };
  refresh();
  return { ownedId: data };
}

/** §38: "¿Ese Auto influyó en que encontraras este vehículo?" */
export async function answerInfluence(ownedId: number, influence: (typeof INFLUENCES)[number]) {
  const user = await requireUser();
  if (!INFLUENCES.includes(influence)) throw new Error("invalid answer");
  const supabase = await createClient();
  const { error } = await supabase.from("owned_vehicles").update({ automotive_influence: influence }).eq("id", ownedId);
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "purchase_influence_answered", { owned_vehicle_id: ownedId, influence });
  refresh();
}

/** §25: the questions were shown or copied (seller_questions_generated / _copied). */
export async function trackSellerQuestions(listingId: number, action: "generated" | "copied") {
  const user = await requireUser();
  const supabase = await createClient();
  await track(supabase, user.id, `seller_questions_${action}`, { listing_id: listingId });
}
