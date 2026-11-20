import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { budgetText, buyMarketHref, demandLine, isOpportunity, modelName, sellerErrorText, supplyText, yearsText } from "@/lib/dealer-buying";
import { buyOpportunities } from "@/lib/dealer-buying-server";
import { myDealer } from "@/lib/dealer-server";

export const metadata: Metadata = { title: "Qué comprar" };

/**
 * «Qué comprar» (fase 3): the models people look for in the agency's zone and
 * it doesn't have in stock, by demand. Only aggregates, rounded in SQL: a
 * model shows only when 3 or more people look for it.
 */
export default async function BuyPage() {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const { rows, error } = dealer.approved ? await buyOpportunities() : { rows: [], error: "not_approved" };

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="type-heading text-[1.9rem] leading-tight">Qué comprar</h1>
        <p className="text-sm text-muted-foreground">
          Los modelos que busca la gente cerca de {dealer.locality_label} y vos no tenés en stock. Contamos búsquedas activas o
          de los últimos 90 días que incluyen tu zona. Mostramos un modelo solo si lo buscan 3 personas o más.
        </p>
      </header>

      {error ? (
        <p role="status" data-testid="buy-error" className="rounded-lg bg-muted p-4 text-[15px]">
          {error === "not_approved" ? "Vas a ver qué comprar con el plan Pro activo." : sellerErrorText(error)}
        </p>
      ) : rows.length === 0 ? (
        <p data-testid="buy-empty" className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
          Por ahora no hay modelos que busquen 3 personas o más en tu zona y que no tengas.
        </p>
      ) : (
        <ol className="divide-y border-t-2 border-foreground" data-testid="buy-list">
          {rows.map((o) => (
            <li key={`${o.make}-${o.model}`} className="grid gap-2 py-4 sm:grid-cols-[1fr_auto] sm:items-center">
              <div className="min-w-0 space-y-1">
                <p className="flex flex-wrap items-center gap-2 font-semibold">
                  {modelName(o)} <span className="font-normal text-muted-foreground">{yearsText(o.yearFrom, o.yearTo)}</span>
                  {isOpportunity(o) ? (
                    <span className="rounded-full bg-mark px-2 py-0.5 text-[11px] font-semibold text-[#14213d]">Poca oferta</span>
                  ) : null}
                </p>
                <p className="text-sm">
                  {demandLine(o)} · {budgetText(o.budget, o.budgetCurrency)} (mediana)
                </p>
                <p className="text-sm text-muted-foreground">{supplyText(o.supplyTotal, o.supplyNear)}</p>
              </div>
              {o.supplyTotal > 0 ? (
                <Link href={buyMarketHref(o)} className="text-sm font-medium underline underline-offset-2">
                  Ver esos avisos
                </Link>
              ) : null}
            </li>
          ))}
        </ol>
      )}
      <p className="text-xs text-muted-foreground">
        Son búsquedas guardadas en Ese Auto, no ventas. No mostramos quién busca ni desde dónde. «Poca oferta»: hay menos avisos
        publicados que búsquedas.
      </p>
    </div>
  );
}
