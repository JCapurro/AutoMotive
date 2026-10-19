/**
 * When the interpreter can't answer (worker down, error, timeout), the
 * structured form takes over. Instead of an empty form, this reads the
 * obvious parts of what the user typed (make and model from the catalog,
 * years, a USD or peso budget, km, gearbox) so they only correct and fill
 * the rest. Deliberately simple: anything unclear is left empty.
 */
import { cityById } from "@/lib/argentina-locations";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";

export type RoughDraft = Partial<Pick<SearchValues,
  "make" | "model" | "year_min" | "year_max" | "price_max" | "currency" | "km_max" | "transmission" | "location">>;

/** AMBA is the city and its suburbs: the city's center with this radius. */
export const AMBA_RADIUS_KM = 40;

function plain(text: string): string {
  return ` ${text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ")} `;
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasWord(haystack: string, word: string): boolean {
  const w = plain(word).trim();
  return Boolean(w) && new RegExp(`[^a-z0-9]${escape(w)}[^a-z0-9]`).test(haystack);
}

/** "11.500" → 11500, "12" → 12; null when it isn't a whole number. */
function whole(digits: string): number | null {
  const n = Number(digits.replace(/\./g, ""));
  return Number.isInteger(n) && n > 0 ? n : null;
}

const NUMBER = String.raw`(\d{1,3}(?:\.\d{3})+|\d+)`;

export function roughDraft(text: string, catalog: Catalog): RoughDraft {
  const t = plain(text);
  const draft: RoughDraft = {};

  // The longest model name found wins ("Focus" inside "Focus RS" stays Focus RS).
  let best: { make: string; model: string } | null = null;
  for (const make of catalog) {
    for (const model of make.models) {
      if (hasWord(t, model.model) && (!best || model.model.length > best.model.length)) best = { make: make.make, model: model.model };
    }
  }
  if (best) Object.assign(draft, best);
  else {
    const make = catalog.find((m) => hasWord(t, m.make));
    if (make) draft.make = make.make;
  }

  const years = [...t.matchAll(/[^0-9](19[5-9]\d|20[0-4]\d)(?![0-9])/g)].map((m) => Number(m[1]));
  if (years.length >= 2) {
    draft.year_min = Math.min(...years);
    draft.year_max = Math.max(...years);
  } else if (years.length === 1) {
    draft.year_min = years[0];
    if (!/en adelante|o mas nuevo|desde/.test(t)) draft.year_max = years[0];
  }

  const km = t.match(new RegExp(`${NUMBER}\\s*(mil)?\\s*(?:km|kms|kilometros)[^a-z]`));
  if (km) {
    const n = whole(km[1]);
    if (n) draft.km_max = km[2] ? n * 1000 : n;
  }

  const usd = t.match(new RegExp(`(?:usd|u\\$s|us\\$)\\s*${NUMBER}\\s*(mil)?`))
    ?? t.match(new RegExp(`${NUMBER}\\s*(mil)?\\s*(?:usd|u\\$s|dolares|verdes)`));
  const ars = t.match(new RegExp(`${NUMBER}\\s*(?:millones|palos)`));
  if (usd) {
    const n = whole(usd[1]);
    if (n) {
      draft.price_max = usd[2] ? n * 1000 : n;
      draft.currency = "USD";
    }
  } else if (ars) {
    const n = whole(ars[1]);
    if (n) {
      draft.price_max = n * 1_000_000;
      draft.currency = "ARS";
    }
  }

  const caba = cityById("caba");
  if (caba && /[^a-z](amba|gba|caba|capital federal)[^a-z]/.test(t)) {
    const amba = /[^a-z](amba|gba)[^a-z]/.test(t);
    draft.location = { label: caba.label, lat: caba.lat, lon: caba.lon, radius_km: amba ? AMBA_RADIUS_KM : 10 };
  }

  if (/[^a-z]manual[^a-z]/.test(t)) draft.transmission = "manual";
  else if (/[^a-z]automatic[ao][^a-z]|[^a-z]automat[^a-z]/.test(t)) draft.transmission = "automatic";
  return draft;
}
