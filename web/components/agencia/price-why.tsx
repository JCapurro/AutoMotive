import { PRICE_WHY_NOTE, PRICE_WHY_TITLE, type PriceWhy } from "@/lib/dealer-price-reasons";

/** «Por qué puede estar abajo del mercado»: the possible explanations of a price off the market (lib/dealer-price-reasons.ts). */
export function PriceWhyBlock({ why }: { why: PriceWhy | null }) {
  if (!why) return null;
  return (
    <section id="por-que" className="scroll-mt-24 space-y-2 rounded-lg border bg-muted/40 p-4" data-testid="price-why">
      <h2 className="type-heading text-lg leading-tight">{PRICE_WHY_TITLE[why.side]}</h2>
      {why.reasons.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-[15px]">
          {why.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      ) : null}
      {why.verdict ? <p className="text-[15px] font-medium">{why.verdict}</p> : null}
      {why.wide ? <p className="text-sm">{why.wide}</p> : null}
      {why.missing ? <p className="text-sm">{why.missing}</p> : null}
      <p className="text-xs text-muted-foreground">{PRICE_WHY_NOTE}</p>
    </section>
  );
}
