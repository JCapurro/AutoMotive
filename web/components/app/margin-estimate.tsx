import { MARGIN } from "@/lib/copy";
import { marginDetail, marginLine, type StoredMargin } from "@/lib/margin-view";
import { cn } from "@/lib/utils";

/**
 * PRO-02: the estimated gross margin against the dealers' median in the
 * listing page's price block, under the total cost: the full line (the same as the
 * Pro emails; the cards carry marginCardLine) and a closed detail of what it subtracts and what
 * it is not. Rendered only for Pro with a stored margin (lib/margin-data.ts).
 * Without enough dealers, only the line that says so (no detail to give).
 */
export function MarginEstimate({ margin, className }: { margin: StoredMargin | null; className?: string }) {
  const line = margin ? marginLine(margin) : null;
  if (!margin || !line) return null;
  if (margin.status === "few_dealers") {
    return (
      <p data-testid="margin-estimate-few-dealers" className={cn("mt-2 min-w-0 text-[13px] font-normal leading-snug break-words text-muted-foreground [font-stretch:100%]", className)}>
        {line}
      </p>
    );
  }
  return (
    <div data-testid="margin-estimate" className={cn("mt-2 min-w-0 text-[13px] font-normal leading-snug [font-stretch:100%]", className)}>
      <p data-testid="margin-estimate-headline" className="font-semibold break-words text-foreground">
        {line}
      </p>
      <details data-testid="margin-estimate-details" className="mt-1">
        <summary className="cursor-pointer text-[13px] font-semibold">{MARGIN.toggle}</summary>
        <ul className="mt-1.5 space-y-0.5 break-words text-muted-foreground">
          {marginDetail(margin).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
