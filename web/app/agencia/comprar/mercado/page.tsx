import { ArrowLeft, ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { modelName, parseBuyMarketQuery, sellerErrorText, yearsText } from "@/lib/dealer-buying";
import { buyMarketListings } from "@/lib/dealer-buying-server";
import { myDealer } from "@/lib/dealer-server";
import { daysSince, km, money } from "@/lib/format";

export const metadata: Metadata = { title: "Avisos del mercado" };

/** The public listings behind a «Qué comprar» row: same model, years asked for, seen in 30 days, cheapest first. */
export default async function BuyMarketPage({ searchParams }: PageProps<"/agencia/comprar/mercado">) {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const q = parseBuyMarketQuery(await searchParams);
  if (!q) notFound();
  const { rows, error } = await buyMarketListings(q);
  const name = modelName(q);
  const near = rows.filter((r) => r.near).length;

  return (
    <div className="space-y-5">
      <Link href="/agencia/comprar" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Qué comprar
      </Link>
      <header className="space-y-1">
        <h1 className="type-heading text-[1.9rem] leading-tight">
          {name} {yearsText(q.yearFrom, q.yearTo)}
        </h1>
        <p className="text-sm text-muted-foreground">
          Avisos activos vistos en los últimos 30 días, en todas las fuentes salvo el stock de agencias. {rows.length} en total, {near} a
          menos de 50 km de tu agencia. Son precios publicados, no de venta.
        </p>
      </header>
      {error ? (
        <p role="status" className="rounded-lg bg-muted p-4 text-[15px]">{sellerErrorText(error)}</p>
      ) : rows.length === 0 ? (
        <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">No hay avisos publicados de este modelo.</p>
      ) : (
        <ul className="divide-y border-t-2 border-foreground" data-testid="buy-market">
          {rows.map((l) => {
            const url = l.url?.startsWith("https://") ? l.url : null;
            return (
              <li key={l.listing_id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">
                    {[l.trim || l.title, l.year].filter(Boolean).join(" · ")}
                    {l.near ? <span className="ml-2 text-xs text-muted-foreground">cerca tuyo</span> : null}
                  </p>
                  <p className="text-muted-foreground">
                    {[km(l.mileage_km), l.location_text, `hace ${daysSince(l.first_seen_at)} días`].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-semibold">{l.currency === "ARS" ? money(l.price, "ARS") : money(l.price_usd ?? l.price, "USD")}</span>
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2">
                      Ver <ExternalLink className="size-3.5" aria-hidden />
                    </a>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
