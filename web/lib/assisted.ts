/**
 * Modo asistido (§12, sección 8.4): the web writes the user's text to
 * llm_jobs, the worker answers with drafts already normalized against
 * vehicle_catalog (worker/normalization/drafts.py), and each draft becomes a
 * pre-filled, editable structured form. Nothing is saved until the user
 * confirms each one.
 */
import { z } from "zod";

import { cityById, cityFromText, provinceCapital } from "@/lib/argentina-locations";

import { bodyTypeCodes, bodyTypesText } from "@/lib/copy";
import { AMBA, PLACES, type Place } from "@/lib/locations";
import { inWords } from "@/lib/pro";
import { type SearchValues, isModelLess } from "@/lib/search-form";

export const ASSISTED_MIN_CHARS = 3;
export const ASSISTED_MAX_CHARS = 1000;
/** The worker's budget is 60 s (LLM_TIMEOUT_SECONDS); past this the form takes over. */
export const ASSISTED_DEADLINE_MS = 75_000;
/** Realtime delivers the result; this poll covers a dropped subscription. */
export const ASSISTED_POLL_MS = 2_000;
/**
 * The worker beats every minute (worker_heartbeat, HEARTBEAT_SECONDS); an
 * older beat means nobody will answer the job, so the form takes over at once.
 */
export const ASSISTED_WORKER_STALE_MS = 3 * 60_000;

export const ASSISTED_EXAMPLES = [
  "Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km",
  "Fiesta Titanium o Polo Highline, 2017 en adelante, hasta 12 mil dólares",
  "Hilux SRV diésel automática, particular, hasta 35 millones, en zona norte",
];

const DraftValues = z.object({
  make: z.string(),
  model: z.string(),
  trim: z.string(),
  trims: z.array(z.string()).default([]),
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
  // docs/CARROCERIA.md. Outputs written before it have none; unknown codes are dropped.
  body_types: z.array(z.string()).default([]),
  seller_type: z.enum(["", "private", "dealer"]),
  location: z.string(),
  // Every place the text names, the first also in `location`; outputs written before it have none.
  locations: z.array(z.string()).default([]),
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

// «Argentina», «todo el país», «cualquier lado»: the whole country. Argentina is also a
// town in Santiago del Estero, so these words never go to the place lookup.
const NATIONAL = /\b(todo el pais|toda la argentina|toda argentina|todo argentina|argentina|cualquier (lado|lugar|parte|zona|provincia)|todos lados|todo el territorio|nacional)\b/g;
const ZONE_FILLER = new Set(["de", "del", "en", "la", "el", "o", "y"]);

/** A zone that says «anywhere in the country». */
export function isNationalZone(text: string): boolean {
  return new RegExp(NATIONAL.source).test(fold(text));
}

/** The zone without its country words («Rosario, Argentina» → «rosario»); "" when nothing else is left. */
export function withoutCountry(text: string): string {
  return fold(text).replace(NATIONAL, " ").split(" ").filter((w) => w && !ZONE_FILLER.has(w)).join(" ");
}

/** draftToValues' note for «todo el país»: the review form opens at the approximate zone. */
export const NATIONAL_ZONE_NOTE = "Pediste todo el país: en Zona elegí «Todo el país».";

/** The place a free-text zone names ("zona norte", "Córdoba capital", "AMBA"); undefined if none. */
export function placeFromText(text: string | null | undefined): Place | undefined {
  const folded = ` ${fold(text ?? "")} `;
  if (folded.trim() === "capital") return PLACES.find((p) => p.id === "caba");
  const hit = ALIASES.find(([alias]) => folded.includes(` ${alias} `));
  const city = cityFromText(text ?? "");
  if (city && (!hit || ["buenos aires", "bs as"].includes(hit[0]))) return city;
  if (!hit) return cityFromText(text ?? "");
  return hit[1] === AMBA.id ? AMBA : PLACES.find((p) => p.id === hit[1]);
}

/** «Santa Fe o Buenos Aires» → its places, without the bare country words. */
function zoneParts(text: string): string[] {
  return text.split(/\s+o\s+|\s+y\s+|\s*[,;/]\s*/i).map((p) => p.trim()).filter((p) => withoutCountry(p));
}

type Zone = SearchValues["location"];

/** A free-text zone as draftToValues would place it. */
function placeZone(text: string): Zone {
  const legacy = placeFromText(text);
  const place = cityFromText(text) ?? (legacy?.id === "caba" ? cityById("caba") : legacy);
  return place ? { label: place.label, lat: place.lat, lon: place.lon, radius_km: place.radius } : null;
}

/**
 * The zone of a draft draftToValues couldn't place, never a reason to stop:
 * the first place of «Santa Fe o Buenos Aires» (one zone per search), else
 * the whole country («cualquier lado de Argentina», or a zone we don't know). The note
 * says what we did; it doesn't ask for anything (noteNeedsChoice).
 */
export function zoneFromText(text: string): { location: Zone; note: string } {
  const raw = text.trim();
  const parts = zoneParts(raw);
  for (const [i, part] of parts.entries()) {
    const location = placeZone(withoutCountry(part));
    if (!location) continue;
    const rest = parts.filter((_, j) => j !== i);
    return {
      location,
      note: rest.length
        ? `Buscamos en ${location.label}: cada búsqueda sigue una zona. Para ${rest.join(" y ")}, creá otra búsqueda o ampliá el radio abajo.`
        : `Buscamos en ${location.label}. Si querés otra zona, cambiala abajo.`,
    };
  }
  if (isNationalZone(raw)) return { location: null, note: "Buscamos en todo el país. Si querés acotar la zona, cambiala abajo." };
  return { location: null, note: `«${raw}» no está en nuestra lista de zonas: buscamos en todo el país. Si querés acotarla, cambiala abajo.` };
}

/**
 * One draft as the structured form's initial values. `base` carries what the
 * text doesn't decide (sources, alert settings, the user's default place).
 * Returns the notes to show above the form (the worker's plus the zone's).
 */
/** A proposal by body type alone for an account whose plan can't save one. */
export const MODEL_LESS_DRAFT_NOTE = "Elegí marca y modelo: buscar solo por carrocería es de Particular y Pro.";

/**
 * The form's values and notes for one proposal. `modelLessSearch`: whether
 * the plan can search by body type alone; without it, the worker's advice for
 * a proposal without a model ("poné un precio máximo") can't be followed.
 */
export function draftToValues(
  draft: AssistedDraft,
  base: SearchValues,
  modelLessSearch = true,
  maxLocations: number | null = null,
): { values: SearchValues; notes: string[] } {
  const v = draft.values;
  let notes = [...draft.notes];
  if (!modelLessSearch && !v.make.trim() && !v.model.trim() && bodyTypeCodes(v.body_types).length) {
    notes = [...notes.filter((n) => !n.includes("sin elegir modelo")), MODEL_LESS_DRAFT_NOTE];
  }
  let location = base.location;
  let extraLocations = base.extra_locations;
  // Every place the text names, each «Santa Fe o Buenos Aires» split into its parts and the country
  // words dropped; drafts from before `locations` carry theirs in `location`.
  const texts = (v.locations.length ? v.locations : v.location ? [v.location] : []).flatMap(zoneParts);
  if (texts.length === 0 && v.location) {
    if (isNationalZone(v.location)) notes.push(NATIONAL_ZONE_NOTE);
  } else if (texts.length) {
    const places: NonNullable<SearchValues["location"]>[] = [];
    for (const text of texts) {
      const named = withoutCountry(text);
      const legacy = placeFromText(named);
      const place = cityFromText(named) ?? (legacy?.id === "caba" ? cityById("caba") : legacy) ?? provinceCapital(named);
      if (!place) {
        notes.push(`No reconocimos la zona «${text}»: elegila de la lista.`);
      } else if (!places.some((p) => p.lat === place.lat && p.lon === place.lon)) {
        places.push({ label: place.label, lat: place.lat, lon: place.lon, radius_km: v.radius_km ?? place.radius });
      }
    }
    const kept = maxLocations == null ? places : places.slice(0, maxLocations);
    if (kept.length < places.length) {
      notes.push(`Tu plan permite buscar en hasta ${inWords(maxLocations ?? 0)} zonas: dejamos ${kept.map((p) => p.label).join(", ")}.`);
    }
    if (kept.length) {
      location = kept[0];
      extraLocations = kept.slice(1);
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
      trims: v.trims,
      trim_strict: v.trim_strict,
      year_min: v.year_min,
      year_max: v.year_max,
      price_max: v.price_max,
      currency: v.currency,
      km_max: v.km_max,
      transmission: v.transmission,
      fuel: v.fuel,
      body_types: bodyTypeCodes(v.body_types),
      location,
      extra_locations: extraLocations,
      km_target: v.km_target,
      price_target: v.price_target,
      seller_type: v.seller_type,
    },
    notes,
  };
}

/** At most this many vehicles per request, the LLM's and the ones the user adds (worker: MAX_VEHICLES). */
export const ASSISTED_MAX_VEHICLES = 5;

/**
 * A vehicle the user adds on the review screen: the request's shared filters
 * (years, km, price, zone, alerts) from `from`, and the make, model and trim to pick.
 */
export function addedVehicle(from: SearchValues): SearchValues {
  return { ...from, name: "", make: "", model: "", trim: "", trims: [], trim_strict: false, body_types: [] };
}

/**
 * Room for new searches under enforced plan limits (one model = one search):
 * `capacity` more can be activated now; `upsell` is shown when asking to choose.
 */
export type SearchLimit = { capacity: number; maxProfiles: number; activeSearches: number; upsell: string | null };

/** After the parse: review every model, choose the ones that fit the plan, or none fits. */
export function afterParse(found: number, limit: SearchLimit | null | undefined): "review" | "choose" | "full" {
  if (!limit || found <= limit.capacity) return "review";
  return limit.capacity > 0 ? "choose" : "full";
}

/** "tu plan permite una búsqueda activa." or "te queda lugar para 2 búsquedas más en tu plan." */
export function roomText(limit: SearchLimit): string {
  const searches = (n: number, more = "") => (n === 1 ? `una búsqueda${more}` : `${n} búsquedas${more}`);
  return limit.activeSearches === 0
    ? `tu plan permite ${searches(limit.maxProfiles, limit.maxProfiles === 1 ? " activa" : " activas")}.`
    : `te queda lugar para ${searches(limit.capacity, " más")} en tu plan.`;
}

/** Picking models: like a radio with room for one, up to `capacity` otherwise. */
export function toggleChoice(selected: number[], index: number, capacity: number): number[] {
  if (selected.includes(index)) return selected.filter((i) => i !== index);
  if (capacity === 1) return [index];
  return selected.length < capacity ? [...selected, index] : selected;
}

/** "Ford Fiesta Titanium"; "SUV o Pick-up" for a draft without a model; else a placeholder. */
export function draftTitle(draft: AssistedDraft, index: number): string {
  const { make, model, trim, trims, body_types: bodyTypes } = draft.values;
  const versions = [...new Set([...trims, trim].filter(Boolean))];
  const bodies = isModelLess(draft.values) ? bodyTypesText(bodyTypes) : "";
  return [make, model, versions.join(" / ")].filter(Boolean).join(" ") || bodies || `Vehículo ${index + 1}`;
}
