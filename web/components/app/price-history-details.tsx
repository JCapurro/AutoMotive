"use client";

import { useRef } from "react";

import { trackPriceHistoryExpanded } from "@/app/app/listings/actions";
import { PRICE_TRACK } from "@/lib/copy";

/**
 * PAR-03: the dated price list, closed. Opening it logs
 * price_history_expanded once per view, however many times it is toggled.
 */
export function PriceHistoryDetails({
  listingId,
  drops,
  days,
  children,
}: {
  listingId: number;
  drops: number;
  days: number;
  children: React.ReactNode;
}) {
  const done = useRef(false);
  return (
    <details
      data-testid="price-history-details"
      className="mt-2"
      onToggle={(event) => {
        if (!event.currentTarget.open || done.current) return;
        done.current = true;
        void trackPriceHistoryExpanded(listingId, drops, days);
      }}
    >
      <summary className="cursor-pointer text-sm font-semibold">{PRICE_TRACK.historyToggle}</summary>
      {children}
    </details>
  );
}
