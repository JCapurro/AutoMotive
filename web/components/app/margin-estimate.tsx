import { MARGIN } from "@/lib/copy";
import { figureLine } from "@/lib/format";
import { marginDetail, marginLine, marginPayload, type StoredMargin } from "@/lib/margin-view";
import { cn } from "@/lib/utils";

/**
 * PRO-02: the estimated gross margin against the dealers' median in the
 * listing page's decision panel, under the total cost: the full line (the same
 * as the Pro emails; the cards carry marginCardLine) with its amount set as a
 * figure, and a closed detail of what it subtracts and what it is not.
 * Rendered only for Pro with a stored margin (lib/margin-data.ts). Without
 * enough dealers, only the line that says so (no detail to give).
 */
export function MarginEstimate({ margin, className }: { margin: StoredMargin | null; className?: string }) {
  const line = margin ? marginLine(margin) : null;
  if (!margin || !line) return null;
  if (margin.status === "few_dealers") {
    return (
      <p data-testid="margin-estimate-few-dealers" className={cn("min-w-0 text-[13px] leading-snug break-words text-muted-foreground", className)}>
        {line}
      </p>
    );
  }
  const { label, figure, note } = figureLine(line);
  return (
    <div data-testid="margin-estimate" className={cn("min-w-0 text-[13px] leading-snug", className)}>
      <p data-testid="margin-estimate-headline" className="break-words">
        {label ? (
          <span className="block text-muted-foreground">
            {label}
            <span className="sr-only">: </span>
          </span>
        ) : null}
        {figure ? (
          <span className={cn("type-figure block text-[21px] leading-tight", marginPayload(margin).usd_max < 0 && "text-warn")}>{figure}</span>
        ) : null}
        {note ? <span className={cn("block", figure && "text-[12px] text-muted-foreground")}>{figure ? ` ${note}` : note}</span> : null}
      </p>
      <details data-testid="margin-estimate-details" className="mt-1">
        <summary className="cursor-pointer text-[13px] font-semibold">{MARGIN.toggle}</summary>
        <ul className="mt-1.5 space-y-0.5 break-words text-muted-foreground">
          {marginDetail(margin).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
