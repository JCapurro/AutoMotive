/**
 * Autoguardado del modo asistido (sección 8.4, paso 5 bis): a request the
 * worker read without doubts is saved as soon as it arrives, and the review
 * screen becomes "Tu búsqueda ya está activa" with the form below to adjust it.
 * Anything the user still has to decide (several vehicles, a model to pick,
 * no room in the plan) keeps the normal review. A zone the text names but we
 * couldn't place doesn't: it becomes the first place we know, or the whole
 * country, with a note to adjust it.
 */
import { type AssistedDraft, NATIONAL_ZONE_NOTE, type SearchLimit, zoneFromText } from "@/lib/assisted";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";
import type { DetectedLocation } from "@/lib/search-location";

export { zoneFromText };

/** A new search with no zone starts at the approximate one, with this radius (search-form.tsx draftFrom). */
export const AUTOSAVE_RADIUS_KM = 30;

function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/**
 * A note that asks the user to choose or fill something: «elegí marca y
 * modelo», «No encontramos…», «Falta el modelo…», «No reconocimos la zona…».
 * Informative ones («Interpretamos goltrend como…», «No dijiste la moneda»)
 * don't stop the autosave: the user sees them above the form to adjust.
 */
export function noteNeedsChoice(note: string): boolean {
  return /\beleg|\bno encontramos\b|\bfalta\b|\bno reconocimos\b|\bcompleta/.test(fold(note));
}

/** make and model exactly as the catalog lists them (case-insensitive). */
export function inCatalog(catalog: Catalog, make: string, model: string): boolean {
  const mk = fold(make.trim());
  const md = fold(model.trim());
  if (!mk || !md) return false;
  return catalog.some((m) => fold(m.make) === mk && m.models.some((x) => fold(x.model) === md));
}

/** The notes draftToValues adds for a zone it didn't place: the autosave places it itself (zoneFromText). */
export function isZoneNote(note: string): boolean {
  return note === NATIONAL_ZONE_NOTE || fold(note).startsWith("no reconocimos la zona");
}

/**
 * The values (and the notes to show above the form) to save without asking,
 * or null when the user has to review. `drafts`: the worker's output;
 * `values`/`notes`: the single draft as the form would open it
 * (draftToValues). A draft without a zone takes the approximate one, as a new
 * form would; with no zone at all, the user picks it. A zone the text names
 * but draftToValues couldn't place is resolved by zoneFromText.
 */
export function autoSaveValues({
  drafts,
  values,
  notes,
  catalog,
  limit,
  approximateLocation,
}: {
  drafts: AssistedDraft[];
  values: SearchValues;
  notes: string[];
  catalog: Catalog;
  limit: SearchLimit | null | undefined;
  approximateLocation: DetectedLocation | null | undefined;
}): { values: SearchValues; notes: string[] } | null {
  if (drafts.length !== 1 || !drafts[0].resolved) return null;
  if (limit && limit.capacity < 1) return null;
  if (!inCatalog(catalog, values.make, values.model)) return null;
  const zoneText = drafts[0].values.location.trim();
  const unplaced = zoneText !== "" && notes.some(isZoneNote);
  const kept = unplaced ? notes.filter((n) => !isZoneNote(n)) : notes;
  if (kept.some(noteNeedsChoice)) return null;
  if (unplaced) {
    const zone = zoneFromText(zoneText);
    return { values: { ...values, location: zone.location }, notes: [...kept, zone.note] };
  }
  const location = values.location
    ?? (approximateLocation
      ? { label: approximateLocation.label, lat: approximateLocation.lat, lon: approximateLocation.lon, radius_km: AUTOSAVE_RADIUS_KM }
      : null);
  if (!location) return null;
  return { values: { ...values, location }, notes };
}

/** The same proposal as last time (a rewritten request read the same way): compare what would be saved. */
export function sameProposal(a: SearchValues | null | undefined, b: SearchValues | null | undefined): boolean {
  if (!a || !b) return false;
  return JSON.stringify(a) === JSON.stringify(b);
}
