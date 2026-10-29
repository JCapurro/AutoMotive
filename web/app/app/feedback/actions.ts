"use server";

import { z } from "zod";
import { liveAccount } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

const feedback = z.object({
  message: z.string().trim().min(10).max(2000),
  profileId: z.number().int().positive().nullable(),
  requestId: z.uuid(),
});

export async function submitProductFeedback(input: { message: string; profileId: number | null; requestId: string }): Promise<{ ok?: boolean; error?: string }> {
  const parsed = feedback.safeParse(input);
  if (!parsed.success) return { error: "Escribí un comentario de entre 10 y 2000 caracteres." };
  try {
    const account = await liveAccount();
    if (!account) return { error: "Tu sesión venció. Volvé a ingresar para enviar el comentario." };
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("submit_product_feedback", {
      p_message: parsed.data.message, p_profile: parsed.data.profileId, p_request: parsed.data.requestId,
    });
    if (error || !data) return { error: error?.message.includes("feedback_rate_limited")
      ? "Ya recibimos tus comentarios por hoy. Podés volver a escribirnos mañana."
      : "No pudimos guardar tu comentario. Probá de nuevo; tu texto sigue acá." };
    return { ok: true };
  } catch {
    return { error: "No pudimos guardar tu comentario. Probá de nuevo; tu texto sigue acá." };
  }
}
