"use client";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { startPayment } from "@/app/app/pro/billing-actions";
import { Button } from "@/components/ui/button";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { OFFER_DAYS, PASS_GUARANTEE, PLAN_COPY, planPrice, type PassOffer, type ProOffer } from "@/lib/pro";

/** missed_since_expiry(): what the paused searches found after access ended (expired_search_matches). */
export type MissedSinceExpiry = { ended_at: string; found: number; below: number };

const autos = (n: number) => `${n} ${n === 1 ? "auto nuevo" : "autos nuevos"}`;

/**
 * The expiry screen (Juan, 05/11/2026): what the account is missing since its
 * access ended, and the passes one click from Mercado Pago.
 */
export function ExpiredMissed({ missed, offer, automatic }: { missed: MissedSinceExpiry; offer: ProOffer; automatic: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [selected, setSelected] = useState<PassOffer | null>(null);
  const [error, setError] = useState<string | null>(null);

  function choose(plan: PassOffer) {
    if (!automatic) { router.push(`/app/pro?plan=${plan}&from=dashboard`); return; }
    setSelected(plan);
    setError(null);
    start(async () => {
      try {
        const result = await startPayment(plan, true, offer.version, offer[plan].amount);
        if (result.needsAccount) router.push(`/app/cuenta?${new URLSearchParams({ next: `/app/pro?plan=${plan}` })}`);
        else if (result.error) setError(result.error);
        else if (result.url) {
          pixel("InitiateCheckout", { content_ids: [plan], value: offer[plan].amount, currency: offer[plan].currency });
          analyticsEvent("begin_checkout", { currency: offer[plan].currency, value: offer[plan].amount, items: [{ item_id: plan, item_name: PLAN_COPY[plan].name }] });
          window.location.assign(result.url);
        }
      } catch {
        setError("No pudimos continuar. Probá de nuevo en unos segundos.");
      }
    });
  }

  return <section aria-labelledby="expired-missed" data-testid="expired-missed" className="space-y-4 rounded-xl border-2 border-foreground p-5">
    <div className="space-y-1">
      <h2 id="expired-missed" className="type-heading text-[22px] leading-tight">
        Desde que venció tu acceso aparecieron {autos(missed.found)} de tus búsquedas
      </h2>
      <p className="text-muted-foreground">
        {missed.below > 0 ? <><b className="mark text-foreground">{missed.below}</b> {missed.below === 1 ? "está" : "están"} por debajo del precio de autos comparables. </> : null}
        Tus búsquedas están pausadas: volvé para verlos y recibir los avisos de los que vengan.
      </p>
    </div>
    <div className="flex flex-wrap gap-2">
      {(["pass_7", "pass_30"] as const).map((plan, i) => (
        <Button key={plan} variant={i === 0 ? "default" : "outline"} className="h-11 px-4.5 text-[15px]" disabled={pending}
          onClick={() => choose(plan)}>
          {pending && selected === plan ? "Abriendo…" : `Volver ${OFFER_DAYS[plan]} días · ${planPrice(offer[plan].amount)}`}
          <ArrowRight aria-hidden />
        </Button>
      ))}
    </div>
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    <p className="text-xs leading-relaxed text-muted-foreground">
      Pago único, sin renovación automática. {PASS_GUARANTEE}{" "}
      {automatic ? <>Al elegir un pase aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>. </> : null}
      <Link href="/app/pro?from=dashboard" className="underline underline-offset-2">Ver todos los planes</Link>
    </p>
  </section>;
}
