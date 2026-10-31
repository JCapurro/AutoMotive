"use client";

import { useRef } from "react";

import { trackTotalCostExpanded } from "@/app/app/listings/actions";
import { COST_ESTIMATE } from "@/lib/copy";

/**
 * PAR-01: the closed breakdown under the total cost header. Opening it logs
 * total_cost_expanded once per view, however many times it is toggled.
 */
export function CostEstimateDetails({
  listingId,
  jurisdiction,
  missing,
  children,
}: {
  listingId: number;
  jurisdiction: string[] | null;
  missing: number;
  children: React.ReactNode;
}) {
  const done = useRef(false);
  return (
    <details
      data-testid="cost-estimate-details"
      className="mt-1"
      onToggle={(event) => {
        if (!event.currentTarget.open || done.current) return;
        done.current = true;
        void trackTotalCostExpanded(listingId, jurisdiction, missing);
      }}
    >
      <summary className="cursor-pointer text-[13px] font-semibold">{COST_ESTIMATE.toggle}</summary>
      {children}
    </details>
  );
}
