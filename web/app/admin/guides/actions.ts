"use server";

import { refresh, revalidatePath } from "next/cache";
import { z } from "zod";

import { requireAdmin } from "@/lib/admin";
import { GuideContentInput, GuideValuesInput, guidePath, lintGuide, publishProblem, slugify } from "@/lib/guides";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Json } from "@/types/database";

/**
 * PAR-04 /admin/guides. Every write goes through the security definer RPCs
 * (service role, p_actor_id = the session's admin). Publishing, unpublishing
 * or saving a published guide invalidates its public page, /guias and the
 * sitemap at once.
 */
export type GuideActionResult = { ok?: boolean; error?: string; id?: number; updatedAt?: string; jobId?: number; requested?: number; left?: number };

const ERRORS: [string, string][] = [
  ["guide_conflict", "Otra persona cambió esta guía. Recargá la página y revisá sus cambios antes de guardar."],
  ["guide_duplicate", "Ya hay una guía de ese modelo y generación."],
  ["guide_unknown_model", "Ese modelo no está en el catálogo."],
  ["guide_not_found", "La guía ya no existe. Recargá la página."],
  ["guide_incomplete", "Para publicar hacen falta las cinco secciones con al menos un renglón y de 3 a 8 preguntas."],
  ["guide_sources_unverified", "Marcá «La revisé» en cada fuente, o borrá la que no exista, antes de publicar."],
  ["guide_generation_off", "La generación con IA está apagada (llm_limits.model_guide.enabled)."],
  ["guide_daily_cap", "Llegaste al tope de borradores de hoy (llm_limits.model_guide.per_day)."],
  ["guide_monthly_cap", "Llegaste al tope de borradores del mes (llm_limits.model_guide.per_month)."],
  ["guide_published", "Una guía publicada no se regenera: despublicala primero."],
  ["guide_job_pending", "Ya hay un borrador de esta guía en cola o generándose."],
  ["guide_has_manual_edits", "La guía tiene cambios a mano: «Regenerar» los reemplaza."],
  ["admin_required", "Solo un admin puede hacer esto."],
];

function guideError(message: string): string {
  return ERRORS.find(([code]) => message.includes(code))?.[1] ?? "No pudimos guardar. Recargá la página y probá de nuevo.";
}

function revalidateGuide(slugMake: unknown, slugModel: unknown) {
  if (typeof slugMake === "string" && typeof slugModel === "string") revalidatePath(guidePath(slugMake, slugModel));
  revalidatePath("/guias");
  revalidatePath("/sitemap.xml");
}

const Id = z.number().int().positive();

/** «Crear borrador»: an empty draft of a catalog model, to fill by hand or with the LLM. */
export async function createGuide(input: unknown): Promise<GuideActionResult> {
  const actor = await requireAdmin();
  const parsed = z.object({ make: z.string().trim().min(1).max(80), model: z.string().trim().min(1).max(80), year_from: z.number().int().nullish(), year_to: z.number().int().nullish() }).safeParse(input);
  if (!parsed.success) return { error: "Elegí marca y modelo." };
  const { make, model, year_from, year_to } = parsed.data;
  const values = {
    make, model, generation_label: null, year_from: year_from ?? null, year_to: year_to ?? null,
    slug_make: slugify(make), slug_model: slugify(model),
    body: { known_issues: [], visit_checklist: [], versions_equipment: [], maintenance_costs: [], generations: [] },
    questions: [], sources: [],
  };
  const { data, error } = await createAdminClient().rpc("admin_save_model_guide", {
    p_id: null, p_values: values as unknown as Json, p_expected_updated_at: null, p_actor_id: actor.id,
  });
  if (error) return { error: guideError(error.message) };
  refresh();
  return { ok: true, id: (data as { id: number }).id };
}

/** Saves the editor. The copy lint runs here too (the editor shows it first). */
export async function saveGuide(input: unknown): Promise<GuideActionResult> {
  const actor = await requireAdmin();
  const parsed = z.object({ id: Id, expectedUpdatedAt: z.string().min(1), values: GuideValuesInput }).safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Revisá los datos de la guía." };
  const { id, expectedUpdatedAt, values } = parsed.data;
  const issues = lintGuide(values);
  if (issues.length) return { error: `${issues[0].where}: ${issues[0].message}.` };
  const payload = { ...values, slug_make: slugify(values.make), slug_model: slugify(values.model) };
  const { data, error } = await createAdminClient().rpc("admin_save_model_guide", {
    p_id: id, p_values: payload as unknown as Json, p_expected_updated_at: expectedUpdatedAt, p_actor_id: actor.id,
  });
  if (error) return { error: guideError(error.message) };
  const row = data as { id: number; updated_at: string; status: string; slug_make: string; slug_model: string };
  if (row.status === "published") revalidateGuide(row.slug_make, row.slug_model);
  refresh();
  return { ok: true, id: row.id, updatedAt: row.updated_at };
}

/** «Publicar» / «Despublicar». Unpublishing also withdraws its questions from the matches. */
export async function setGuideStatus(input: unknown): Promise<GuideActionResult> {
  const actor = await requireAdmin();
  const parsed = z.object({ id: Id, status: z.enum(["draft", "published"]) }).safeParse(input);
  if (!parsed.success) return { error: "Datos inválidos." };
  const admin = createAdminClient();
  if (parsed.data.status === "published") {
    // Same rules as the RPC, with the message of the editor.
    const { data: g } = await admin.from("model_guides").select("body, questions, sources").eq("id", parsed.data.id).maybeSingle();
    const values = g ? GuideContentInput.safeParse(g) : null;
    if (values?.success) {
      const problem = publishProblem(values.data) ?? (lintGuide(values.data)[0] ? `${lintGuide(values.data)[0].where}: ${lintGuide(values.data)[0].message}.` : null);
      if (problem) return { error: problem };
    }
  }
  const { data, error } = await admin.rpc("admin_set_model_guide_status", { p_id: parsed.data.id, p_status: parsed.data.status, p_actor_id: actor.id });
  if (error) return { error: guideError(error.message) };
  const row = data as { slug_make: string; slug_model: string; updated_at: string };
  revalidateGuide(row.slug_make, row.slug_model);
  refresh();
  return { ok: true, updatedAt: row.updated_at };
}

/** «Generar borrador» / «Regenerar» (force). Only with llm_limits.model_guide.enabled. */
export async function requestGuide(input: unknown): Promise<GuideActionResult> {
  const actor = await requireAdmin();
  const parsed = z.object({ id: Id, force: z.boolean().default(false) }).safeParse(input);
  if (!parsed.success) return { error: "Datos inválidos." };
  const { data, error } = await createAdminClient().rpc("admin_request_model_guide", {
    p_guide_id: parsed.data.id, p_force: parsed.data.force, p_actor_id: actor.id,
  });
  if (error) return { error: guideError(error.message) };
  refresh();
  return { ok: true, jobId: data as number };
}

/**
 * «Generar los que faltan»: the candidates without a guide get an empty draft
 * and a job each, until the day's cap; says how many were left.
 */
export async function generateMissing(): Promise<GuideActionResult> {
  const actor = await requireAdmin();
  const admin = createAdminClient();
  const { data: candidates, error } = await admin.rpc("admin_guide_candidates", { p_limit: 30 });
  if (error) return { error: guideError(error.message) };
  let requested = 0;
  let left = 0;
  let capped = false;
  for (const c of candidates ?? []) {
    let id = c.guide_id;
    if (id && c.guide_status !== "draft") continue;
    if (capped) {
      left += 1;
      continue;
    }
    if (!id) {
      const created = await admin.rpc("admin_save_model_guide", {
        p_id: null,
        p_values: { make: c.make, model: c.model, generation_label: null, year_from: c.year_from, year_to: c.year_to, slug_make: slugify(c.make), slug_model: slugify(c.model), body: {}, questions: [], sources: [] } as unknown as Json,
        p_expected_updated_at: null, p_actor_id: actor.id,
      });
      if (created.error) {
        left += 1;
        continue;
      }
      id = (created.data as { id: number }).id;
    }
    const job = await admin.rpc("admin_request_model_guide", { p_guide_id: id, p_force: false, p_actor_id: actor.id });
    if (!job.error) requested += 1;
    else {
      left += 1;
      if (/guide_(daily|monthly)_cap|guide_generation_off/.test(job.error.message)) capped = true;
    }
  }
  refresh();
  return { ok: true, requested, left };
}
