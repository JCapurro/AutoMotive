import { Megaphone } from "lucide-react";

import { cn } from "@/lib/utils";

/** Juan, 20/11: a car that reaches a buyer through an agency's stock says so, always (worker twin: intelligence/copy.py DEALER_LABEL). */
export const DEALER_LABEL = "Promocionado";

/**
 * The «Promocionado» chip (spec §6.4, C1): a car an agency loaded or synced, with
 * the label the buyer always sees. Only with a name: dealer_name comes from
 * match_cards / dealer_badges / listing_dealer_card, which give it only with
 * the channel on and the agency approved and active.
 */
export function DealerBadge({ name, withName = false, className }: { name: string | null | undefined; withName?: boolean; className?: string }) {
  if (!name) return null;
  return (
    <span
      data-testid="dealer-badge"
      title={name}
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded bg-foreground px-1.5 py-0.5 text-[10px] font-bold tracking-wider whitespace-nowrap text-background uppercase",
        className,
      )}
    >
      <Megaphone className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{DEALER_LABEL}</span>
      {withName ? <span className="truncate font-semibold tracking-normal normal-case">· {name}</span> : null}
    </span>
  );
}
