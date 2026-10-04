"use client";

import { useEffect, useRef } from "react";

import { markSeen } from "@/app/app/listings/actions";
import { pixel } from "@/lib/meta-pixel";

/** Opening a listing marks it "Visto" and logs listing_detail_viewed (after render, not during it). */
export function ViewTracker({ listingId, notificationId }: { listingId: number; notificationId: number | null }) {
  // Strict Mode remounts effects in development; the ref survives it, so it counts once.
  const done = useRef<string | null>(null);
  useEffect(() => {
    const key = `${listingId}:${notificationId ?? ""}`;
    if (done.current === key) return;
    done.current = key;
    void markSeen(listingId, notificationId);
    pixel("ViewContent", { content_ids: [String(listingId)], content_type: "product" });
  }, [listingId, notificationId]);
  return null;
}
