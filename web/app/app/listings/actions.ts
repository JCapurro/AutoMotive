"use server";

import { refresh } from "next/cache";
import { z } from "zod";

import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { type InteractionStatus, type RejectionReason } from "@/lib/copy";
import { track } from "@/lib/events";
import { canChangeStatus, normalizeNote } from "@/lib/listing-tracking";
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

/**
 * §26 states; a discard may carry a §27 reason. Purchases go through
 * recordPurchase, and a purchased listing keeps its status (X-01: terminal in
 * v1). Contactado and Visita agendada leave saved as it was.
 */
export async function setStatus(listingId: number, status: InteractionStatus, reason?: RejectionReason | null) {
  const user = await requireUser();
  if (!STATUSES.includes(status) || status === "purchased" || status === "new") throw new Error("invalid status");
  const rejection = status === "discarded" && reason && REASONS.includes(reason) ? reason : null;
  const supabase = await createClient();
  const before = await currentStatus(supabase, listingId);
  if (!canChangeStatus((before?.status ?? "new") as InteractionStatus, status)) throw new Error("status locked");
  const { error } = await supabase
    .from("user_listing_interactions")
    .upsert({ user_id: user.id, listing_id: listingId, status, rejection_reason: rejection,
      ...(status === "interested" ? { saved: true } : status === "discarded" ? { saved: false } : {}) }, { onConflict: "user_id,listing_id" });
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "listing_status_changed", {
    listing_id: listingId,
    status,
    from: before?.status ?? "new",
    via: "web",
  });
  if ((status === "interested" && !before?.saved) || (status === "discarded" && before?.saved)) {
    await track(supabase, user.id, "listing_saved", { listing_id: listingId, saved: status === "interested" });
  }
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

/**
 * X-01: the user's private note on a listing. Trimmed, empty → null, over
 * app_config.listing_tracking.note_max_chars fails without writing. The event
 * carries the length, never the text.
 */
export async function setNote(listingId: number, note: string) {
  const user = await requireUser();
  const { listingTracking } = await webConfig();
  const normalized = normalizeNote(String(note ?? ""), listingTracking.noteMaxChars);
  if ("error" in normalized) throw new Error(normalized.error);
  const supabase = await createClient();
  const { error } = await supabase
    .from("user_listing_interactions")
    .upsert({ user_id: user.id, listing_id: listingId, note: normalized.note }, { onConflict: "user_id,listing_id" });
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "listing_note_saved", { listing_id: listingId, length: normalized.note ? [...normalized.note].length : 0 });
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

const ContactMessageEvent = z.object({
  listingId: z.number().int().positive(),
  via: z.enum(["clipboard", "mailto"]),
  custom: z.boolean(),
});

/**
 * PRO-01: the ready-to-send message was copied or opened in the user's email
 * (contact_message_copied). Nothing is sent: Ese Auto has no seller address.
 */
export async function trackContactMessage(listingId: number, via: "clipboard" | "mailto", custom: boolean) {
  const parsed = ContactMessageEvent.safeParse({ listingId, via, custom });
  if (!parsed.success) return;
  const user = await requireUser();
  const supabase = await createClient();
  await track(supabase, user.id, "contact_message_copied", {
    listing_id: parsed.data.listingId, via: parsed.data.via, custom_template: parsed.data.custom,
  });
}

const RiskChecklistEvent = z.object({ listingId: z.number().int().positive(), action: z.enum(["viewed", "copied"]) });

/**
 * PAR-02: the «Antes de señar» checklist was seen or copied
 * (risk_checklist_viewed / _copied). Only to the events table, never to Pixel
 * or GA; RLS lets each user record only their own events.
 */
export async function trackRiskChecklist(listingId: number, action: "viewed" | "copied") {
  const parsed = RiskChecklistEvent.safeParse({ listingId, action });
  if (!parsed.success) return;
  const user = await requireUser();
  const supabase = await createClient();
  await track(supabase, user.id, `risk_checklist_${parsed.data.action}`, { listing_id: parsed.data.listingId });
}

/** PAR-03: the listing page's price history was opened (once per view, components/app/price-history-details.tsx). */
export async function trackPriceHistoryExpanded(listingId: number, drops: number, days: number) {
  const user = await requireUser();
  const parsed = z
    .object({ listingId: z.number().int().positive(), drops: z.number().int().min(0).max(1000), days: z.number().int().min(0).max(100_000) })
    .safeParse({ listingId, drops, days });
  if (!parsed.success) return;
  const supabase = await createClient();
  await track(supabase, user.id, "price_history_expanded", { listing_id: listingId, drops, days });
}

/** PAR-01: opening the total cost breakdown (once per view). Props: the jurisdiction used and how many terms were missing. */
export async function trackTotalCostExpanded(listingId: number, jurisdiction: string[] | null, missing: number) {
  const user = await requireUser();
  const parsed = z
    .object({
      listingId: z.number().int().positive(),
      jurisdiction: z.array(z.enum(["caba", "ba", "rest"])).max(3).nullable(),
      missing: z.number().int().min(0).max(4),
    })
    .safeParse({ listingId, jurisdiction, missing });
  if (!parsed.success) return;
  const supabase = await createClient();
  await track(supabase, user.id, "total_cost_expanded", { listing_id: listingId, jurisdiction, missing });
}
