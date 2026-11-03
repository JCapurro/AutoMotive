/**
 * Aviso de zona (docs/AVISO_ZONA.md): a search whose zone has almost nothing
 * says so with numbers, and the person widens it with one tap. Every search
 * keeps the zone it was saved with; nothing widens by itself (Juan,
 * 02/11/2026). The rules and the words, shared by the server helper
 * (lib/zone-notice-server.ts), the modo asistido's card and the results page.
 */
import { number } from "@/lib/format";
import type { SearchValues } from "@/lib/search-form";
import { APPROXIMATE_LABEL, APPROXIMATE_SUFFIX, DEVICE_LABEL } from "@/lib/search-location";
import type { Filters } from "@/lib/types";

/** The notice shows at this many visible results or fewer (app_config.low_results.max_results). */
export const ZONE_NOTICE_MAX_RESULTS = 3;
/** An option is offered only if the search would show at least this many. */
export const ZONE_NOTICE_TARGET = ZONE_NOTICE_MAX_RESULTS + 1;
/** The wider radii offered, smallest first: only the ones above the search's own. */
export const WIDER_RADII = [100, 200] as const;
/** A source whose first read hasn't started this long after the search (or its target) was created doesn't hold the notice. */
export const FIRST_READ_GRACE_MS = 5 * 60_000;
/** A first read that just ended still holds it this long: the worker matches its batch after closing the run. */
export const FIRST_READ_MATCH_MS = 3 * 60_000;
/** A target whose last read is this much older than the search reads the market again first (the worker's REACTIVATION_IDLE_SECONDS). */
export const STALE_READ_MS = 24 * 3_600_000;
/** The results page's title, where focus goes when the notice's buttons go away. */
export const SEARCH_TITLE_ID = "search-title";
/** The card asks every few seconds until the search is ready, and gives up after a while. */
export const ZONE_NOTICE_POLL_MS = 5_000;
export const ZONE_NOTICE_POLL_MAX_MS = 10 * 60_000;

export type WidenTo = (typeof WIDER_RADII)[number] | "pais";
/** Where the zone came from: the connection (autosave), the device, or a place the person named. */
export type ZoneKind = "ip" | "device" | "named";
export type ZonePlacement = "card" | "page";
/** The search's own zone: latitude, longitude and radius in km. */
export type Zone = [number, number, number];
/** `count`: what the search would show; `capped`: the trial shows no more than that («50+»). */
export type ZoneOption = { to: WidenTo; count: number; capped: boolean };
export type ZoneNoticeData = {
  profileId: number;
  /** The visible results now (search_result_counts.all_count). */
  count: number;
  /** «Laferrere», «tu zona aproximada», «tu ubicación». */
  place: string;
  kind: ZoneKind;
  zone: Zone;
  options: ZoneOption[];
  /** A target was created for this search: the model's market was still being collected. */
  cold: boolean;
};
/** `pending`: the search isn't ready to be counted yet (the card asks again). */
export type ZoneNoticeAnswer = { state: "pending" } | { state: "none" } | { state: "show"; notice: ZoneNoticeData };

export function isWidenTo(value: unknown): value is WidenTo {
  return value === "pais" || (WIDER_RADII as readonly unknown[]).includes(value);
}

export function zoneKind(label: string | null | undefined): ZoneKind {
  const text = (label ?? "").trim();
  if (text === APPROXIMATE_LABEL || text.endsWith(APPROXIMATE_SUFFIX)) return "ip";
  return text === DEVICE_LABEL ? "device" : "named";
}

/** The place in a sentence: «a 30 km de Laferrere», «… de tu zona aproximada». */
export function zonePlace(label: string | null | undefined): string {
  const text = (label ?? "").trim();
  if (text === APPROXIMATE_LABEL) return "tu zona aproximada";
  if (text === DEVICE_LABEL) return "tu ubicación";
  if (text.endsWith(APPROXIMATE_SUFFIX)) return text.slice(0, -APPROXIMATE_SUFFIX.length).trim() || "tu zona aproximada";
  return text || "la zona elegida";
}

/** The search's own zone, or null without one (the whole country). */
export function zoneOf(p: { origin_lat: number | null; origin_lon: number | null; radius_km: number | null }): Zone | null {
  if (p.origin_lat == null || p.origin_lon == null || p.radius_km == null || !(p.radius_km > 0)) return null;
  return [p.origin_lat, p.origin_lon, p.radius_km];
}

/** A zone as events store it (props.zone), or null. */
export function parseZone(value: unknown): Zone | null {
  if (!Array.isArray(value) || value.length !== 3) return null;
  const [lat, lon, radius] = value.map(Number);
  return [lat, lon, radius].every(Number.isFinite) ? [lat, lon, radius] : null;
}

export function sameZone(a: Zone | null, b: Zone | null): boolean {
  return a != null && b != null && a.every((value, i) => Math.abs(value - b[i]) < 1e-9);
}

export type NoticeProfile = {
  enabled: boolean;
  filters: unknown;
  origin_lat: number | null;
  origin_lon: number | null;
  radius_km: number | null;
  bootstrapped_at: string | null;
  rematch_requested_at: string | null;
};

/**
 * What can be told without counting: `none` (the notice never applies, or
 * not now), `pending` (wait: the search is being prepared) or `count`. Only
 * a search with a model and one zone of its own; the free trial's quota
 * reached hides it (FreeResultLimit explains why nothing new shows), and
 * «Dejar así» hides it for that zone. `count`: the visible results, null
 * when they couldn't be read. `reading`: a source still on its first read.
 */
export function noticeGate({ profile, count, quotaReached, dismissed, reading }: {
  profile: NoticeProfile;
  count: number | null;
  quotaReached: boolean;
  dismissed: Zone[];
  reading: boolean;
}): "none" | "pending" | "count" {
  const filters = (profile.filters ?? {}) as Filters;
  const zone = zoneOf(profile);
  if (!profile.enabled || !filters.make?.trim() || !filters.model?.trim()) return "none";
  if (!zone || filters.extra_locations?.length) return "none";
  if (quotaReached || dismissed.some((z) => sameZone(z, zone))) return "none";
  if (!profile.bootstrapped_at || profile.rematch_requested_at || reading || count == null) return "pending";
  return count <= ZONE_NOTICE_MAX_RESULTS ? "count" : "none";
}

/**
 * The options to offer: the smallest wider radius that brings the search to
 * ZONE_NOTICE_TARGET, then the whole country if it gets there too and shows
 * more than that radius (under the trial's cap both can read the same «N+»,
 * and the country would spend the last slots far away); none when no option
 * gets there. `count`: the visible
 * results now. `current`, `radii`, `country`: preview_search's count for the
 * current zone, each radius above it and no zone; an option's estimate is
 * `count` plus what it adds over the current zone. `cap`: the most an
 * enforced free trial can still show (null: no cap), shown as «N+».
 */
export function zoneOptions({ count, current, radii, country, cap }: {
  count: number;
  current: number;
  radii: { radius: (typeof WIDER_RADII)[number]; count: number }[];
  country: number;
  cap: number | null;
}): ZoneOption[] {
  const option = (to: WidenTo, preview: number): ZoneOption => {
    const total = count + Math.max(preview - current, 0);
    return cap != null && total > cap ? { to, count: cap, capped: true } : { to, count: total, capped: false };
  };
  const reaches = (o: ZoneOption) => o.count >= ZONE_NOTICE_TARGET;
  const radius = radii.map((r) => ({ preview: r.count, option: option(r.radius, r.count) })).find((r) => reaches(r.option));
  const whole = option("pais", country);
  const out = radius ? [radius.option] : [];
  if (reaches(whole) && (!radius || whole.count > radius.option.count)) out.push(whole);
  return out;
}

/** The filters with no place: the whole country (as the form saves it, search-form.ts toFilters). */
export function withoutPlace(filters: Filters): Filters {
  const rest = { ...filters };
  delete rest.location_label;
  delete rest.extra_locations;
  return rest;
}

/**
 * The modo asistido's draft after a widening, so the form below shows what
 * was saved and its next «Guardar cambios» doesn't undo it: the new radius
 * around the same place, or the whole country without the autosave's note on
 * where it searched.
 */
export function widenedDraft<D extends { values: SearchValues; notes: string[] }>(draft: D, to: WidenTo): D {
  const { values, notes } = draft;
  return to === "pais"
    ? { ...draft, values: { ...values, location: null, extra_locations: [] }, notes: notes.filter((n) => !n.startsWith("Buscamos en ")) }
    : { ...draft, values: { ...values, location: values.location && { ...values.location, radius_km: to } } };
}

/** The card's form key: SearchForm reads its values when it mounts, so a widened zone mounts it again. */
export function searchFormKey(location: SearchValues["location"]): string {
  return location ? `${location.lat},${location.lon},${location.radius_km}` : "pais";
}

function publications(n: number): string {
  return n === 1 ? "1 publicación" : `${n} publicaciones`;
}

/** «En tu zona no hay publicaciones ahora.» / «En tu zona hay solo 2 publicaciones ahora.» */
export function noticeHeadline(count: number): string {
  return count === 0 ? "En tu zona no hay publicaciones ahora." : `En tu zona hay solo ${publications(count)} ahora.`;
}

/** «Buscamos a 30 km de Laferrere.» */
export function zoneLine(n: ZoneNoticeData): string {
  return `Buscamos a ${number(n.zone[2])} km de ${n.place}.`;
}

/** The card's lead line: «A 30 km de Laferrere no hay publicaciones ahora.» */
export function cardLead(n: ZoneNoticeData): string {
  const where = `A ${number(n.zone[2])} km de ${n.place}`;
  return n.count === 0 ? `${where} no hay publicaciones ahora.` : `${where} hay solo ${publications(n.count)} ahora.`;
}

export const IP_ZONE_LINE = "La zona sale de tu conexión y puede no ser exacta.";

/** «Hasta 200 km · 14», «Todo el país · 50+». */
export function optionLabel(o: ZoneOption): string {
  const what = o.to === "pais" ? "Todo el país" : `Hasta ${number(o.to)} km`;
  return `${what} · ${number(o.count)}${o.capped ? "+" : ""}`;
}

/** What the tap changed: «Listo: ahora buscamos a 200 km de Laferrere.» */
export function widenedText(to: WidenTo, place: string): string {
  return to === "pais" ? "Listo: ahora buscamos en todo el país." : `Listo: ahora buscamos a ${number(to)} km de ${place}.`;
}

/** «Dejar así» on the results page, where the panel goes away. */
export const KEPT_TEXT = "Listo: dejamos la zona como está.";
export const WIDEN_FAILED = "No pudimos ampliar la zona. Probá de nuevo.";
export const KEEP_FAILED = "No pudimos guardar tu elección. Probá de nuevo.";
/** A tap on a notice whose search changed since (another tab or device): its counts were for the old zone. */
export const ZONE_CHANGED = "La búsqueda cambió. Volvé a abrirla para ver su zona.";
