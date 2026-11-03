import { answerSellIntent } from "@/app/vender-mi-auto/actions";
import { SELL_INTENT } from "@/lib/sell-intent";

/**
 * PAR-05, Prueba B: one quiet line in the listing page, for an account that
 * hasn't answered (the page decides, lib/sell-intent.ts showFichaQuestion).
 * «Sí» opens /vender-mi-auto; «No» comes back here, without the line.
 */
export function SellIntentLine({ listingId, className }: { listingId: number; className?: string }) {
  return (
    <form action={answerSellIntent} data-testid="sell-intent-line" className={className}>
      <input type="hidden" name="volver" value={`/app/listings/${listingId}`} />
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
        <span>{SELL_INTENT.question}</span>
        <span className="flex gap-3">
          <button type="submit" name="r" value="yes" className="font-semibold text-foreground underline underline-offset-2">
            {SELL_INTENT.yes}
          </button>
          <button type="submit" name="r" value="no" className="font-semibold text-foreground underline underline-offset-2">
            {SELL_INTENT.no}
          </button>
        </span>
      </p>
    </form>
  );
}
