"use server";

import { refresh } from "next/cache";
import { z } from "zod";

import { requireAdmin } from "@/lib/admin";
import { createAdminClient } from "@/lib/supabase/admin";

export type ProspectActionResult = { ok?: boolean; error?: string };

const ERRORS: [string, string][] = [
  ["admin_required", "Solo un admin puede hacer esto."],
  ["prospect_not_found", "Ese prospecto ya no existe. Recargá la página."],
  ["message_not_found", "Ese mensaje ya no existe. Recargá la página."],
  ["message_not_ready", "Ese mensaje ya no está para enviar (lo marcaste antes o venció). Recargá la página."],
  ["invalid_text", "El mensaje no puede quedar vacío ni pasar los 2.000 caracteres."],
  ["invalid_phone", "El número tiene que quedar como 549 + característica + número (13 dígitos)."],
  ["invalid_variant", "Esa variante no existe."],
];

function writeError(message: string): string {
  return ERRORS.find(([code]) => message.includes(code))?.[1] ?? "No pudimos guardar. Recargá la página y probá de nuevo.";
}

const Input = z.object({
  prospectId: z.number().int().positive(),
  messageId: z.number().int().positive().nullable(),
  action: z.enum(["sent", "replied", "not_interested", "wrong_number", "closed", "skipped", "edited", "chose_variant", "reopened", "phone_set"]),
  text: z.string().max(2000).nullable(),
});

/** Every change Juan makes on /admin/prospeccion: one RPC that re-checks the admin and logs the event. */
export async function prospectAction(input: unknown): Promise<ProspectActionResult> {
  const actor = await requireAdmin();
  const parsed = Input.safeParse(input);
  if (!parsed.success) return { error: "Datos inválidos." };
  const v = parsed.data;
  const { error } = await createAdminClient().rpc("admin_prospect_action", {
    p_actor_id: actor.id,
    p_prospect_id: v.prospectId,
    p_message_id: v.messageId,
    p_action: v.action,
    p_text: v.text,
  });
  if (error) return { error: writeError(error.message) };
  refresh();
  return { ok: true };
}
