import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { StockTable } from "@/components/agencia/stock-table";
import { Button } from "@/components/ui/button";
import { webConfig } from "@/lib/config";
import { stockRowView } from "@/lib/dealer-insights";
import { myDealer, stockInsights } from "@/lib/dealer-server";
import { firstImage } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Stock" };

const FILTERS = [
  { id: "available", label: "Disponibles" },
  { id: "reserved", label: "Reservados" },
  { id: "sold", label: "Vendidos" },
  { id: "all", label: "Todos" },
] as const;

/** dealer_stock_insights(), one row per car: price vs market, comparables, demand, days, status and whether it reaches buyers. */
export default async function StockPage({ searchParams }: PageProps<"/agencia/stock">) {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const q = await searchParams;
  const filter = FILTERS.find((f) => f.id === q.estado)?.id ?? "available";
  const supabase = await createClient();
  const [insights, { dealerProgram }, { data: photoRows }] = await Promise.all([
    stockInsights(),
    webConfig(),
    // The cover: the car's own photos, or its portal listing's for a synced one.
    supabase.from("dealer_stock_items").select("id, images, listings!dealer_stock_items_listing_id_fkey(images)").eq("dealer_id", dealer.id),
  ]);
  const photos = new Map((photoRows ?? []).map((r) => [r.id, firstImage(r.images) ?? firstImage(r.listings?.images)]));
  const rows = insights
    .filter((r) => filter === "all" || r.status === filter)
    .map((r) => stockRowView(r, dealerProgram.manualConfirmDays, photos.get(r.item_id) ?? null));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="type-heading text-[1.9rem] leading-tight">Tu stock</h1>
          <p className="text-sm text-muted-foreground">
            Precio contra autos del mismo modelo, año ±1, vistos en los últimos 30 días, en todas las fuentes. Pesos al dólar blue del día.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" className="h-9"><Link href="/agencia/stock/nuevo">Cargar un auto</Link></Button>
          <Button asChild variant="outline" className="h-9"><Link href="/agencia/stock/planilla">Subir planilla</Link></Button>
        </div>
      </div>
      <nav aria-label="Filtrar por estado" className="-mx-4 overflow-x-auto px-4">
        <ul className="flex gap-1">
          {FILTERS.map((f) => (
            <li key={f.id}>
              <Link
                href={f.id === "available" ? "/agencia/stock" : `/agencia/stock?estado=${f.id}`}
                aria-current={f.id === filter ? "page" : undefined}
                className={cn("inline-flex h-7 items-center rounded-lg px-2.5 text-xs whitespace-nowrap text-muted-foreground hover:bg-muted", f.id === filter && "bg-muted font-medium text-foreground")}
              >
                {f.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <StockTable rows={rows} unconfirmed={dealer.counts.unconfirmed} />
    </div>
  );
}
