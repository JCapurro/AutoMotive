import { cn } from "@/lib/utils";

export function DealerFeesNotice({ sellerType, className }: { sellerType?: string | null; className?: string }) {
  if (sellerType !== "dealer") return null;

  return (
    <p data-testid="dealer-fees-notice" className={cn("mt-2 text-[13px] font-normal leading-snug text-muted-foreground", className)}>
      Trámites y gestoría: 8–10% adicional estimado.
    </p>
  );
}
