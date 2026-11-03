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

/** `updatedAt`: the latest content_updated_at of the model's published guides. */
export type GuideIndexEntry = { make: string; model: string; slugMake: string; slugModel: string; updatedAt: string };

/** One entry per published model (for /guias and the sitemap); [] on a base without the table. */
export const publishedGuideIndex = cache(async (): Promise<GuideIndexEntry[]> => {
  const { data, error } = await createPublicClient()
    .from("model_guides")
    .select("make, model, slug_make, slug_model, content_updated_at")
    .order("make")
    .order("model");
  if (missingTable(error)) return [];
  if (error) throw new Error(`model_guides: ${error.message}`);
  const byModel = new Map<string, GuideIndexEntry>();
  for (const row of data ?? []) {
    const key = `${row.slug_make}/${row.slug_model}`;
    const prev = byModel.get(key);
    if (!prev || row.content_updated_at > prev.updatedAt) {
      byModel.set(key, { make: row.make, model: row.model, slugMake: row.slug_make, slugModel: row.slug_model, updatedAt: row.content_updated_at });
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
