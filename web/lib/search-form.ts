/**
 * The structured search form (§12 "modo estructurado") and its mapping onto
 * search_profiles (sección 4.3): one vehicle per search; hard filters in
 * `filters`, soft preferences in `preferences`, the place in origin_* /
 * radius_km. Shared by the form (client) and its server actions.
 */
import { z } from "zod";

import type { Level } from "@/lib/copy";
import type { Filters, Preferences, SearchProfile } from "@/lib/types";

const year = z.number().int().min(1950).max(2100).nullable().default(null);
const positive = z.number().positive().max(1e12).nullable().default(null);
const kilometers = z.number().int().min(0).max(2_000_000).nullable().default(null);

export const SearchInput = z
  .object({
    name: z.string().trim().max(80).default(""),
    make: z.string().trim().min(1, "Elegí una marca."),
    model: z.string().trim().min(1, "Elegí un modelo."),
    trim: z.string().trim().max(60).default(""),
    trim_strict: z.boolean().default(false),
    year_min: year,
    year_max: year,
    price_max: positive,
    currency: z.enum(["USD", "ARS"]).default("USD"),
    km_max: kilometers,
    transmission: z.enum(["", "manual", "automatic"]).default(""),
    fuel: z.string().max(20).default(""),
    sources: z.array(z.string().max(40)).max(20).default([]),
    location: z
      .object({
        label: z.string().trim().min(1).max(80),
        lat: z.number().min(-90).max(90),
        lon: z.number().min(-180).max(180),
        radius_km: z.number().positive("El radio tiene que ser mayor a 0.").max(3000),
      })
      .nullable()
      .default(null),
    km_target: kilometers,
    price_target: positive,
    seller_type: z.enum(["", "private", "dealer"]).default(""),
    notification_frequency: z.enum(["immediate", "daily"]).default("immediate"),
    notify_min_level: z.enum(["high", "good", "match", "low"]).default("good"),
  })
  .refine((v) => v.year_min == null || v.year_max == null || v.year_min <= v.year_max, {
    message: "El año «desde» no puede ser mayor que el «hasta».",
    path: ["year_max"],
  });

export type SearchInput = z.input<typeof SearchInput>;
export type SearchValues = z.output<typeof SearchInput>;

export function defaultName(v: Pick<SearchValues, "make" | "model" | "trim">): string {
  return [v.make, v.model, v.trim].filter(Boolean).join(" ").trim();
}

/** The hard filters of the form, as `filters` stores them. `allSources`: every enabled source. */
export function toFilters(v: SearchValues, allSources: string[] = []): Filters {
  const f: Filters = { make: v.make, model: v.model, trims: v.trim ? [v.trim] : [], trim_strict: Boolean(v.trim) && v.trim_strict };
  if (v.year_min != null) f.year_min = v.year_min;
  if (v.year_max != null) f.year_max = v.year_max;
  if (v.price_max != null) f.price_max = v.price_max;
  if (v.price_max != null || v.price_target != null) f.currency = v.currency;
  if (v.km_max != null) f.km_max = v.km_max;
  if (v.transmission) f.transmission = v.transmission;
  if (v.fuel) f.fuel = v.fuel;
  // Every source selected = no restriction, so sources added later are searched too.
  const chosen = [...new Set(v.sources)];
  if (chosen.length && !allSources.every((s) => chosen.includes(s))) f.sources = chosen;
  if (v.location) f.location_label = v.location.label;
  return f;
}

export function toPreferences(v: SearchValues): Preferences {
  const p: Preferences = {};
  if (v.km_target != null) p.km_target = v.km_target;
  if (v.price_target != null) p.price_target = v.price_target;
  if (v.seller_type) p.seller_type = v.seller_type;
  return p;
}

export function toColumns(v: SearchValues, allSources: string[]) {
  return {
    name: v.name || defaultName(v),
    filters: toFilters(v, allSources),
    preferences: toPreferences(v),
    origin_lat: v.location?.lat ?? null,
    origin_lon: v.location?.lon ?? null,
    radius_km: v.location?.radius_km ?? null,
    notification_frequency: v.notification_frequency,
    notify_min_level: v.notify_min_level,
  };
}

/** A stored search back into the form (edition). */
export function fromProfile(p: SearchProfile, allSources: string[]): SearchValues {
  const f = (p.filters ?? {}) as Filters;
  const prefs = (p.preferences ?? {}) as Preferences;
  return {
    name: p.name,
    make: f.make ?? "",
    model: f.model ?? "",
    trim: f.trims?.[0] ?? "",
    trim_strict: Boolean(f.trim_strict),
    year_min: f.year_min ?? null,
    year_max: f.year_max ?? null,
    price_max: f.price_max ?? null,
    currency: f.currency ?? "USD",
    km_max: f.km_max ?? null,
    transmission: f.transmission ?? "",
    fuel: f.fuel ?? "",
    sources: f.sources?.length ? f.sources : allSources,
    location:
      p.origin_lat != null && p.origin_lon != null && p.radius_km != null
        ? { label: f.location_label ?? "Ubicación guardada", lat: p.origin_lat, lon: p.origin_lon, radius_km: p.radius_km }
        : null,
    km_target: prefs.km_target ?? null,
    price_target: prefs.price_target ?? null,
    seller_type: prefs.seller_type ?? "",
    notification_frequency: p.notification_frequency,
    notify_min_level: p.notify_min_level as Level,
  };
}

/** Whether an edit changes what matches, so the worker must redo the backfill (sección 5.7). */
export function matchingChanged(
  before: Pick<SearchProfile, "filters" | "preferences" | "origin_lat" | "origin_lon" | "radius_km">,
  after: ReturnType<typeof toColumns>,
): boolean {
  const key = (x: {
    filters: unknown;
    preferences: unknown;
    origin_lat: number | null;
    origin_lon: number | null;
    radius_km: number | null;
  }) => JSON.stringify([sortKeys(x.filters), sortKeys(x.preferences), x.origin_lat, x.origin_lon, x.radius_km]);
  return key(before) !== key(after);
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, sortKeys(v)]),
    );
  }
  return value;
}
