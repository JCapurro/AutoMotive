import Link from "next/link";

import { CostEstimateDetails } from "@/components/app/cost-estimate-details";
import { COST_ESTIMATE } from "@/lib/copy";
import type { CostView } from "@/lib/cost-estimate-data";
import { costDetail } from "@/lib/cost-estimate-view";
import { cn } from "@/lib/utils";

/**
 * PAR-01: the total cost estimate in the listing page's price block, in place
 * of the old fixed «8–10 %» notice: the header (lib/cost-estimator.ts
 * costLine) and a closed, compact breakdown (Juan 02/11). Without the buyer's
 * locality there is no amount at all, only lineNoZone, linked to the search's
 * edit form when there is a search. Rendered only with the plan's total_cost
 * flag and something to estimate (lib/cost-estimate-data.ts returns null otherwise).
 */
export function CostEstimate({ listingId, view, className }: { listingId: number; view: CostView | null; className?: string }) {
  if (!view) return null;
  const { estimate } = view;
  const noZone = estimate.missing.some((m) => m.code === "zone");
  const missing = estimate.missing.filter((m) => m.code !== "fx").length;
  const detail = estimate.p_ars != null && !noZone ? costDetail(estimate, view.cfg) : null;
  const [before, after] = COST_ESTIMATE.lineNoZone.split(COST_ESTIMATE.noZoneLink);
  return (
    <div data-testid="cost-estimate" className={cn("mt-2 min-w-0 text-[13px] font-normal leading-snug [font-stretch:100%]", className)}>
      <p data-testid="cost-estimate-headline" className="font-semibold break-words text-foreground">
        {noZone && view.searchProfileId != null ? (
          <>
            {before}
            <Link href={`/app/searches/${view.searchProfileId}/edit`} className="underline">
              {COST_ESTIMATE.noZoneLink}
            </Link>
            {after}
          </>
        ) : (
          view.line
        )}
      </p>
      {detail ? (
        <CostEstimateDetails listingId={listingId} jurisdiction={estimate.jurisdiction} missing={missing}>
          <dl className="mt-1.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-0.5">
            {detail.rows.map((row) => (
              <div key={row.label} className={cn("contents", row.label === COST_ESTIMATE.total && "font-semibold")}>
                <dt className="min-w-0 text-muted-foreground">{row.label}</dt><dd className="text-right tabular-nums">{row.amount}</dd>
              </div>
            ))}
          </dl>
          <p data-testid="cost-estimate-footnote" className="mt-1.5 text-[12px] break-words text-muted-foreground">
            {detail.footnote}
          </p>
          {detail.sources.length ? (
            <details data-testid="cost-estimate-sources" className="mt-1 text-[12px] text-muted-foreground">
              <summary className="cursor-pointer underline">{COST_ESTIMATE.sourcesToggle}</summary>
              {detail.sources.map((s) => (
                <p key={s} className="mt-0.5 break-words">
                  {s}
                </p>
              ))}
            </details>
          ) : null}
        </CostEstimateDetails>
      ) : null}
    </div>
  );
}
