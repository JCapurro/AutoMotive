/**
 * The structured search form (§12 "modo estructurado") and its mapping onto
 * search_profiles (sección 4.3): one vehicle per search; hard filters in
 * `filters`, soft preferences in `preferences`, the place in origin_* /
 * radius_km. Shared by the form (client) and its server actions.
 */
import { z } from "zod";

import { BODY_TYPE_CODES, type BodyType, type Level, SELLER_STRICT, bodyTypeCodes, bodyTypesText, isBodyType } from "@/lib/copy";
import { money, number } from "@/lib/format";
import type { Filters, Preferences, SearchProfile, SellerType } from "@/lib/types";

/** Hard ceiling on places added to a search, whatever the plan (the plan's own cap is lower or none). */
export const MAX_EXTRA_LOCATIONS = 9;

const WHOLE = "Escribí solo números enteros, sin comas ni decimales.";
const year = z.number("Elegí un año.").int("Elegí un año.").min(1950, "Elegí un año desde 1950.").max(2100, "Elegí un año válido.").nullable().default(null);
const positive = z.number(WHOLE).positive("Escribí un monto mayor a 0.").max(1e12, "Ese monto es demasiado grande.").nullable().default(null);
const kilometers = z.number(WHOLE).int(WHOLE).min(0, "Los kilómetros no pueden ser negativos.").max(2_000_000, "Poné hasta 2.000.000 km.").nullable().default(null);

export const SearchInput = z
  .object({
    name: z.string().trim().max(80).default(""),
    // Both, or neither for a model-less search (docs/CARROCERIA.md): see the superRefine below.
    make: z.string().trim().default(""),
    model: z.string().trim().default(""),
    trim: z.string().trim().max(60).default(""),
    trims: z.array(z.string().trim().min(1).max(60)).max(30).default([]),
    trim_strict: z.boolean().default(false),
    year_min: year,
    year_max: year,
    price_max: positive,
    currency: z.enum(["USD", "ARS"]).default("USD"),
    km_max: kilometers,
    transmission: z.enum(["", "manual", "automatic"]).default(""),
    fuel: z.string().max(20).default(""),
    body_types: z.array(z.enum(BODY_TYPE_CODES)).max(BODY_TYPE_CODES.length).default([]),
    sources: z.array(z.string().max(40)).max(20).default([]),
    location: z
      .object({
        label: z.string().trim().min(1).max(80),
        lat: z.number().min(-90).max(90),
        lon: z.number().min(-180).max(180),
        radius_km: z.number("Escribí el radio en kilómetros (por ejemplo: 30).").positive("El radio tiene que ser mayor a 0.").max(3000, "Poné un radio de hasta 3.000 km."),
      })
      .nullable()
      .default(null),
    // Places added to `location` ("Chaco o Corrientes"); the plan's cap is checked on save (locationCap).
    extra_locations: z
      .array(
        z.object({
          label: z.string().trim().min(1).max(80),
          lat: z.number().min(-90).max(90),
          lon: z.number().min(-180).max(180),
          radius_km: z.number().positive().max(3000),
        }),
      )
      .max(MAX_EXTRA_LOCATIONS, "Elegiste demasiadas zonas.")
      .default([]),
    km_target: kilometers,
    price_target: positive,
    seller_type: z.enum(["", "private", "dealer"]).default(""),
    // PRO-01: seller_type as a hard filter (filters.seller_types), Pro only;
    // the server action decides what a plan without it keeps (sellerForPlan).
    seller_strict: z.boolean().default(false),
    notification_frequency: z.enum(["immediate", "daily"]).default("immediate"),
    notify_min_level: z.enum(["high", "good", "match", "low"]).default("good"),
    // Pro (3.2): "avisame solo si está X% o más por debajo de comparables".
    opportunity_threshold_pct: z
      .number("Escribí un número entero.")
      .int("Escribí un número entero.")
      .min(1, "Elegí entre 1 y 90 %.")
      .max(90, "Elegí entre 1 y 90 %.")
      .nullable()
      .default(null),
  })
  .refine((v) => v.year_min == null || v.year_max == null || v.year_min <= v.year_max, {
    message: "El año «desde» no puede ser mayor que el «hasta».",
    path: ["year_max"],
  })
  .refine((v) => !v.seller_strict || v.seller_type !== "", { message: SELLER_STRICT.required, path: ["seller_type"] })
  // A model, or (plans with model_less_search) no make and no model with body
  // types and a max price. The plan itself is checked by the server and the database.
  .superRefine((v, ctx) => {
    const issue = (path: string, message: string) => ctx.addIssue({ code: "custom", path: [path], message });
    if (v.model && !v.make) issue("make", "Elegí una marca.");
    if (v.model || (v.make && !v.model)) {
      if (!v.model) issue("model", "Elegí un modelo.");
      return;
    }
    if (!v.body_types.length) {
      issue("make", "Elegí una marca.");
      issue("model", "Elegí un modelo.");
      issue("body_types", "Elegí al menos una carrocería.");
    } else if (v.price_max == null) {
      issue("price_max", "Poné un precio máximo para buscar por carrocería.");
    }
  });

export type SearchInput = z.input<typeof SearchInput>;
export type SearchValues = z.output<typeof SearchInput>;

export function selectedTrims(v: { trim: string; trims?: string[] }): string[] {
  return [...new Set([...(v.trims ?? []), v.trim].filter(Boolean))];
}

/** No make and no model: a search by body type only (model_less_search). */
export function isModelLess(v: { make?: string | null; model?: string | null }): boolean {
  return !v.make?.trim() && !v.model?.trim();
}

/** The free trial's line under the vehicle (model_less_search is Particular's and Pro's). */
export const MODEL_LESS_UPSELL = "Con Particular o Pro también podés buscar por carrocería, sin elegir modelo.";
/** Saving a model-less search from an account without model_less_search. */
export const MODEL_LESS_UNAVAILABLE = "Tu plan no incluye la búsqueda por carrocería sin modelo. Elegí un modelo o pasate a Particular o Pro.";

/**
 * The body types a search within this model can filter by: the catalog's,
 * most common first, only when it lists two or more (one is certain, none unknown).
 */
export function modelBodyTypes(catalog: readonly string[] | null | undefined): BodyType[] {
  const codes = [...new Set((catalog ?? []).filter(isBodyType))];
  return codes.length >= 2 ? codes : [];
}

/** "USD 20.000" · "$ 25.000.000" */
function priceText(amount: number, currency: string | undefined): string {
  return currency === "ARS" ? `$ ${number(amount)}` : money(amount, "USD");
}

/**
 * "Ford Fiesta Titanium / SE"; without a model, the body types and the max
 * price: "SUV hasta USD 20.000", "SUV o Pick-up hasta $ 25.000.000".
 */
export function defaultName(v: {
  make?: string; model?: string; trim?: string; trims?: string[];
  body_types?: readonly string[]; price_max?: number | null; currency?: string;
}): string {
  if (isModelLess(v)) {
    const codes = bodyTypeCodes(v.body_types);
    if (!codes.length) return "";
    const price = v.price_max != null ? ` hasta ${priceText(v.price_max, v.currency)}` : "";
    const name = `${bodyTypesText(codes)}${price}`;
    return name.length <= 80 ? name : `${codes.length} carrocerías${price}`.slice(0, 80);
  }
  return [v.make, v.model, selectedTrims({ trim: v.trim ?? "", trims: v.trims }).join(" / ")]
    .filter(Boolean).join(" ").trim().slice(0, 80);
}

/** filters.seller_types as stored: one known type, or none (anything else is no filter, as in the worker). */
export function storedSellerTypes(f: Pick<Filters, "seller_types"> | null | undefined): SellerType[] {
  const types = f?.seller_types;
  return Array.isArray(types) ? types.filter((t): t is SellerType => t === "private" || t === "dealer") : [];
}

/**
 * PRO-01, decisión 8: only a plan with seller_filter (Pro) sets the strict
 * seller filter; any plan clears it. Without the feature a strict value is
 * kept only when it is the one already stored (`stored`, an edit that didn't
 * touch it); a new one, or another one, never gets stored: a new search's
 * type goes as the soft preference, an edit keeps what was stored.
 */
export function sellerForPlan(v: SearchValues, sellerFilter: boolean, stored: SellerType[] = []): SearchValues {
  if (sellerFilter || !v.seller_strict) return v;
  if (stored.length) return { ...v, seller_type: stored[0], seller_strict: true };
  return { ...v, seller_strict: false };
}

/** The hard filters of the form, as `filters` stores them. `allSources`: every enabled source. */
export function toFilters(v: SearchValues, allSources: string[] = []): Filters {
  const trims = selectedTrims(v);
  // A model-less search stores neither make nor model (nor versions): docs/CARROCERIA.md.
  const f: Filters = isModelLess(v)
    ? {}
    : { make: v.make, model: v.model, trims, trim_strict: trims.length > 0 && v.trim_strict };
  if (v.year_min != null) f.year_min = v.year_min;
  if (v.year_max != null) f.year_max = v.year_max;
  if (v.price_max != null) f.price_max = v.price_max;
  if (v.price_max != null || v.price_target != null) f.currency = v.currency;
  if (v.km_max != null) f.km_max = v.km_max;
  if (v.transmission) f.transmission = v.transmission;
  if (v.fuel) f.fuel = v.fuel;
  const bodyTypes = bodyTypeCodes(v.body_types);
  if (bodyTypes.length) f.body_types = bodyTypes;
  // Every source selected = no restriction, so sources added later are searched too.
  const chosen = [...new Set(v.sources)];
  if (chosen.length && !allSources.every((s) => chosen.includes(s))) f.sources = chosen;
  if (v.location) {
    f.location_label = v.location.label;
    // Extras only count next to a place of its own: without one the search covers the whole country.
    if (v.extra_locations.length) f.extra_locations = v.extra_locations;
  }
  if (v.seller_strict && v.seller_type) f.seller_types = [v.seller_type];
  return f;
}

export function toPreferences(v: SearchValues): Preferences {
  const p: Preferences = {};
  if (v.km_target != null) p.km_target = v.km_target;
  if (v.price_target != null) p.price_target = v.price_target;
  // With the strict filter the type lives in filters.seller_types, never twice.
  if (v.seller_type && !v.seller_strict) p.seller_type = v.seller_type;
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
    opportunity_threshold_pct: v.opportunity_threshold_pct,
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
    trims: f.trims ?? [],
    trim_strict: Boolean(f.trim_strict),
    year_min: f.year_min ?? null,
    year_max: f.year_max ?? null,
    price_max: f.price_max ?? null,
    currency: f.currency ?? "USD",
    km_max: f.km_max ?? null,
    transmission: f.transmission ?? "",
    fuel: f.fuel ?? "",
    body_types: bodyTypeCodes(f.body_types),
    sources: f.sources?.length ? f.sources : allSources,
    location:
      p.origin_lat != null && p.origin_lon != null && p.radius_km != null
        ? { label: f.location_label ?? "Ubicación guardada", lat: p.origin_lat, lon: p.origin_lon, radius_km: p.radius_km }
        : null,
    extra_locations: f.extra_locations ?? [],
    km_target: prefs.km_target ?? null,
    price_target: prefs.price_target ?? null,
    // A downgraded search keeps filters.seller_types: the worker reads it as the preference, the select shows it.
    seller_type: prefs.seller_type ?? storedSellerTypes(f)[0] ?? "",
    seller_strict: storedSellerTypes(f).length > 0,
    notification_frequency: p.notification_frequency,
    notify_min_level: p.notify_min_level as Level,
    opportunity_threshold_pct: p.opportunity_threshold_pct ?? null,
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

/** The same value with every object's keys in one order: jsonb hands keys back in its own order, so compare through this. */
export function sortKeys(value: unknown): unknown {
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
