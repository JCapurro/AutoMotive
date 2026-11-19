import "server-only";

import { cache } from "react";

import { webConfig } from "@/lib/config";
import { type DealerCard, parseDealerCard } from "@/lib/dealer-contact";
import { channelOn } from "@/lib/dealer-program";
import { createClient } from "@/lib/supabase/server";
import type { Json } from "@/types/database";

/**
 * The agencies' reads (spec §6.3). Every one goes with the signed-in user's
 * client: RLS and the RPCs' membership checks decide what comes back. No
 * service role here.
 */

export type DealerSource = { id: number; source: string; profile_url: string | null; seller_name_hint: string | null; status: string };
export type ProfileLink = { kind: "mercadolibre" | "facebook" | "instagram" | "web"; url: string };
export type MyDealer = {
  id: number;
  name: string;
  contact_email: string | null;
  phone: string | null;
  whatsapp: string | null;
  address_text: string | null;
  locality_label: string;
  lat: number;
  lon: number;
  profile_links: ProfileLink[];
  status: string;
  approved: boolean;
  sources: DealerSource[];
  counts: { available: number; reserved: number; sold: number; unconfirmed: number; review: number; leads_new: number };
};

function asDealer(raw: Json | null): MyDealer | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== "number") return null;
  const counts = (r.counts ?? {}) as Record<string, unknown>;
  const n = (v: unknown) => (typeof v === "number" ? v : 0);
  return {
    ...(r as unknown as MyDealer),
    profile_links: Array.isArray(r.profile_links) ? (r.profile_links as ProfileLink[]) : [],
    sources: Array.isArray(r.sources) ? (r.sources as DealerSource[]) : [],
    counts: {
      available: n(counts.available), reserved: n(counts.reserved), sold: n(counts.sold),
      unconfirmed: n(counts.unconfirmed), review: n(counts.review), leads_new: n(counts.leads_new),
    },
  };
}

/** The signed-in user's agency, or null (no agency, or the read failed). Once per request. */
export const myDealer = cache(async (): Promise<MyDealer | null> => {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("my_dealer");
  if (error) {
    console.error("my_dealer:", error.code);
    return null;
  }
  return asDealer(data);
});

export type StockInsight = {
  item_id: number;
  listing_id: number | null;
  origin: string;
  status: string;
  sync_state: string;
  make: string | null;
  model: string | null;
  trim: string | null;
  year: number | null;
  mileage_km: number | null;
  price: number | null;
  currency: string | null;
  price_usd: number | null;
  confirmed_at: string | null;
  confirm_due_at: string | null;
  hidden_reason: string | null;
  market: Json;
  days_in_stock: number | null;
  model_days_to_sell: Json;
  demand: Json;
};

/** dealer_stock_insights(): one row per car of my stock (not archived). */
export async function stockInsights(): Promise<StockInsight[]> {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("dealer_stock_insights");
  if (error) {
    console.error("dealer_stock_insights:", error.code);
    return [];
  }
  return (data ?? []) as StockInsight[];
}

export type DealerLead = {
  id: number;
  item_id: number | null;
  listing_id: number | null;
  buyer_name: string;
  buyer_phone: string;
  message: string | null;
  consent_at: string;
  origin: string;
  status: string;
  status_changed_at: string | null;
  created_at: string;
  listings: { make: string | null; model: string | null; trim: string | null; year: number | null; title: string | null } | null;
};

/** My agency's inbox (RLS: members only), newest first. Never buyer_user_id. */
export async function dealerLeads(dealerId: number): Promise<DealerLead[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("dealer_leads")
    .select("id, item_id, listing_id, buyer_name, buyer_phone, message, consent_at, origin, status, status_changed_at, created_at, listings(make, model, trim, year, title)")
    .eq("dealer_id", dealerId)
    .order("created_at", { ascending: false })
    .limit(300);
  if (error) {
    console.error("dealer_leads:", error.code);
    return [];
  }
  return (data ?? []) as unknown as DealerLead[];
}

/** listing_dealer_card() for the listing page; null for a common listing or a failed read. */
export async function dealerCard(listingId: number): Promise<DealerCard | null> {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("listing_dealer_card", { p_listing_id: listingId });
  if (error) {
    console.error("listing_dealer_card:", error.code);
    return null;
  }
  return parseDealerCard(data);
}

/** The «Agencia» names of a list of listings (only those with the label). Empty without the channel: no call. */
export async function dealerBadges(ids: number[]): Promise<Map<number, string>> {
  const unique = [...new Set(ids)].slice(0, 200);
  if (!unique.length) return new Map();
  const program = (await webConfig()).dealerProgram;
  if (!program || !channelOn(program)) return new Map();
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("dealer_badges", { p_listing_ids: unique });
  if (error) {
    console.error("dealer_badges:", error.code);
    return new Map();
  }
  return new Map((data ?? []).map((r) => [r.listing_id, r.dealer_name]));
}
