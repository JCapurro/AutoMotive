"use client";

import { useEffect, useRef } from "react";

import { markSeen } from "@/app/app/listings/actions";
import { pixel } from "@/lib/meta-pixel";
import { analyticsEvent } from "@/lib/google-analytics";
import type { ListOriginParams } from "@/lib/list-position";

/**
 * Opening a listing marks it "Visto" and logs listing_detail_viewed (after render, not during it).
 * From a results list, with the search, order and place it had (valor justo §6.3); first-party only.
 */
export function ViewTracker({
  listingId,
  notificationId,
  origin = null,
}: {
  listingId: number;
  notificationId: number | null;
  origin?: ListOriginParams | null;
}) {
  // Strict Mode remounts effects in development; the ref survives it, so it counts once.
  const done = useRef<string | null>(null);
  const profileId = origin?.profileId ?? null;
  const sort = origin?.sort ?? null;
  const position = origin?.position ?? null;
  useEffect(() => {
    const key = `${listingId}:${notificationId ?? ""}:${profileId ?? ""}:${sort ?? ""}:${position ?? ""}`;
    if (done.current === key) return;
    done.current = key;
    const from = profileId != null || sort != null || position != null ? { profileId, sort, position } : null;
    void markSeen(listingId, notificationId, from);
    pixel("ViewContent", { content_ids: [String(listingId)], content_type: "product" });
    analyticsEvent("view_item", { item_id: String(listingId), content_type: "vehicle_listing" });
  }, [listingId, notificationId, profileId, sort, position]);
  return null;
}
