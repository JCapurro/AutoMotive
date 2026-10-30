import { CostEstimateDetails } from "@/components/app/cost-estimate-details";
import { COST_ESTIMATE } from "@/lib/copy";
import type { CostView } from "@/lib/cost-estimate-data";
import { costDetail } from "@/lib/cost-estimate-view";
import { cn } from "@/lib/utils";

/**
 * PAR-01: the total cost estimate in the listing page's price block, in place
 * of the old fixed «8–10 %» notice: the header (lib/cost-estimator.ts
 * costLine) and a closed breakdown. Rendered only with the plan's total_cost
 * flag and something to estimate (lib/cost-estimate-data.ts returns null otherwise).
 */
export function CostEstimate({ listingId, view, className }: { listingId: number; view: CostView | null; className?: string }) {
  if (!view) return null;
  const { estimate } = view;
  const missing = estimate.missing.filter((m) => m.code !== "fx").length;
  const detail = estimate.p_ars != null ? costDetail(estimate, view.cfg, view.zones, view.from, view.sellerKind) : null;
  return (
    <div data-testid="cost-estimate" className={cn("mt-2 min-w-0 text-[13px] font-normal leading-snug [font-stretch:100%]", className)}>
      <p data-testid="cost-estimate-headline" className="font-semibold break-words text-foreground">
        {view.line}
      </p>
      {detail ? (
        <CostEstimateDetails listingId={listingId} jurisdiction={estimate.jurisdiction} missing={missing}>
          <dl className="mt-1.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-0.5">
            {detail.rows.map((row) => (
              <div key={row.label} className="contents">
                <dt className="min-w-0 text-muted-foreground">{row.label}</dt>
                <dd className="text-right tabular-nums whitespace-nowrap">{row.amount}</dd>
              </div>
            ))}
          </dl>
          <ul className="mt-1.5 space-y-0.5 break-words text-muted-foreground">
            {detail.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          {detail.sources.length ? (
            <div data-testid="cost-estimate-sources" className="mt-1.5 text-[12px] text-muted-foreground">
              <p className="font-semibold">{COST_ESTIMATE.sources}</p>
              <ul className="space-y-0.5 break-words">
                {detail.sources.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </CostEstimateDetails>
      ) : null}
    </div>
  );
}
