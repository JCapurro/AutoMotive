"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import { ASSISTED_MAX_CHARS, ASSISTED_MIN_CHARS } from "@/lib/assisted";
import { requireUser } from "@/lib/auth";
import type { Frequency } from "@/lib/copy";
import { track } from "@/lib/events";
import { SearchInput, type SearchValues, matchingChanged, toColumns, toFilters } from "@/lib/search-form";
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
export type AssistedStart = { jobId?: number; error?: string };
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
};

async function enabledSources(supabase: Awaited<ReturnType<typeof createClient>>): Promise<string[]> {
  const { data } = await supabase.from("sources").select("id").eq("enabled", true);
  return (data ?? []).map((s) => s.id);
}

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, (c) => `\\${c}`);
}

/** The catalog's spelling of make and model; null when the pair isn't in the catalog. */
async function canonical(supabase: Awaited<ReturnType<typeof createClient>>, v: SearchValues) {
  const { data } = await supabase
    .from("vehicle_catalog")
    .select("make, model")
    .ilike("make", escapeLike(v.make))
    .ilike("model", escapeLike(v.model))
    .is("trim", null)
    .limit(1)
    .maybeSingle();
  return data;
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
  const vehicle = await canonical(supabase, parsed.data);
  if (!vehicle) return { error: "Elegí una marca y un modelo de la lista.", fields: { model: "Modelo desconocido." } };
  const values = { ...parsed.data, make: vehicle.make, model: vehicle.model };
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
        channels: profile?.default_channels ?? ["telegram", "web"],
        raw_query: rawQuery,
      })
      .select("id")
      .single();
    if (error) {
      if (error.message.includes("plan_limit_exceeded")) {
        return { error: "Llegaste al máximo de búsquedas de tu plan." };
      }
      return { error: "No pudimos guardar la búsqueda. Probá de nuevo." };
    }
    await track(supabase, user.id, "search_profile_created", {
      mode: origin?.mode ?? "structured",
      profile_id: data.id,
      ...(origin ? { llm_job_id: origin.jobId, edited: origin.edited } : {}),
    });
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
  if (error) return { error: "No pudimos guardar los cambios. Probá de nuevo." };
  await track(supabase, user.id, "search_profile_updated", { profile_id: id, filters_changed: rematch });
  redirect(`/app/searches/${id}`);
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
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("llm_jobs")
    .insert({ user_id: user.id, kind: "parse_search", input: { text: clean } })
    .select("id")
    .single();
  if (error) {
    if (error.message.includes("llm_rate_limited")) {
      return { error: "Hiciste muchas consultas seguidas. Probá en un rato o completá el formulario." };
    }
    return { error: "No pudimos enviar tu búsqueda. Probá de nuevo o completá el formulario." };
  }
  await track(supabase, user.id, "assisted_search_requested", { llm_job_id: data.id, chars: clean.length });
  return { jobId: data.id };
}

/** "N publicaciones actuales coinciden": the hard filters over the last 30 days (preview_search). */
export async function previewSearch(raw: SearchInput): Promise<Preview | null> {
  await requireUser();
  const parsed = SearchInput.safeParse(raw);
  if (!parsed.success) return null;
  const supabase = await createClient();
  const sources = await enabledSources(supabase);
  const v = parsed.data;
  const { data, error } = await supabase.rpc("preview_search", {
    p_filters: toFilters(v, sources) as Json,
    p_origin_lat: v.location?.lat,
    p_origin_lon: v.location?.lon,
    p_radius_km: v.location?.radius_km,
  });
  if (error || !data) return null;
  return data as unknown as Preview;
}

export async function setSearchEnabled(id: number, enabled: boolean): Promise<void> {
  const user = await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.from("search_profiles").update({ enabled }).eq("id", id);
  if (!error) {
    await track(supabase, user.id, enabled ? "search_profile_resumed" : "search_profile_paused", { profile_id: id });
  }
  refresh();
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
