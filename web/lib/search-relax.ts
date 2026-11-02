/**
 * Zero results in the form's preview: the same search with one hard filter
 * loosened, so the user sees what to change instead of leaving ("Sin la
 * versión GT Line: 34 publicaciones"). Each variant changes only what
 * preview_search actually filters by (versions count only with trim_strict).
 * The server action counts each variant (relaxSuggestions); the form applies
 * the chosen change to its fields.
 */
import { BODY_TYPE, SELLER_STRICT, bodyTypeCodes } from "@/lib/copy";
import { money, number } from "@/lib/format";
import { type SearchValues, isModelLess, selectedTrims } from "@/lib/search-form";

/** The fields a suggestion changes, as the form holds them (location null = toda la Argentina). */
export type RelaxChange = Partial<
  Pick<SearchValues, "trim_strict" | "seller_strict" | "year_min" | "year_max" | "price_max" | "km_max" | "transmission" | "fuel" | "body_types" | "location">
>;

export type RelaxKey = "trims" | "years" | "price" | "km" | "location" | "transmission" | "fuel" | "body_types" | "seller";

export type Relaxation = { key: RelaxKey; label: string; change: RelaxChange };
export type RelaxSuggestion = Relaxation & { count: number };

/** At most this many variants are counted per search (one preview_search each). */
export const MAX_RELAX_VARIANTS = 6;
/** At most this many suggestions are shown. */
export const MAX_RELAX_SUGGESTIONS = 3;

const YEAR_STEP = 2;
const PRICE_STEP = 1.2;

/** 13.200 → 13.000; 8.450 → 8.500; 30.400.000 → 30.000.000: two significant digits, never below `floor`. */
export function roundPrice(value: number, floor: number): number {
  const step = 10 ** Math.max(Math.floor(Math.log10(value)) - 1, 0);
  const rounded = Math.round(value / step) * step;
  return rounded > floor ? rounded : Math.ceil((floor + 1) / step) * step;
}

function versionsText(trims: string[]): string {
  return trims.length === 1 ? `Sin la versión ${trims[0]}` : `Cualquier versión (no solo ${trims.join(" / ")})`;
}

function yearsText(min: number | null, max: number | null): string {
  if (min != null && max != null) return min === max ? `Solo ${min}` : `${min}–${max}`;
  return min != null ? `Desde ${min}` : `Hasta ${max}`;
}

function priceText(amount: number, currency: SearchValues["currency"]): string {
  return currency === "ARS" ? `Hasta $ ${number(amount)}` : `Hasta ${money(amount, "USD")}`;
}

/**
 * The search with one filter loosened at a time, most likely to help first;
 * none for a model-less search (the hints are for a chosen model). `thisYear`
 * caps a widened «hasta».
 */
export function relaxVariants(v: SearchValues, thisYear = new Date().getFullYear()): Relaxation[] {
  if (isModelLess(v)) return [];
  const out: Relaxation[] = [];
  const trims = selectedTrims(v);
  if (v.trim_strict && trims.length) out.push({ key: "trims", label: versionsText(trims), change: { trim_strict: false } });
  if (v.year_min != null || v.year_max != null) {
    const year_min = v.year_min != null ? v.year_min - YEAR_STEP : null;
    const year_max = v.year_max != null ? Math.min(v.year_max + YEAR_STEP, Math.max(thisYear + 1, v.year_max)) : null;
    if (year_min !== v.year_min || year_max !== v.year_max) {
      out.push({ key: "years", label: yearsText(year_min, year_max), change: { year_min, year_max } });
    }
  }
  if (v.price_max != null) {
    const price_max = roundPrice(v.price_max * PRICE_STEP, v.price_max);
    out.push({ key: "price", label: priceText(price_max, v.currency), change: { price_max } });
  }
  if (v.km_max != null) out.push({ key: "km", label: "Sin tope de km", change: { km_max: null } });
  if (v.location) out.push({ key: "location", label: "Toda la Argentina", change: { location: null } });
  if (v.transmission) out.push({ key: "transmission", label: "Manual o automática", change: { transmission: "" } });
  if (v.fuel) out.push({ key: "fuel", label: "Cualquier combustible", change: { fuel: "" } });
  // PRO-01: the strict seller filter (preview_search applies it for Pro); the type stays as the preference.
  if (v.seller_strict && v.seller_type) out.push({ key: "seller", label: SELLER_STRICT.relax, change: { seller_strict: false } });
  const bodyTypes = bodyTypeCodes(v.body_types);
  if (bodyTypes.length) {
    const label = bodyTypes.length === 1 ? `No solo ${BODY_TYPE[bodyTypes[0]]}` : "Cualquier carrocería";
    out.push({ key: "body_types", label, change: { body_types: [] } });
  }
  return out.slice(0, MAX_RELAX_VARIANTS);
}

/** The search with a suggestion applied. */
export function applyRelax(v: SearchValues, change: RelaxChange): SearchValues {
  return { ...v, ...change };
}

/** The suggestions worth showing: some listing, most listings first, the variants' order on a tie. */
export function bestSuggestions(counted: RelaxSuggestion[], max = MAX_RELAX_SUGGESTIONS): RelaxSuggestion[] {
  return counted
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => s.count > 0)
    .sort((a, b) => b.s.count - a.s.count || a.i - b.i)
    .slice(0, max)
    .map(({ s }) => s);
}
