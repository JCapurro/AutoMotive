"use server";

import { refresh } from "next/cache";
import { z } from "zod";

import { requireAdmin } from "@/lib/admin";
import { fromArtInput, parseNumber } from "@/lib/admin-experiments-data";
import { createAdminClient } from "@/lib/supabase/admin";

export type ExperimentActionResult = { ok?: boolean; error?: string };

const ERRORS: [string, string][] = [
  ["experiment_exists", "Ya hay un experimento con ese identificador."],
  ["experiment_not_found", "El experimento ya no existe. Recargá la página."],
  ["admin_required", "Solo un admin puede hacer esto."],
  ["invalid_status", "Ese estado no existe."],
  ["admin_experiments_slug_check", "El identificador usa solo minúsculas, números y guion bajo (hasta 60)."],
];

function writeError(message: string): string {
  return ERRORS.find(([code]) => message.includes(code))?.[1] ?? "No pudimos guardar. Recargá la página y probá de nuevo.";
}

const optionalText = (max: number) => z.string().trim().max(max, `Máximo ${max} caracteres.`);
const optionalNumber = z.string().trim().max(30).refine((v) => v === "" || parseNumber(v) !== null, "Escribí un número (ej. 48 o 48,5).");
const optionalDate = z.string().trim().refine((v) => v === "" || /^\d{4}-\d{2}-\d{2}$/.test(v), "Fecha inválida.");
const optionalDateTime = z.string().trim().refine((v) => v === "" || fromArtInput(v) !== null, "Fecha y hora inválidas.");

const ExperimentInput = z.object({
  slug: z.string().trim().regex(/^[a-z0-9_]{1,60}$/, "El identificador usa solo minúsculas, números y guion bajo (hasta 60)."),
  title: z.string().trim().min(1, "Falta el título.").max(120, "El título tiene hasta 120 caracteres."),
  config_key: z.string().trim().max(200),
  hypothesis: optionalText(2000),
  metric: optionalText(2000),
  baseline_text: optionalText(1000),
  baseline_value: optionalNumber,
  /** `datetime-local` in Argentina time. */
  started_at: optionalDateTime,
  review_at: optionalDate,
});

const VerdictInput = z.object({
  slug: z.string().trim().min(1).max(60),
  status: z.enum(["running", "won", "lost", "inconclusive", "paused"]),
  result_text: optionalText(1000),
  result_value: optionalNumber,
  verdict_note: optionalText(2000),
});

type Parsed = z.infer<typeof ExperimentInput>;

function args(actorId: string, v: Parsed) {
  return {
    p_actor_id: actorId,
    p_slug: v.slug,
    p_title: v.title,
    p_config_key: v.config_key || null,
    p_hypothesis: v.hypothesis,
    p_metric: v.metric,
    p_baseline_text: v.baseline_text || null,
    p_baseline_value: parseNumber(v.baseline_value),
    p_started_at: fromArtInput(v.started_at),
    p_review_at: v.review_at || null,
  };
}

export async function createExperiment(input: unknown): Promise<ExperimentActionResult> {
  const actor = await requireAdmin();
  const parsed = ExperimentInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Datos inválidos." };
  const { error } = await createAdminClient().rpc("admin_create_experiment", args(actor.id, parsed.data));
  if (error) return { error: writeError(error.message) };
  refresh();
  return { ok: true };
}

export async function updateExperiment(input: unknown): Promise<ExperimentActionResult> {
  const actor = await requireAdmin();
  const parsed = ExperimentInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Datos inválidos." };
  const { error } = await createAdminClient().rpc("admin_update_experiment", args(actor.id, parsed.data));
  if (error) return { error: writeError(error.message) };
  refresh();
  return { ok: true };
}

/** Records won/lost/inconclusive with its result, or reopens (running) / pauses the experiment. */
export async function recordVerdict(input: unknown): Promise<ExperimentActionResult> {
  const actor = await requireAdmin();
  const parsed = VerdictInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Datos inválidos." };
  const v = parsed.data;
  const { error } = await createAdminClient().rpc("admin_record_experiment_verdict", {
    p_actor_id: actor.id,
    p_slug: v.slug,
    p_status: v.status,
    p_result_text: v.result_text || null,
    p_result_value: parseNumber(v.result_value),
    p_verdict_note: v.verdict_note || null,
  });
  if (error) return { error: writeError(error.message) };
  refresh();
  return { ok: true };
}
