import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { SellerRequest } from "@/components/agencia/seller-request";
import { webConfig } from "@/lib/config";
import { DISTANCE_TEXT, requestStatusText, sellerCarText, sellerErrorText } from "@/lib/dealer-buying";
import { dealerSellers } from "@/lib/dealer-buying-server";
import { myDealer } from "@/lib/dealer-server";

export const metadata: Metadata = { title: "Vendedores" };

/**
 * People who want to sell their car and ticked «También me interesa que
 * agencias me contacten para comprarlo». The agency sees only coarse data
 * (the car if they gave it, a distance band) and asks; the seller decides.
 * The contact shows only after the seller accepts. Behind dealer_program.sellers_enabled.
 */
export default async function SellersPage() {
  const [dealer, { dealerSellers: config }] = await Promise.all([myDealer(), webConfig()]);
  if (!config.sellersEnabled) notFound();
  if (!dealer) redirect("/agencia");
  const { rows, error } = dealer.approved ? await dealerSellers() : { rows: [], error: "not_approved" };

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="type-heading text-[1.9rem] leading-tight">Vendedores</h1>
        <p className="text-sm text-muted-foreground">
          Personas que tienen que vender su auto y nos dijeron que les interesa que una agencia se lo compre. Pedí el contacto: le
          avisamos al vendedor y él decide. Si acepta, ves acá su nombre y lo que eligió compartir. Hasta {config.requestsPerDay}{" "}
          pedidos por día.
        </p>
      </header>

      {error ? (
        <p role="status" data-testid="sellers-error" className="rounded-lg bg-muted p-4 text-[15px]">
          {error === "not_approved" ? "Vas a ver vendedores con el plan Pro activo." : sellerErrorText(error)}
        </p>
      ) : rows.length === 0 ? (
        <p data-testid="sellers-empty" className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
          Por ahora no hay vendedores cerca de tu agencia.
        </p>
      ) : (
        <ul className="divide-y border-t-2 border-foreground" data-testid="sellers-list">
          {rows.map((s) => (
            <li key={s.ref} className="grid gap-2 py-4 sm:grid-cols-[1fr_auto] sm:items-start">
              <div className="min-w-0 space-y-1">
                <p className="font-semibold">{sellerCarText(s)}</p>
                <p className="text-sm text-muted-foreground">
                  {DISTANCE_TEXT[s.distance]} · {s.recent ? "Nos lo dijo este mes" : "Nos lo dijo hace más de un mes"}
                </p>
                {s.requestStatus ? <p className="text-sm">{requestStatusText(s.requestStatus)}</p> : null}
                {s.requestStatus === "accepted" ? (
                  <p className="text-sm font-medium" data-testid="seller-contact">
                    {[s.sharedName, s.sharedPhone, s.sharedEmail].filter(Boolean).join(" · ")}
                  </p>
                ) : null}
              </div>
              {s.canRequest ? (
                <SellerRequest sellerRef={s.ref} />
              ) : !s.requestStatus ? (
                <p className="text-xs text-muted-foreground">Ya recibió varios pedidos esta semana.</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
