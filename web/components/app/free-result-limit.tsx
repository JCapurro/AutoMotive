"use client";

import { useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, CarFront, Check, MessageSquare, SlidersHorizontal } from "lucide-react";
import { startPayment } from "@/app/app/pro/billing-actions";
import { joinWaitlist } from "@/app/app/pro/actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { CUSTOM_PLAN, PLAN_COPY, planPrice, WAITLIST_PLANS, type ProOffer, type WaitlistPlan } from "@/lib/pro";
import { ProductFeedback } from "@/components/app/product-feedback";

type CheckoutOptions = { offer: ProOffer; automatic: boolean; pilot: boolean };

/** Each choice starts the existing acquisition flow, without another plan picker. */
export function FreeResultPlans({ offer, automatic, pilot }: CheckoutOptions) {
  const router = useRouter();
  const id = useId();
  const [pending, start] = useTransition();
  const [selected, setSelected] = useState<WaitlistPlan | null>(null);
  const [requested, setRequested] = useState<WaitlistPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const verb = automatic ? "Elegir" : pilot ? "Solicitar" : "Anotarme en";

  function choose(plan: WaitlistPlan) {
    setSelected(plan);
    setError(null);
    start(async () => {
      try {
        if (automatic) {
          const result = await startPayment(plan, true, offer.version, offer[plan].amount);
          if (result.needsAccount) router.push(`/app/cuenta?${new URLSearchParams({ next: `/app/pro?plan=${plan}` })}`);
          else if (result.error) setError(result.error);
          else if (result.url) {
            pixel("InitiateCheckout", { content_ids: [plan], value: offer[plan].amount, currency: offer[plan].currency });
            analyticsEvent("begin_checkout", { currency: offer[plan].currency, value: offer[plan].amount, items: [{ item_id: plan, item_name: PLAN_COPY[plan].name }] });
            window.location.assign(result.url);
          }
        } else {
          const result = await joinWaitlist(plan, "results");
          if (result.error) setError(result.error);
          else setRequested(plan);
        }
      } catch {
        setError("No pudimos continuar. Probá de nuevo en unos segundos.");
      }
    });
  }

  return <div className="space-y-3">
    <div className="divide-y rounded-xl border px-4">
      {WAITLIST_PLANS.map((plan) => {
        const Icon = plan === "pass_30" ? CarFront : Building2;
        const terms = plan === "pass_30" ? "Pago único por 30 días" : automatic ? "Renovación mensual automática" : pilot ? "30 días · renovación manual" : "Por mes";
        const action = `${verb} ${PLAN_COPY[plan].name}`;
        return <button key={plan} type="button" aria-label={action} aria-describedby={`${id}-${plan}`} disabled={pending || (!automatic && requested === plan)}
          onClick={() => choose(plan)} className="group flex w-full items-center gap-3 py-4 text-left transition-colors outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60">
          <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
          <span id={`${id}-${plan}`} className="min-w-0 flex-1 space-y-1">
            <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 font-medium"><span>{PLAN_COPY[plan].name}</span><span className="tabular-nums">{planPrice(offer[plan].amount)} <span className="text-xs font-normal text-muted-foreground">ARS</span></span></span>
            <span className="block text-xs leading-relaxed text-muted-foreground">{terms}</span>
            <span className="block pt-1 text-sm font-medium">{pending && selected === plan ? "Abriendo…" : !automatic && requested === plan ? "Solicitud registrada" : action}</span>
          </span>
          <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
        </button>;
      })}
      <a href={CUSTOM_PLAN.href} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 py-4 text-sm outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <SlidersHorizontal className="size-5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1"><span className="block font-medium">Consultar Custom</span><span className="text-xs text-muted-foreground">Un plan a tu medida · a convenir</span></span>
        <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </a>
    </div>
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    {requested && !automatic ? <p role="status" className="text-sm text-muted-foreground">{pilot ? `Registramos tu solicitud de ${PLAN_COPY[requested].name}. Coordinamos el pago y la activación.` : `Estás en la lista de espera de ${PLAN_COPY[requested].name}. Te avisamos cuando abramos las altas.`} La solicitud no genera un cobro.</p> : null}
    {!automatic && !requested ? <p className="text-xs leading-relaxed text-muted-foreground">{pilot ? "Coordinamos el pago y la activación. La solicitud no genera un cobro." : "Estos planes están en lista de espera. Te avisamos cuando abramos las altas; no se genera un cobro."}</p> : null}
    {automatic ? <p className="text-xs leading-relaxed text-muted-foreground">Al elegir Particular o Pro aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>. Pro se renueva cada mes; podés cancelar desde Ajustes.</p> : null}
  </div>;
}

/** Rendered only after the account has received its entire free quota. */
export function FreeResultLimit({ limit, profileId, ...checkout }: { limit: number; profileId: number } & CheckoutOptions) {
  const [open, setOpen] = useState(true);
  const [feedback, setFeedback] = useState(false);
  return <>
    <aside aria-label="Límite de la prueba gratis" className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card px-5 py-4 text-sm">
      <div className="space-y-1">
        <p className="font-medium">Completaste tu prueba de {limit} resultados</p>
        <p className="text-muted-foreground">Tus resultados siguen disponibles. Elegí un plan para recibir más.</p>
      </div>
      <Button onClick={() => setOpen(true)}>Elegir un plan <ArrowRight aria-hidden /></Button>
    </aside>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] gap-0 overflow-y-auto rounded-2xl p-0 sm:max-w-[500px]" data-testid="free-result-limit">
        <DialogHeader className="gap-4 px-6 pt-7 pb-6 sm:px-8 sm:pt-8">
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            {feedback ? <><MessageSquare className="size-3.5" aria-hidden /> Tu experiencia</> : <><Check className="size-3.5" aria-hidden /> Prueba gratis completada</>}
          </span>
          <DialogTitle className="max-w-[340px] pr-4 text-[28px] leading-[1.15] font-semibold tracking-tight sm:text-[32px]">{feedback ? "¿Qué podemos mejorar?" : <>Seguí buscando <span className="block">ese auto.</span></>}</DialogTitle>
          <DialogDescription className="max-w-sm leading-relaxed">{feedback ? "Contanos qué te faltó, qué no funcionó o qué te gustaría encontrar en Ese Auto." : <>Ya recibiste los {limit} resultados de tu prueba gratis. Elegí un plan para recibir nuevas coincidencias.</>}</DialogDescription>
        </DialogHeader>
        <div className="px-6 sm:px-8">{feedback ? <ProductFeedback profileId={profileId} onBack={() => setFeedback(false)} /> : <FreeResultPlans {...checkout} />}</div>
        {!feedback ? <div className="flex flex-col px-6 pt-3 pb-5 sm:px-8 sm:pb-6">
          <DialogClose asChild><Button variant="ghost" className="h-10 w-full text-muted-foreground md:h-10">Seguir viendo mis resultados</Button></DialogClose>
          <Button variant="link" className="h-9 gap-2 text-xs text-muted-foreground md:h-9" onClick={() => setFeedback(true)}><MessageSquare className="size-3.5" aria-hidden /> Enviar feedback</Button>
        </div> : null}
      </DialogContent>
    </Dialog>
  </>;
}
