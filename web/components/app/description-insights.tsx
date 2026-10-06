import { priceContext, sellerStatements, type DescriptionListing } from "@/lib/description";
import type { PriceRef } from "@/lib/types";

export function SellerDescription({ listing }: { listing: DescriptionListing }) {
  const statements = sellerStatements(listing);
  if (!statements.length) return null;
  return (
    <section data-testid="seller-description">
      <h2 className="type-heading text-[21px] leading-tight">Según el vendedor</h2>
      <p className="mt-2 text-sm text-muted-foreground">Datos que leímos en el aviso con ayuda de IA. Son afirmaciones del vendedor; conviene confirmarlas.</p>
      <dl className="mt-3 divide-y">
        {statements.map((s) => (
          <div key={s.field} className="py-3">
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{s.label}</dt>
            <dd className="mt-1 text-[15px]">
              {s.value}
              {s.conflict ? <span className="ml-2 text-sm font-semibold text-warn">Difiere de la ficha: conviene confirmar.</span> : null}
              <details className="mt-1 text-sm text-muted-foreground">
                <summary className="cursor-pointer underline decoration-border underline-offset-3">Ver qué dice el aviso</summary>
                {s.quotes.map((quote) => <blockquote key={quote} className="mt-2 border-l-2 border-mark pl-3 whitespace-pre-line">“{quote}”</blockquote>)}
              </details>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function DescriptionPriceContext({ listing, refs, minN }: { listing: DescriptionListing; refs: PriceRef | null; minN: number }) {
  const { intro, factors } = priceContext(listing, refs, minN);
  if (!factors.length) return null;
  return (
    <div className="mt-5 border-t pt-4" data-testid="description-price-context">
      <h3 className="text-base font-semibold">Qué puede influir en el precio</h3>
      <p className="mt-2 text-sm text-muted-foreground">{intro}</p>
      <ul className="mt-2 divide-y">
        {factors.map((factor) => <li key={factor} className="py-2 text-[15px]">{factor}</li>)}
      </ul>
      <p className="mt-2 text-sm text-muted-foreground">Podés revisar las frases originales en «Según el vendedor».</p>
    </div>
  );
}
