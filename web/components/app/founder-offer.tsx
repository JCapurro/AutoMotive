"use client";
import { BadgePercent } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { startPayment } from "@/app/app/pro/billing-actions";
import { Button } from "@/components/ui/button";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { founderOfferTerms, planPrice, type FounderOffer } from "@/lib/pro";

/** Pro at the founder price, only for whoever opens the private link (/fundador/<code>). */
export function FounderOfferCard({ code, founder, version, automatic }: { code: string; founder: FounderOffer; version: string; automatic: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const full = founder.left <= 0;
  function buy() {
    setError(null);
    start(async () => {
      const result = await startPayment("pro_monthly", true, version, founder.amount, code);
      if (result.needsAccount) router.push(`/app/cuenta?${new URLSearchParams({ next: `/app/pro?plan=pro_monthly&fundador=${code}` })}`);
      else if (result.error) setError(result.error);
      else if (result.url) {
        pixel("InitiateCheckout", { content_ids: ["pro_monthly"], value: founder.amount, currency: "ARS" });
        analyticsEvent("begin_checkout", { currency: "ARS", value: founder.amount, items: [{ item_id: "pro_monthly", item_name: "Pro fundador" }] });
        window.location.assign(result.url);
      }
    });
  }
  return (
    <section data-testid="founder-offer" aria-label="Precio fundador" className="space-y-3 rounded-xl bg-amber-50 p-5 ring-2 ring-amber-300 dark:bg-amber-950/30">
      <p className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-800 dark:text-amber-300"><BadgePercent className="size-4" aria-hidden /> Precio fundador para agencias</p>
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-3xl font-semibold tracking-tight">{planPrice(founder.amount)}</span>
        <span className="text-muted-foreground">por mes</span>
        {founder.regular ? <span className="text-sm text-muted-foreground line-through">{planPrice(founder.regular)}</span> : null}
      </p>
      <p className="text-sm">{founderOfferTerms(founder)}</p>
      <p className="text-sm font-medium">{full ? "Ya se ocuparon todos los lugares." : `Quedan ${founder.left} de ${founder.slots} lugares.`}</p>
      {automatic && !full ? <Button onClick={buy} disabled={pending}>{pending ? "Abriendo…" : `Contratar Pro a ${planPrice(founder.amount)}`}</Button> : null}
      {!automatic && !full ? <p className="text-sm text-muted-foreground">Escribinos y coordinamos el alta con este precio.</p> : null}
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      <p className="text-xs text-muted-foreground">Renovación mensual automática. Podés cancelar desde Ajustes. Al contratar aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>.</p>
    </section>
  );
}
