import "server-only";

import { configObject } from "@/lib/admin-config";
import { missingTable } from "@/lib/guides-data";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Database } from "@/types/database";

export type GuideRow = Database["public"]["Tables"]["model_guides"]["Row"];
export type GuideCandidate = Database["public"]["Functions"]["admin_guide_candidates"]["Returns"][number];
export type GuideCounts = { viewed: number; cta_clicked: number; questions_copied: number };
export type GuideJob = { id: number; status: string; error: string | null; created_at: string; finished_at: string | null; provider: string | null };
export type GuideGeneration = { enabled: boolean; perDay: number; perMonth: number; usedToday: number; usedMonth: number };

/** llm_limits.model_guide as /admin/guides reads it (off without the key). */
export function guideGeneration(llmLimits: unknown): Omit<GuideGeneration, "usedToday" | "usedMonth"> {
  const cfg = configObject(configObject(llmLimits).model_guide);
  const int = (v: unknown) => (typeof v === "number" && Number.isInteger(v) ? v : 0);
  return { enabled: cfg.enabled === true, perDay: int(cfg.per_day), perMonth: int(cfg.per_month) };
}

/** Midnight of today and of the 1st of the month in Argentina (UTC-3, no DST), as ISO. */
export function argentinaStarts(now = new Date()): { today: string; month: string } {
  const local = new Date(now.getTime() - 3 * 3600_000);
  const y = local.getUTCFullYear(), m = local.getUTCMonth(), d = local.getUTCDate();
  return { today: new Date(Date.UTC(y, m, d, 3)).toISOString(), month: new Date(Date.UTC(y, m, 1, 3)).toISOString() };
}

export type GuidesOverview =
  | { missing: true }
  | { missing: false; candidates: GuideCandidate[]; guides: GuideRow[]; counts: Map<number, GuideCounts>; jobs: Map<number, GuideJob>; pilot: Set<number>; generation: GuideGeneration };

/** Everything /admin/guides lists. Service role: call only after requireAdmin(). */
export async function loadGuidesOverview(): Promise<GuidesOverview> {
  const admin = createAdminClient();
  const { data: guides, error } = await admin.from("model_guides").select("*").order("make").order("model").order("generation_label", { nullsFirst: true });
  if (missingTable(error)) return { missing: true };
  if (error) throw new Error(`model_guides: ${error.message}`);
  const starts = argentinaStarts();
  const [candidates, counts, jobs, config, today, month] = await Promise.all([
    admin.rpc("admin_guide_candidates", { p_limit: 30 }),
    admin.rpc("admin_guide_event_counts", { p_days: 30 }),
    admin.from("llm_jobs").select("id, status, error, created_at, finished_at, provider, input").eq("kind", "model_guide").order("id", { ascending: false }).limit(500),
    admin.from("app_config").select("key, value").in("key", ["llm_limits", "model_guides"]),
    admin.rpc("model_guide_jobs_since", { p_since: starts.today }),
    admin.rpc("model_guide_jobs_since", { p_since: starts.month }),
  ]);
  const byGuide = new Map<number, GuideJob>();
  for (const j of jobs.data ?? []) {
    const id = Number(configObject(j.input).guide_id);
    if (Number.isInteger(id) && !byGuide.has(id)) byGuide.set(id, { id: j.id, status: j.status, error: j.error, created_at: j.created_at, finished_at: j.finished_at, provider: j.provider });
  }
  const value = (key: string) => config.data?.find((r) => r.key === key)?.value;
  const pilotIds = configObject(value("model_guides")).pilot;
  return {
    missing: false,
    candidates: candidates.data ?? [],
    guides: guides ?? [],
    counts: new Map((counts.data ?? []).map((c) => [Number(c.guide_id), { viewed: Number(c.viewed), cta_clicked: Number(c.cta_clicked), questions_copied: Number(c.questions_copied) }])),
    jobs: byGuide,
    pilot: new Set(Array.isArray(pilotIds) ? pilotIds.filter((v): v is number => typeof v === "number") : []),
    generation: { ...guideGeneration(value("llm_limits")), usedToday: Number(today.data ?? 0), usedMonth: Number(month.data ?? 0) },
  };
}

/** One guide for the editor, its last job and the catalog's distribution (a reference, never synced). */
export async function loadGuide(id: number) {
  const admin = createAdminClient();
  const { data: guide, error } = await admin.from("model_guides").select("*").eq("id", id).maybeSingle();
  if (missingTable(error)) return { missing: true as const };
  if (error) throw new Error(`model_guides: ${error.message}`);
  if (!guide) return null;
  const [jobs, catalog, config] = await Promise.all([
    admin.from("llm_jobs").select("id, status, error, created_at, finished_at, provider").eq("kind", "model_guide").eq("input->>guide_id", String(id)).order("id", { ascending: false }).limit(1),
    admin.from("vehicle_catalog").select("timing_belt, year_from, year_to").eq("make", guide.make).eq("model", guide.model).is("trim", null).maybeSingle(),
    admin.from("app_config").select("value").eq("key", "llm_limits").maybeSingle(),
  ]);
  return {
    missing: false as const,
    guide,
    job: (jobs.data?.[0] ?? null) as GuideJob | null,
    timingBelt: catalog.data?.timing_belt ?? null,
    generation: guideGeneration(config.data?.value),
  };
}
