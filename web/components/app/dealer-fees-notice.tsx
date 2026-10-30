import { effectiveSeller } from "@/lib/seller";
import { cn } from "@/lib/utils";

/** Shown for a dealer and for a «posible agencia» (F-02, lib/seller.ts). */
export function DealerFeesNotice({
  sellerType,
  dealerInferred,
  className,
}: {
  sellerType?: string | null;
  dealerInferred?: boolean | null;
  className?: string;
}) {
  if (effectiveSeller({ seller_type: sellerType, dealer_inferred: dealerInferred }) !== "dealer") return null;

  return (
    <p data-testid="dealer-fees-notice" className={cn("mt-2 text-[13px] font-normal leading-snug text-muted-foreground", className)}>
      Trámites y gestoría: 8–10% adicional estimado.
    </p>
  );
}
