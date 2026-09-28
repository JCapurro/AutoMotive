/**
 * Modo asistido (§12, sección 8.4): the web writes the user's text to
 * llm_jobs, the worker answers with drafts already normalized against
 * vehicle_catalog (worker/normalization/drafts.py), and each draft becomes a
 * pre-filled, editable structured form. Nothing is saved until the user
 * confirms each one.
 */
import { z } from "zod";

import { AMBA, PLACES, type Place } from "@/lib/locations";
import type { SearchValues } from "@/lib/search-form";

export const ASSISTED_MIN_CHARS = 3;
export const ASSISTED_MAX_CHARS = 1000;
/** The worker's budget is 60 s (LLM_TIMEOUT_SECONDS); past this the form takes over. */
export const ASSISTED_DEADLINE_MS = 75_000;
/** Realtime delivers the result; this poll covers a dropped subscription. */
export const ASSISTED_POLL_MS = 2_000;

export const ASSISTED_EXAMPLES = [
  "Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km",
  "Fiesta Titanium o Polo Highline, 2017 en adelante, hasta 12 mil dólares",
  "Hilux SRV diésel automática, particular, hasta 35 millones, en zona norte",
];

const DraftValues = z.object({
  make: z.string(),
  model: z.string(),
  trim: z.string(),
  trim_strict: z.boolean(),
  year_min: z.number().int().nullable(),
  year_max: z.number().int().nullable(),
  price_max: z.number().nullable(),
  price_target: z.number().nullable(),
  currency: z.enum(["USD", "ARS"]),
  km_max: z.number().int().nullable(),
  km_target: z.number().int().nullable(),
  transmission: z.enum(["", "manual", "automatic"]),
  fuel: z.string(),
  seller_type: z.enum(["", "private", "dealer"]),
  location: z.string(),
  radius_km: z.number().nullable(),
});

export const AssistedDraft = z.object({
  values: DraftValues,
  resolved: z.boolean(),
  notes: z.array(z.string()),
});
export type AssistedDraft = z.infer<typeof AssistedDraft>;

/** llm_jobs.output of a parse_search job. */
export const AssistedOutput = z.object({ drafts: z.array(AssistedDraft) });
export type AssistedOutput = z.infer<typeof AssistedOutput>;

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

// First match wins, so specific names go before generic ones: "zona norte de
// GBA" is Zona Norte, "Córdoba capital" is Córdoba and not CABA.
const ALIASES: [string, string][] = [
  ["zona norte", "zona-norte"],
  ["gba norte", "zona-norte"],
  ["zona oeste", "zona-oeste"],
  ["gba oeste", "zona-oeste"],
  ["zona sur", "zona-sur"],
  ["gba sur", "zona-sur"],
  ["capital federal", "caba"],
  ["ciudad de buenos aires", "caba"],
  ["ciudad autonoma", "caba"],
  ["caba", "caba"],
  ...PLACES.filter((p) => !p.id.startsWith("zona-") && p.id !== "caba").flatMap((p): [string, string][] => [
    [fold(p.label), p.id],
    [p.id.replace(/-/g, " "), p.id],
  ]),
  ["tucuman", "tucuman"],
  ["jujuy", "jujuy"],
  ["amba", AMBA.id],
  ["gba", AMBA.id],
  ["gran buenos aires", AMBA.id],
  ["conurbano", AMBA.id],
  ["buenos aires", AMBA.id],
  ["bs as", AMBA.id],
];

/** The place a free-text zone names ("zona norte", "Córdoba capital", "AMBA"); undefined if none. */
export function placeFromText(text: string | null | undefined): Place | undefined {
  const folded = ` ${fold(text ?? "")} `;
  if (folded.trim() === "capital") return PLACES.find((p) => p.id === "caba");
  const hit = ALIASES.find(([alias]) => folded.includes(` ${alias} `));
  if (!hit) return undefined;
  return hit[1] === AMBA.id ? AMBA : PLACES.find((p) => p.id === hit[1]);
}

/**
 * One draft as the structured form's initial values. `base` carries what the
 * text doesn't decide (sources, alert settings, the user's default place).
 * Returns the notes to show above the form (the worker's plus the zone's).
 */
export function draftToValues(draft: AssistedDraft, base: SearchValues): { values: SearchValues; notes: string[] } {
  const v = draft.values;
  const notes = [...draft.notes];
  let location = base.location;
  if (v.location) {
    const place = placeFromText(v.location);
    if (place) {
      location = { label: place.label, lat: place.lat, lon: place.lon, radius_km: v.radius_km ?? place.radius };
    } else {
      notes.push(`No reconocimos la zona «${v.location}»: elegila de la lista.`);
    }
  } else if (v.radius_km && location) {
    location = { ...location, radius_km: v.radius_km };
  }
  return {
    values: {
      ...base,
      name: "",
      make: v.make,
      model: v.model,
      trim: v.trim,
      trim_strict: v.trim_strict,
      year_min: v.year_min,
      year_max: v.year_max,
      price_max: v.price_max,
      currency: v.currency,
      km_max: v.km_max,
      transmission: v.transmission,
      fuel: v.fuel,
      location,
      km_target: v.km_target,
      price_target: v.price_target,
      seller_type: v.seller_type,
    },
    notes,
  };
}

/** "Ford Fiesta Titanium", or a placeholder when the catalog didn't resolve it. */
export function draftTitle(draft: AssistedDraft, index: number): string {
  const { make, model, trim } = draft.values;
  return [make, model, trim].filter(Boolean).join(" ") || `Vehículo ${index + 1}`;
}
