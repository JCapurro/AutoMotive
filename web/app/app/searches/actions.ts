"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import { ASSISTED_MAX_CHARS, ASSISTED_MIN_CHARS, ASSISTED_WORKER_STALE_MS, AssistedOutput } from "@/lib/assisted";
import { requireUser } from "@/lib/auth";
import type { Frequency } from "@/lib/copy";
import { track } from "@/lib/events";
import { queuePixel } from "@/lib/meta-pixel-server";
import {
  MODEL_LESS_UNAVAILABLE,
  SearchInput,
  type SearchValues,
  isModelLess,
  matchingChanged,
  modelBodyTypes,
  toColumns,
  toFilters,
} from "@/lib/search-form";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";
import type { Json } from "@/types/database";

export type SaveResult = { error?: string; fields?: Record<string, string>; savedId?: number };
/**
 * A search created from the modo asistido (sección 8.4): the llm_jobs row it
 * came from, whether the user changed the proposal, and `stay` to get the new
 * id back instead of a redirect (several vehicles reviewed on one page).
 * `assisted_fallback`: the parse failed and the user filled the form by hand.
 */
export type SaveOrigin = {
  mode: "assisted" | "assisted_fallback";
  jobId: number | null;
  edited: boolean;
  stay: boolean;
};
/** `unavailable`: the worker isn't running, so no job was queued. */
export type AssistedStart = { jobId?: number; error?: string; unavailable?: boolean };
export type Preview = { count: number; sample: PreviewListing[] };
export type PreviewListing = {
  id: number;
  title: string;
  make: string | null;
  model: string | null;
  trim: string | null;
  year: number | null;
  price: number | null;
  currency: string | null;
  mileage_km: number | null;
  location_text: string | null;
  body_type: string | null;
};

async function enabledSources(supabase: Awaited<ReturnType<typeof createClient>>): Promise<string[]> {
  const { data } = await supabase.from("sources").select("id").eq("enabled", true);
  return (data ?? []).map((s) => s.id);
}

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, (c) => `\\${c}`);
}

/** The catalog's spelling of make and model, and its body types; null when the pair isn't in the catalog. */
async function canonical(supabase: Awaited<ReturnType<typeof createClient>>, v: SearchValues) {
  const { data } = await supabase
    .from("vehicle_catalog")
    .select("make, model, body_types")
    .ilike("make", escapeLike(v.make))
    .ilike("model", escapeLike(v.model))
    .is("trim", null)
    .limit(1)
    .maybeSingle();
  return data;
}

/**
 * What enforce_plan_features says about a model-less search (docs/CARROCERIA.md),
 * in the form's words; null for any other error.
 */
function modelLessError(message: string): SaveResult | null {
  if (message.includes("plan_feature_unavailable")) return { error: MODEL_LESS_UNAVAILABLE };
  if (message.includes("search_needs_model_or_body_type")) {
    return { error: "Elegí un modelo o al menos una carrocería.", fields: { model: "Elegí un modelo.", body_types: "Elegí al menos una carrocería." } };
  }
  if (message.includes("search_needs_max_price")) {
    const priceMax = "Poné un precio máximo para buscar por carrocería.";
    return { error: priceMax, fields: { price_max: priceMax } };
  }
  return null;
}

/** Create or edit a search (§12). The worker then stores its backfill. */
export async function saveSearch(id: number | null, raw: SearchInput, origin?: SaveOrigin): Promise<SaveResult> {
  const user = await requireUser();
  const parsed = SearchInput.safeParse(raw);
  if (!parsed.success) {
    const fields = Object.fromEntries(parsed.error.issues.map((i) => [String(i.path[0]), i.message]));
    return { error: "Revisá los campos marcados.", fields };
  }
  const supabase = await createClient();
  // No make and no model: a search by body type, for plans with model_less_search (the database checks it again).
  const modelLess = isModelLess(parsed.data);
  const [vehicle, { data: thresholdAlerts }, { data: modelLessSearch }] = await Promise.all([
    modelLess ? null : canonical(supabase, parsed.data),
    supabase.rpc("my_plan_feature", { p_feature: "threshold_alerts" }),
    modelLess ? supabase.rpc("my_plan_feature", { p_feature: "model_less_search" }) : { data: null },
  ]);
  if (modelLess && modelLessSearch !== true) return { error: MODEL_LESS_UNAVAILABLE };
  if (!modelLess && !vehicle) return { error: "Elegí una marca y un modelo de la lista.", fields: { model: "Modelo desconocido." } };
  // Within a model, only the body types the form offers for it (the catalog's, when it lists several).
  const offered = modelBodyTypes(vehicle?.body_types);
  const vehicleValues = vehicle
    ? { make: vehicle.make, model: vehicle.model, body_types: parsed.data.body_types.filter((code) => offered.includes(code)) }
    : {};
  // Only a plan with the threshold (Pro) keeps one; any other plan saves none.
  const values = { ...parsed.data, ...vehicleValues,
    opportunity_threshold_pct: thresholdAlerts ? parsed.data.opportunity_threshold_pct : null };
  const sources = await enabledSources(supabase);
  const valid = values.sources.filter((s) => sources.includes(s));
  if (!valid.length) return { error: "Elegí al menos una fuente.", fields: { sources: "Elegí al menos una fuente." } };
  const columns = toColumns({ ...values, sources: valid }, sources);
  const row = {
    ...columns,
    filters: columns.filters as { [key: string]: Json },
    preferences: columns.preferences as { [key: string]: Json },
  };

  if (id == null) {
    const { data: profile } = await supabase.from("profiles").select("default_channels").single();
    const rawQuery = origin?.jobId != null ? await jobText(supabase, origin.jobId) : null;
    const { data, error } = await supabase
      .from("search_profiles")
      .insert({
        ...row,
        user_id: user.id,
        channels: profile?.default_channels ?? ["email"],
        raw_query: rawQuery,
      })
      .select("id")
      .single();
    if (error) {
      if (error.message.includes("plan_access_expired")) return { error: "Tu acceso venció. Elegí Particular o Pro en Planes para volver a buscar." };
      if (error.message.includes("plan_limit_exceeded")) {
        return { error: "Llegaste al máximo de búsquedas de tu plan." };
      }
      return modelLessError(error.message) ?? { error: "No pudimos guardar la búsqueda. Probá de nuevo." };
    }
    await track(supabase, user.id, "search_profile_created", {
      mode: origin?.mode ?? "structured",
      profile_id: data.id,
      by_body_type: modelLess,
      ...(origin ? { llm_job_id: origin.jobId, edited: origin.edited } : {}),
    });
    // Several reviewed models report the request when the review ends (finishAssisted).
    if (!origin?.stay) {
      await recordSearchRequest(supabase, user.id, origin?.mode === "assisted" ? origin.jobId : null, origin?.mode ?? "structured", modelLess);
    }
    // The free trial's 72 hours start with the first active search (/app/pro).
    const { count } = await supabase.from("search_profiles").select("id", { count: "exact", head: true });
    if (count === 1) await queuePixel("StartTrial", { content_name: "first_search" }, `trial:${user.id}`);
    await queuePixel("SearchCreated", { mode: origin?.mode ?? "structured" }, `search:${data.id}`);
    if (origin?.stay) return { savedId: data.id };
    redirect(`/app/searches/${data.id}`);
  }

  const { data: before } = await supabase
    .from("search_profiles")
    .select("filters, preferences, origin_lat, origin_lon, radius_km")
    .eq("id", id)
    .maybeSingle();
  if (!before) return { error: "La búsqueda no existe." };
  const rematch = matchingChanged(before, columns);
  const { error } = await supabase
    .from("search_profiles")
    .update({ ...row, ...(rematch ? { rematch_requested_at: new Date().toISOString() } : {}) })
    .eq("id", id);
  if (error) return modelLessError(error.message) ?? { error: "No pudimos guardar los cambios. Probá de nuevo." };
  await track(supabase, user.id, "search_profile_updated", { profile_id: id, filters_changed: rematch });
  redirect(`/app/searches/${id}`);
}

type Client = Awaited<ReturnType<typeof createClient>>;

/**
 * search_created, once per request: the plan, the models the request named
 * and the searches created from them. A structured form is one model.
 * by_body_type: the search, or a vehicle of the request, has no model (docs/CARROCERIA.md).
 */
async function recordSearchRequest(
  supabase: Client, userId: string, jobId: number | null, mode: string, byBodyType = false,
): Promise<void> {
  const { data: access } = await supabase.rpc("my_plan_snapshot");
  const plan = (access as { plan?: string } | null)?.plan ?? null;
  if (jobId == null) {
    await track(supabase, userId, "search_created", { plan, mode, models_detected: 1, searches_created: 1, by_body_type: byBodyType });
    return;
  }
  const job = String(jobId);
  const { data: recorded } = await supabase.from("events").select("id").eq("name", "search_created").eq("props->>llm_job_id", job).limit(1);
  if (recorded?.length) return;
  const [{ data: row }, { count }] = await Promise.all([
    supabase.from("llm_jobs").select("output").eq("id", jobId).maybeSingle(),
    supabase.from("events").select("id", { count: "exact", head: true }).eq("name", "search_profile_created").eq("props->>llm_job_id", job),
  ]);
  const output = AssistedOutput.safeParse(row?.output);
  await track(supabase, userId, "search_created", {
    plan, mode, llm_job_id: jobId,
    models_detected: output.success ? output.data.drafts.length : null,
    searches_created: count ?? 0,
    by_body_type: output.success
      ? output.data.drafts.some((d) => isModelLess(d.values) && d.values.body_types.length > 0)
      : null,
  });
}

/** The review of an assisted request ended (models saved, discarded or none fit the plan). */
export async function finishAssisted(jobId: number): Promise<void> {
  const user = await requireUser();
  if (!Number.isSafeInteger(jobId) || jobId <= 0) return;
  await recordSearchRequest(await createClient(), user.id, jobId, "assisted");
}

/** What the user typed for an assisted job (RLS: only their own jobs). */
async function jobText(supabase: Awaited<ReturnType<typeof createClient>>, jobId: number): Promise<string | null> {
  const { data } = await supabase.from("llm_jobs").select("input").eq("id", jobId).maybeSingle();
  const text = (data?.input as { text?: unknown } | undefined)?.text;
  return typeof text === "string" ? text : null;
}

/**
 * Modo asistido (sección 8.4, paso 2): queue the text for the worker's LLM.
 * The page then waits for the job's output (Realtime, with polling).
 */
export async function startAssisted(text: string): Promise<AssistedStart> {
  const user = await requireUser();
  const clean = text.trim();
  if (clean.length < ASSISTED_MIN_CHARS) return { error: "Contanos qué auto buscás: modelo, años, presupuesto…" };
  if (clean.length > ASSISTED_MAX_CHARS) return { error: `Usá menos de ${ASSISTED_MAX_CHARS} caracteres.` };
  if (!(await workerAlive())) return { unavailable: true };
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("llm_jobs")
    .insert({ user_id: user.id, kind: "parse_search", input: { text: clean } })
    .select("id")
    .single();
  if (error) {
    if (error.message.includes("plan_access_expired")) return { error: "Tu acceso venció. Elegí un plan para volver a buscar." };
    if (error.message.includes("llm_rate_limited")) {
      return { error: "Hiciste muchas consultas seguidas. Probá en un rato o completá el formulario." };
    }
    return { error: "No pudimos enviar tu búsqueda. Probá de nuevo o completá el formulario." };
  }
  await track(supabase, user.id, "assisted_search_requested", { llm_job_id: data.id, chars: clean.length });
  return { jobId: data.id };
}

/**
 * Whether the worker beat recently (worker_heartbeat is server-only). If the
 * heartbeat can't be read, assume it's alive: the wait's deadline still covers it.
 */
async function workerAlive(): Promise<boolean> {
  const { data, error } = await createAdminClient().from("worker_heartbeat").select("beat_at").maybeSingle();
  if (error) return true;
  return data != null && Date.now() - new Date(data.beat_at).getTime() < ASSISTED_WORKER_STALE_MS;
}

/** "N publicaciones actuales coinciden": the hard filters over the last 30 days (preview_search). */
export async function previewSearch(raw: SearchInput): Promise<Preview | null> {
  await requireUser();
  const parsed = SearchInput.safeParse(raw);
  if (!parsed.success) return null;
  const supabase = await createClient();
  const v = parsed.data;
  // A model-less count only for plans that can save one (preview_search itself isn't gated).
  const [sources, { data: allowed }] = await Promise.all([
    enabledSources(supabase),
    isModelLess(v) ? supabase.rpc("my_plan_feature", { p_feature: "model_less_search" }) : { data: true },
  ]);
  if (allowed !== true) return null;
  const { data, error } = await supabase.rpc("preview_search", {
    p_filters: toFilters(v, sources) as Json,
    p_origin_lat: v.location?.lat,
    p_origin_lon: v.location?.lon,
    p_radius_km: v.location?.radius_km,
  });
  if (error || !data) return null;
  return data as unknown as Preview;
}

export async function setSearchEnabled(id: number, enabled: boolean): Promise<SaveResult> {
  const user = await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.from("search_profiles").update({ enabled }).eq("id", id);
  if (!error) {
    await track(supabase, user.id, enabled ? "search_profile_resumed" : "search_profile_paused", { profile_id: id });
  }
  if (error?.message.includes("plan_access_expired")) return { error: "Tu acceso venció. Elegí un plan para reanudar." };
  if (error?.message.includes("plan_limit_exceeded")) return { error: "Llegaste al máximo de búsquedas activas. Pausá otra o elegí un plan con más capacidad." };
  const modelLess = error ? modelLessError(error.message) : null;
  if (modelLess) return { error: modelLess.error };
  if (error) return { error: "No pudimos cambiar el estado. Probá de nuevo." };
  refresh();
  return {};
}

export async function setSearchFrequency(id: number, frequency: Frequency): Promise<void> {
  const user = await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.from("search_profiles").update({ notification_frequency: frequency }).eq("id", id);
  if (!error) {
    await track(supabase, user.id, "search_profile_updated", { profile_id: id, notification_frequency: frequency });
  }
  refresh();
}

export async function deleteSearch(id: number): Promise<void> {
  const user = await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.from("search_profiles").delete().eq("id", id);
  if (!error) await track(supabase, user.id, "search_profile_deleted", { profile_id: id });
  redirect("/app");
}
