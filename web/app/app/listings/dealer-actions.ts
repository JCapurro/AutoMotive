"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { requireUser } from "@/lib/auth";
import { consentText, type LeadResult, leadErrorText, normalizePhone, parseDealerCard, parseLeadResult } from "@/lib/dealer-contact";
import { track } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

const ContactInput = z.object({
  name: z.string().trim().min(2, "Revisá tu nombre.").max(80, "Revisá tu nombre."),
  phone: z.string().trim().max(40),
  message: z.string().trim().max(500, "El mensaje es muy largo.").optional().default(""),
  consent: z.literal(true, { error: "Marcá la casilla para que le pasemos tus datos." }),
  notificationId: z.number().int().positive().nullable().optional().default(null),
});

export type ContactResult = { lead?: LeadResult; error?: string };

/**
 * «Quiero que me contacten» (spec §3.8): the buyer's own request, with the
 * consent they ticked. The RPC checks the channel, the listing, the consent
 * text and the daily cap, and logs dealer_lead_created without any of the
 * buyer's data. Nothing of what they typed goes to logs here either.
 */
export async function requestDealerContact(listingId: number, form: unknown): Promise<ContactResult> {
  const user = await requireUser();
  if (!Number.isInteger(listingId) || listingId <= 0) return { error: leadErrorText("contact_unavailable") };
  const parsed = ContactInput.safeParse(form);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? leadErrorText(null) };
  const v = parsed.data;
  const phone = normalizePhone(v.phone);
  if (!phone) return { error: leadErrorText("invalid_contact:phone") };
  const supabase = await createClient();
  // The consent names the agency the page showed: read again here, never taken from the browser.
  const { data: card } = await supabase.rpc("listing_dealer_card", { p_listing_id: listingId });
  const parsedCard = parseDealerCard(card);
  const dealerName = parsedCard?.dealerName;
  if (!dealerName) return { error: leadErrorText("contact_unavailable") };
  const { data, error } = await supabase.rpc("request_dealer_contact", {
    p_listing_id: listingId,
    p_name: v.name,
    p_phone: phone,
    p_message: v.message || null,
    p_consent: true,
    p_consent_text: consentText(dealerName),
    p_notification_id: v.notificationId,
  });
  if (error) {
    // The code only (consent_required, rate_limited…), never the buyer's data.
    console.error("request_dealer_contact:", String(error.message ?? "").slice(0, 40));
    return { error: leadErrorText(error.message) };
  }
  const lead = parseLeadResult(data);
  if (!lead) return { error: leadErrorText(null) };
  if (lead.created) {
    // Ids only: never the name, phone or message (C2).
    await track(supabase, user.id, "dealer_contact_requested", {
      listing_id: listingId, dealer_id: parsedCard?.dealerId ?? undefined, origin: v.notificationId ? "alert" : "ficha",
    });
  }
  revalidatePath(`/app/listings/${listingId}`);
  return { lead };
}
