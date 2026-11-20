import { type Filter, isResultFilter } from "@/lib/result-filters";
import { isSort, type Sort } from "@/lib/sorts";

/**
 * Where a car was opened from in a search's results list (valor justo §6.3):
 * the search, the order in use, the tab (a place on «Nuevos» isn't one on
 * «Todos») and the 1-based place it had. The results page adds them to the
 * card's link as src, ord, flt and pos (s, f and p are already that page's
 * sort, filter and page number); /app, /app/saved and the alerts don't.
 */
export type ListOrigin = { profileId: number; sort: Sort; filter: Filter; position: number };

/** What a URL can carry: each part checked on its own, null when it isn't valid. */
export type ListOriginParams = { profileId: number | null; sort: Sort | null; filter: Filter | null; position: number | null };

const POSITIVE_INT = /^[1-9]\d{0,8}$/;

/** A listing card's link: the bare listing page, or with the list's src, ord, flt and pos. */
export function listingHref(listingId: number | null, origin?: ListOrigin | null): string {
  const path = `/app/listings/${listingId}`;
  if (!origin) return path;
  const qs = new URLSearchParams({
    src: String(origin.profileId),
    ord: origin.sort,
    flt: origin.filter,
    pos: String(origin.position),
  });
  return `${path}?${qs}`;
}

function positiveInt(value: unknown): number | null {
  return typeof value === "string" && POSITIVE_INT.test(value) ? Number(value) : null;
}

/**
 * The listing page's src, ord, flt and pos. A src or pos that isn't a positive
 * integer, an ord that isn't a known sort and a flt that isn't a results tab
 * are dropped, each on its own; whether src is one of
 * the user's searches holding the listing is markSeen's check.
 */
export function parseListOrigin(query: Record<string, string | string[] | undefined>): ListOriginParams {
  return {
    profileId: positiveInt(query.src),
    sort: isSort(query.ord) ? query.ord : null,
    filter: isResultFilter(query.flt) ? query.flt : null,
    position: positiveInt(query.pos),
  };
}

/** The ids of the listings a «Ver más» page adds: the list renders from the first row, the event wants only the new ones. */
export function pageListingIds(
  shown: ReadonlyArray<{ listing_id: number | null }>,
  page: number,
  pageSize: number,
): number[] {
  return shown
    .slice(pageSize * (page - 1))
    .map((card) => card.listing_id)
    .filter((id): id is number => id != null);
}

function positiveIntOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}

/**
 * markSeen's first check of what the client sent (a server action takes
 * anything): each part kept only when valid, the rest null. The search's
 * ownership is checked against the database after this.
 */
export function cleanListOrigin(raw: unknown): ListOriginParams {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    profileId: positiveIntOrNull(o.profileId),
    sort: isSort(o.sort) ? o.sort : null,
    filter: isResultFilter(o.filter) ? o.filter : null,
    position: positiveIntOrNull(o.position),
  };
}

/** The most ids one search_results_viewed takes (a page is 50). */
export const MAX_PAGE_IDS = 200;

/** trackResultsViewed's check: null when any part is invalid, the event isn't recorded. */
export function cleanResultsViewed(
  profileId: unknown,
  sort: unknown,
  filter: unknown,
  page: unknown,
  listingIds: unknown,
): { profileId: number; sort: Sort; filter: Filter; page: number; listingIds: number[] } | null {
  const id = positiveIntOrNull(profileId);
  const p = positiveIntOrNull(page);
  if (id == null || p == null || !isSort(sort) || !isResultFilter(filter)) return null;
  if (!Array.isArray(listingIds) || listingIds.length === 0 || listingIds.length > MAX_PAGE_IDS) return null;
  const ids = listingIds.map(positiveIntOrNull);
  if (ids.some((x) => x == null)) return null;
  return { profileId: id, sort, filter, page: p, listingIds: ids as number[] };
}
