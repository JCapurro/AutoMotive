import { Store } from "lucide-react";

import { cn } from "@/lib/utils";

export const DEALER_LABEL = "Agencia";

/**
 * The «Agencia» chip (spec §6.4, C1): a car an agency loaded or synced, with
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
        "inline-flex max-w-full items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap text-foreground",
        className,
      )}
    >
      <Store className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{withName ? `${DEALER_LABEL} · ${name}` : DEALER_LABEL}</span>
    </span>
  );
}
