"use server";

import { refresh } from "next/cache";

import { requireUser } from "@/lib/auth";
import type { Frequency } from "@/lib/copy";
import { track } from "@/lib/events";
import { placeById } from "@/lib/locations";
import { createClient } from "@/lib/supabase/server";

const CHANNELS = ["telegram", "email", "web"] as const;

/** Channels for every search (sección 7.2). The web inbox is always on. */
export async function saveChannels(channels: string[]): Promise<void> {
  const user = await requireUser();
  const chosen = [...new Set(["web", ...channels.filter((c) => (CHANNELS as readonly string[]).includes(c))])];
  const supabase = await createClient();
  const { error } = await supabase.from("profiles").update({ default_channels: chosen }).eq("id", user.id);
  if (error) throw new Error(error.message);
  await supabase.from("search_profiles").update({ channels: chosen }).eq("user_id", user.id);
  await track(supabase, user.id, "channels_updated", { channels: chosen });
  refresh();
}

/** Default frequency (§32), applied to the existing searches too. */
export async function saveFrequency(frequency: Frequency): Promise<void> {
  const user = await requireUser();
  if (frequency !== "immediate" && frequency !== "daily") throw new Error("invalid frequency");
  const supabase = await createClient();
  const { error } = await supabase.from("profiles").update({ default_notification_frequency: frequency }).eq("id", user.id);
  if (error) throw new Error(error.message);
  await supabase.from("search_profiles").update({ notification_frequency: frequency }).eq("user_id", user.id);
  await track(supabase, user.id, "notification_frequency_updated", { frequency });
  refresh();
}

/** Where new searches are centered by default ("" clears it). */
export async function saveDefaultLocation(placeId: string): Promise<void> {
  const user = await requireUser();
  const place = placeById(placeId);
  const supabase = await createClient();
  const { error } = await supabase
    .from("profiles")
    .update({
      default_origin_lat: place?.lat ?? null,
      default_origin_lon: place?.lon ?? null,
      default_origin_label: place?.label ?? null,
    })
    .eq("id", user.id);
  if (error) throw new Error(error.message);
  refresh();
}

/** Whether the bot already linked this account (the page polls it after opening the deep link). */
export async function telegramLinked(): Promise<boolean> {
  await requireUser();
  const supabase = await createClient();
  const { data } = await supabase.from("profiles").select("telegram_chat_id").maybeSingle();
  return Boolean(data?.telegram_chat_id);
}

export async function unlinkTelegram(): Promise<void> {
  const user = await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.rpc("unlink_telegram");
  if (error) throw new Error(error.message);
  await track(supabase, user.id, "telegram_unlinked");
  refresh();
}
