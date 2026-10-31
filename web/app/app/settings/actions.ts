"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import { requireUser } from "@/lib/auth";
import { z } from "zod";

import { CONTACT_TEMPLATE_ERROR, type Frequency, lintContactTemplate } from "@/lib/copy";
import { track } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

const CHANNELS = ["email"] as const;

/** Channels for every search (sección 7.2). Email is the MVP delivery channel. */
export async function saveChannels(channels: string[]): Promise<void> {
  const user = await requireUser();
  const chosen = [...new Set(channels.filter((c) => (CHANNELS as readonly string[]).includes(c)))];
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

const ContactTemplateInput = z.string().max(5000).nullable();

/**
 * PRO-01: the template of the message for sellers (profiles.contact_template).
 * Linted (lintContactTemplate, the worker's rule too); empty saves null (the
 * default template). The error goes back, never thrown, so the form shows it.
 * No event of its own: adoption shows in contact_message_copied.custom_template.
 */
export async function saveContactTemplate(raw: string | null): Promise<{ error?: string; value?: string | null }> {
  const user = await requireUser();
  const parsed = ContactTemplateInput.safeParse(raw);
  if (!parsed.success) return { error: CONTACT_TEMPLATE_ERROR.too_long };
  const { value, error } = lintContactTemplate(parsed.data);
  if (error) return { error: CONTACT_TEMPLATE_ERROR[error] };
  const supabase = await createClient();
  const { error: dbError } = await supabase.from("profiles").update({ contact_template: value }).eq("id", user.id);
  if (dbError) return { error: "No pudimos guardar. Probá de nuevo." };
  refresh();
  return { value };
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
  if (error) return { error: error.message.includes("cancel_subscription_before_deleting") ? "Primero cancelá Pro desde Ajustes y esperá la confirmación de Mercado Pago. Después podés borrar tu cuenta." : "No pudimos borrar la cuenta. Probá de nuevo." };
  // The user no longer exists: clear the cookies whatever Auth answers.
  await supabase.auth.signOut({ scope: "local" }).catch(() => undefined);
  redirect("/?cuenta=borrada");
}
