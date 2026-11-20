import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { MarketView, type MarketListing } from "@/components/agencia/market-view";
import { PriceWhyBlock } from "@/components/agencia/price-why";
import { marketBasisChip, marketBasisText, parseMarket } from "@/lib/dealer-insights";
import { myDealer, priceContexts, stockInsights, whyOf } from "@/lib/dealer-server";
import { daysSince, money, vehicle } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Mercado" };

/**
 * «Ver el mercado» of one car: the listings its price is compared against
 * (dealer_market_listings: same model, year ±1, active, seen in the last 30
 * days, every source but the agencies' own stock), with the car placed among
 * them. Public listings only; nothing about buyers.
 */
export default async function ItemMarketPage({ params }: PageProps<"/agencia/stock/[itemId]/mercado">) {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const { itemId: raw } = await params;
  if (!/^\d+$/.test(raw)) notFound();
  const itemId = Number(raw);
  const supabase = await createClient();
  const [insights, contexts, { data, error }, { data: sources }] = await Promise.all([
    stockInsights(),
    priceContexts(),
    supabase.rpc("dealer_market_listings", { p_item_id: itemId }),
    supabase.from("sources").select("id, name"),
  ]);
  const insight = insights.find((r) => r.item_id === itemId);
  if (!insight) notFound();
  if (error) console.error("dealer_market_listings:", error.code);

  const sourceName = new Map((sources ?? []).map((s) => [s.id, s.name]));
  const listings: MarketListing[] = (data ?? []).map((l) => ({
    id: l.listing_id,
    title: [vehicle({ make: insight.make, model: insight.model }), l.trim].filter(Boolean).join(" ") || l.title,
    year: l.year,
    km: l.mileage_km,
    inRef: l.in_ref !== false,
    priceUsd: Number(l.price_usd),
    priceShown: l.currency === "ARS" ? `${money(l.price, "ARS")} ≈ ${money(l.price_usd, "USD")}` : money(l.price_usd, "USD"),
    source: sourceName.get(l.source) ?? l.source,
    seller: l.seller_type === "private" || l.seller_type === "dealer" ? l.seller_type : null,
    location: l.location_text,
    days: daysSince(l.first_seen_at),
    url: l.url?.startsWith("https://") ? l.url : null,
  }));
  const market = parseMarket(insight.market);
  const model = vehicle({ make: insight.make, model: insight.model }) || "Auto";
  const years = insight.year ? `${insight.year - 1} a ${insight.year + 1}` : "";

  return (
    <div className="space-y-6">
      <Link href="/agencia/stock" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Tu stock
      </Link>
      <header className="space-y-1">
        <h1 className="type-heading text-[1.9rem] leading-tight">El mercado del {model}{years ? ` ${years}` : ""}</h1>
        <p className="text-sm text-muted-foreground">
          Los avisos del modelo de tu {vehicle({ make: insight.make, model: insight.model, trim: insight.trim, year: insight.year })}, año ±1, vistos en los
          últimos 30 días en todas las fuentes. {marketBasisText(market)} Pesos al dólar blue del día. Son precios publicados, no de venta.{" "}
          <Link href={`/agencia/stock/${itemId}`} className="underline underline-offset-2">Editar el auto</Link>
        </p>
      </header>
      <PriceWhyBlock why={whyOf(insight, contexts)} />
      <MarketView
        refLabel={marketBasisChip(market)}
        listings={listings}
        own={{
          name: [insight.trim, insight.year].filter(Boolean).join(" ") || model,
          year: insight.year,
          priceUsd: insight.price_usd,
          priceShown: insight.currency === "ARS" && insight.price_usd ? `${money(insight.price, "ARS")} ≈ ${money(insight.price_usd, "USD")}` : money(insight.price, insight.currency),
        }}
      />
    </div>
  );
}
