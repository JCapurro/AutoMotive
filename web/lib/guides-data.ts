import "server-only";

import { cache } from "react";

import { isSlug, PUBLIC_GUIDE_COLUMNS, type PublicGuide, type PublicGuideRow, sortGenerations, toPublicGuide } from "@/lib/guides";
import { createPublicClient } from "@/lib/supabase/public";

/** A base without 20261205120000_par04_model_guides (the web of main runs on it). */
export function missingTable(error: { code?: string; message?: string } | null | undefined): boolean {
  if (!error) return false;
  return error.code === "PGRST205" || error.code === "42P01" || (/model_guides/.test(error.message ?? "") && /does not exist|could not find/i.test(error.message ?? ""));
}

/**
 * The published guides of one model, by year, read as anon (RLS: published
 * only). null: no such model, only drafts, a slug out of pattern (not even
 * asked) or a base without the table. Any other error throws: ISR keeps
 * serving the page it had.
 */
export const publishedModelGuides = cache(async (slugMake: string, slugModel: string): Promise<PublicGuide[] | null> => {
  if (!isSlug(slugMake) || !isSlug(slugModel)) return null;
  const { data, error } = await createPublicClient()
    .from("model_guides")
    .select(PUBLIC_GUIDE_COLUMNS)
    .eq("slug_make", slugMake)
    .eq("slug_model", slugModel)
    .order("year_from", { ascending: true, nullsFirst: true })
    .order("id");
  if (missingTable(error)) return null;
  if (error) throw new Error(`model_guides: ${error.message}`);
  const guides = ((data ?? []) as PublicGuideRow[]).map(toPublicGuide);
  return guides.length ? sortGenerations(guides) : null;
});

/**
 * A make's published guides, one array per model (by model, each by year),
 * read as anon: /guias/<marca>. null like publishedModelGuides: no published
 * model, a slug out of pattern or a base without the table.
 */
export const publishedMakeGuides = cache(async (slugMake: string): Promise<PublicGuide[][] | null> => {
  if (!isSlug(slugMake)) return null;
  const { data, error } = await createPublicClient()
    .from("model_guides")
    .select(PUBLIC_GUIDE_COLUMNS)
    .eq("slug_make", slugMake)
    .order("model")
    .order("year_from", { ascending: true, nullsFirst: true })
    .order("id");
  if (missingTable(error)) return null;
  if (error) throw new Error(`model_guides: ${error.message}`);
  const byModel = new Map<string, PublicGuide[]>();
  for (const row of (data ?? []) as PublicGuideRow[]) byModel.set(row.slug_model, [...(byModel.get(row.slug_model) ?? []), toPublicGuide(row)]);
  return byModel.size ? [...byModel.values()].map(sortGenerations) : null;
});

/**
 * `updatedAt`: the latest content_updated_at of the model's published guides;
 * `yearFrom`/`yearTo`: the years they cover together (null where none says).
 */
export type GuideIndexEntry = {
  make: string;
  model: string;
  slugMake: string;
  slugModel: string;
  updatedAt: string;
  yearFrom?: number | null;
  yearTo?: number | null;
};

const lower = (a: number | null | undefined, b: number | null | undefined) => (a == null ? (b ?? null) : b == null ? a : Math.min(a, b));
const upper = (a: number | null | undefined, b: number | null | undefined) => (a == null ? (b ?? null) : b == null ? a : Math.max(a, b));

/** One entry per published model (for /guias and the sitemap); [] on a base without the table. */
export const publishedGuideIndex = cache(async (): Promise<GuideIndexEntry[]> => {
  const { data, error } = await createPublicClient()
    .from("model_guides")
    .select("make, model, slug_make, slug_model, content_updated_at, year_from, year_to")
    .order("make")
    .order("model");
  if (missingTable(error)) return [];
  if (error) throw new Error(`model_guides: ${error.message}`);
  const byModel = new Map<string, GuideIndexEntry>();
  for (const row of data ?? []) {
    const key = `${row.slug_make}/${row.slug_model}`;
    const prev = byModel.get(key);
    const yearFrom = lower(prev?.yearFrom, row.year_from);
    const yearTo = upper(prev?.yearTo, row.year_to);
    if (!prev || row.content_updated_at > prev.updatedAt) {
      byModel.set(key, { make: row.make, model: row.model, slugMake: row.slug_make, slugModel: row.slug_model, updatedAt: row.content_updated_at, yearFrom, yearTo });
    } else {
      byModel.set(key, { ...prev, yearFrom, yearTo });
    }
  }
  return [...byModel.values()];
});

/**
 * Every published guide, one array per model (by make and model, each by
 * year), read as anon: llms.txt and llms-full.txt. [] on a base without the table.
 */
export const publishedGuidesByModel = cache(async (): Promise<PublicGuide[][]> => {
  const { data, error } = await createPublicClient()
    .from("model_guides")
    .select(PUBLIC_GUIDE_COLUMNS)
    .order("make")
    .order("model")
    .order("year_from", { ascending: true, nullsFirst: true })
    .order("id");
  if (missingTable(error)) return [];
  if (error) throw new Error(`model_guides: ${error.message}`);
  const byModel = new Map<string, PublicGuide[]>();
  for (const row of (data ?? []) as PublicGuideRow[]) {
    const key = `${row.slug_make}/${row.slug_model}`;
    byModel.set(key, [...(byModel.get(key) ?? []), toPublicGuide(row)]);
  }
  return [...byModel.values()].map(sortGenerations);
});
