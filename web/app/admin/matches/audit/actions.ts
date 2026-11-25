"use server";

import { refresh } from "next/cache";
import { z } from "zod";

import { requireAdmin } from "@/lib/admin";
import { REASONS, SAMPLE_SIZE, verdictProblem, VERDICTS } from "@/lib/admin-match-audit";
import { createAdminClient } from "@/lib/supabase/admin";

export type AuditActionResult = { ok?: boolean; error?: string; total?: number; added?: number };

const SaveInput = z.object({
  id: z.number().int().positive(),
  verdict: z.enum(VERDICTS),
  reasons: z.array(z.enum(REASONS)).max(REASONS.length),
  note: z.string().max(1000).optional(),
});

/** Guarda (o corrige) el veredicto de un match de la muestra. */
export async function saveReview(input: unknown): Promise<AuditActionResult> {
  const actor = await requireAdmin();
  const parsed = SaveInput.safeParse(input);
  if (!parsed.success) return { error: "Datos inválidos." };
  const { id, verdict, reasons, note } = parsed.data;
  const problem = verdictProblem(verdict, reasons);
  if (problem) return { error: problem };
  const { error } = await createAdminClient().rpc("admin_match_review_save", {
    p_id: id,
    p_verdict: verdict,
    p_reasons: verdict === "good" ? [] : reasons,
    p_note: note?.trim() ? note.trim() : null,
    p_actor_id: actor.id,
    // This screen is a signed-in admin session: it is the one caller that declares a person.
    p_reviewer_kind: "person",
  });
  if (error) return { error: "No pudimos guardar el veredicto. Recargá la página y probá de nuevo." };
  refresh();
  return { ok: true };
}

/** Sortea la muestra de esta semana, o la completa hasta 60 si ya había una. */
export async function drawSample(): Promise<AuditActionResult> {
  await requireAdmin();
  const { data, error } = await createAdminClient().rpc("admin_match_review_draw", { p_size: SAMPLE_SIZE });
  if (error) return { error: "No pudimos sortear la muestra. Probá de nuevo." };
  const result = (data ?? {}) as { total?: number; added?: number };
  refresh();
  return { ok: true, total: result.total ?? 0, added: result.added ?? 0 };
}
