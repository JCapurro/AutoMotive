import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { SheetImport } from "@/components/agencia/sheet-import";
import { loadCatalog } from "@/lib/catalog";
import { webConfig } from "@/lib/config";
import { myDealer } from "@/lib/dealer-server";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Subir planilla" };

export default async function SheetPage() {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const [catalog, { dealerProgram }] = await Promise.all([loadCatalog(await createClient()), webConfig()]);
  return (
    <div className="space-y-5">
      <div className="max-w-2xl space-y-1">
        <h1 className="type-heading text-[1.9rem] leading-tight">Subí tu planilla</h1>
        <p className="text-sm text-muted-foreground">
          La que ya usás, como está: marca, modelo, versión, año, km y precio de venta. Antes de cargar te mostramos qué entendimos de cada fila.
          ¿Un solo auto? <Link href="/agencia/stock/nuevo" className="underline underline-offset-2">Cargalo a mano</Link>.
        </p>
      </div>
      <SheetImport catalog={catalog} photo={dealerProgram.photoImportEnabled} />
    </div>
  );
}
