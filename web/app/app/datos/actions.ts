"use server";

import { revalidatePath } from "next/cache";

import { requireUser } from "@/lib/auth";
import { track } from "@/lib/events";
import { normalizeArPhone, PHONE_ERROR } from "@/lib/phone";
import { createClient } from "@/lib/supabase/server";

export type PhoneSource = "datos" | "results";
export type PhoneState = { error?: string; phone?: string | null; saved?: boolean };

/**
 * The user's mobile (profiles.phone, E.164). From «Mis datos» an empty field
 * removes it; the results' prompt only ever adds one.
 */
export async function savePhone(source: PhoneSource, _prev: PhoneState, form: FormData): Promise<PhoneState> {
  const user = await requireUser();
  const raw = String(form.get("phone") ?? "").trim();
  const phone = raw ? normalizeArPhone(raw) : null;
  if (raw && !phone) return { error: PHONE_ERROR };
  if (!phone && source !== "datos") return { error: "Escribí tu celular." };
  const supabase = await createClient();
  const { data: before } = await supabase.from("profiles").select("phone").eq("id", user.id).maybeSingle();
  const { error } = await supabase.from("profiles").update({ phone }).eq("id", user.id);
  if (error) {
    console.error("phone not saved:", error.message);
    return { error: "No pudimos guardar tu celular. Probá de nuevo." };
  }
  if (phone && !before?.phone) await track(supabase, user.id, "phone_added", { source });
  if (!phone && before?.phone) await track(supabase, user.id, "phone_removed", { source });
  // The results' prompt shows its own «Listo»; refreshing that page would remove it before it's read.
  if (source === "datos") revalidatePath("/app/datos");
  return { phone, saved: true };
}

/** The results' prompt: shown once per browser, or closed without a number. */
export async function phonePromptEvent(kind: "viewed" | "dismissed", profileId: number): Promise<void> {
  if (kind !== "viewed" && kind !== "dismissed") return;
  const user = await requireUser();
  await track(await createClient(), user.id, `phone_prompt_${kind}`, { profile_id: Number(profileId) || null });
}
