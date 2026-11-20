import { type Filter, isResultFilter } from "@/lib/result-filters";
import { isSort, type Sort } from "@/lib/sorts";

/**
 * Where a car was opened from in a search's results list (valor justo §6.3):
 * the search, the order in use and the 1-based place it had. The results page
 * adds them to the card's link as src, ord and pos (s and p are already that
 * page's sort and page number); /app, /app/saved and the alerts don't.
 */
export type ListOrigin = { profileId: number; sort: Sort; position: number };

/** What a URL can carry: each part checked on its own, null when it isn't valid. */
export type ListOriginParams = { profileId: number | null; sort: Sort | null; position: number | null };

const POSITIVE_INT = /^[1-9]\d{0,8}$/;

/** A listing card's link: the bare listing page, or with the list's src, ord and pos. */
export function listingHref(listingId: number | null, origin?: ListOrigin | null): string {
  const path = `/app/listings/${listingId}`;
  if (!origin) return path;
  const qs = new URLSearchParams({ src: String(origin.profileId), ord: origin.sort, pos: String(origin.position) });
  return `${path}?${qs}`;
}

function positiveInt(value: unknown): number | null {
  return typeof value === "string" && POSITIVE_INT.test(value) ? Number(value) : null;
}

/**
 * The listing page's src, ord and pos. A src or pos that isn't a positive
 * integer and an ord that isn't a known sort are dropped; whether src is one of
 * the user's searches holding the listing is markSeen's check.
 */
export function parseListOrigin(query: Record<string, string | string[] | undefined>): ListOriginParams {
  return {
    profileId: positiveInt(query.src),
    sort: isSort(query.ord) ? query.ord : null,
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
