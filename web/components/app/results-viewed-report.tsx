"use client";

import { useEffect, useRef } from "react";

import { trackResultsViewed } from "@/app/app/searches/actions";
import type { Filter } from "@/lib/result-filters";
import type { Sort } from "@/lib/sorts";

/**
 * Valor justo §6.3: search_results_viewed once per (search, sort, filter, page).
 * The page refreshes itself while a search is being prepared, so the key, not
 * the render, decides. Only the page's own ids: «Ver más» renders from the
 * first row. First-party only (track()), never to Pixel or GA.
 */
export function ResultsViewedReport({
  profileId,
  sort,
  filter,
  page,
  listingIds,
}: {
  profileId: number;
  sort: Sort;
  filter: Filter;
  page: number;
  listingIds: number[];
}) {
  // Strict Mode remounts effects in development; the ref survives it, so it counts once.
  const done = useRef<string | null>(null);
  const ids = listingIds.join(",");
  useEffect(() => {
    if (!ids) return;
    const key = `${profileId}:${sort}:${filter}:${page}`;
    if (done.current === key) return;
    done.current = key;
    void trackResultsViewed(profileId, sort, filter, page, ids.split(",").map(Number));
  }, [profileId, sort, filter, page, ids]);
  return null;
}
