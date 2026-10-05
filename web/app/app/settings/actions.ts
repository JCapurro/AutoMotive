"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import { requireUser } from "@/lib/auth";
import type { Frequency } from "@/lib/copy";
import { track } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

const CHANNELS = ["email", "web"] as const;

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

/**
 * Deletes the account and everything in it (F7, punto 7; Ley 25.326). The SQL
 * keeps one anonymous account_deleted event; then the session is closed.
 */
export async function deleteAccount(): Promise<{ error: string } | void> {
  await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.rpc("delete_my_account");
  // Returned, not thrown: the client can't tell a throw from this redirect.
  if (error) return { error: error.message.includes("cancel_subscription_before_deleting") ? "Primero cancelá Agencia desde Ajustes y esperá la confirmación de Mercado Pago. Después podés borrar tu cuenta." : "No pudimos borrar la cuenta. Probá de nuevo." };
  // The user no longer exists: clear the cookies whatever Auth answers.
  await supabase.auth.signOut({ scope: "local" }).catch(() => undefined);
  redirect("/?cuenta=borrada");
}
