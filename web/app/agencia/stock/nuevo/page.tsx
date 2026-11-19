import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { StockItemForm } from "@/components/agencia/stock-item-form";
import { loadCatalog } from "@/lib/catalog";
import { myDealer } from "@/lib/dealer-server";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Cargar un auto" };

export default async function NewItemPage() {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const catalog = await loadCatalog(await createClient());
  return (
    <div className="space-y-5">
      <div>
        <h1 className="type-heading text-[1.9rem] leading-tight">Cargar un auto</h1>
        <p className="text-sm text-muted-foreground">
          ¿Tenés muchos? <Link href="/agencia/stock/planilla" className="underline underline-offset-2">Subí tu planilla</Link>.
        </p>
      </div>
      <StockItemForm catalog={catalog} dealerId={dealer.id} />
    </div>
  );
}
