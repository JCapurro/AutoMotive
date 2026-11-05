"use client";

import { useEffect, useId, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, MessageSquare, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { startPayment } from "@/app/app/pro/billing-actions";
import { joinWaitlist, trackQuotaPopup } from "@/app/app/pro/actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { CUSTOM_PLAN, OFFER_DAYS, PASS_GUARANTEE, PLAN_COPY, PLAN_NAMES, planPrice, proSummary, type PassOffer, type PlanCaps, type ProOffer, type WaitlistPlan } from "@/lib/pro";
import { cn } from "@/lib/utils";
import { ProductFeedback } from "@/components/app/product-feedback";

type CheckoutOptions = { offer: ProOffer; automatic: boolean; pilot: boolean; /** app_config.plan_limits.pro: what Pro adds, as the backend applies it. */ pro: PlanCaps };

/**
 * Two ways to go on, side by side and the same size: Particular (7 or 30 days)
 * to find a car, Pro to resell. Each button starts the existing acquisition
 * flow, without another plan picker; both sit on the boxes' last row, aligned.
 */
export function FreeResultPlans({ offer, automatic, pilot, pro, onSelect }: CheckoutOptions & { onSelect?: (plan: WaitlistPlan) => void }) {
  const router = useRouter();
  const id = useId();
  const [pending, start] = useTransition();
  const [pass, setPass] = useState<PassOffer>("pass_30");
  const [selected, setSelected] = useState<WaitlistPlan | null>(null);
  const [requested, setRequested] = useState<WaitlistPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const verb = automatic ? "Elegir" : pilot ? "Solicitar" : "Anotarme en";

  function choose(plan: WaitlistPlan) {
    setSelected(plan);
    setError(null);
    onSelect?.(plan);
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

  function label(plan: WaitlistPlan, action: string) {
    if (pending && selected === plan) return "Abriendo…";
    if (!automatic && requested === plan) return "Solicitud registrada";
    return action;
  }
  const passAction = `${verb} ${PLAN_NAMES.pass} ${OFFER_DAYS[pass]} días`;
  const proAction = `${verb} ${PLAN_COPY.pro_monthly.name}`;
  const proTerms = automatic ? "Renovación mensual automática" : pilot ? "30 días · renovación manual" : "Por mes";
  const box = "row-span-7 grid grid-rows-subgrid gap-y-2 rounded-lg";
  const kicker = "text-xs font-semibold text-muted-foreground";
  const figure = "type-figure text-[26px] leading-none";

  return <div className="space-y-3">
    <div className="grid gap-3 sm:grid-cols-2">
      <section aria-labelledby={`${id}-pass`} className={cn(box, "border-2 border-foreground p-[15px]")}>
        <p className={kicker}>Para encontrar tu auto</p>
        <h3 id={`${id}-pass`} className="text-base font-bold">{PLAN_NAMES.pass}</h3>
        <div role="group" aria-label="Duración del pase" className="grid grid-cols-2 gap-0.5 rounded-lg bg-muted p-[3px]">
          {(["pass_7", "pass_30"] as const).map((plan) => (
            <button key={plan} type="button" aria-pressed={plan === pass} onClick={() => setPass(plan)}
              className={cn("h-8 rounded-md text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                plan === pass ? "bg-background text-foreground shadow-[0_0_0_1px_var(--border)]" : "text-muted-foreground hover:text-foreground")}>
              {OFFER_DAYS[plan]} días
            </button>
          ))}
        </div>
        <p className={figure}>{planPrice(offer[pass].amount)} <span className="text-xs font-medium text-muted-foreground [font-stretch:100%]">ARS</span></p>
        <p id={`${id}-pass-terms`} className="text-xs text-muted-foreground">Pago único por {OFFER_DAYS[pass]} días</p>
        <p id={`${id}-pass-guarantee`} className="flex items-start gap-2 text-xs font-medium"><ShieldCheck className="size-4 shrink-0" aria-hidden />{PASS_GUARANTEE}</p>
        <Button type="button" className="mt-1 h-auto min-h-10 w-full self-end whitespace-normal py-2 md:min-h-9" aria-describedby={`${id}-pass-terms ${id}-pass-guarantee`}
          disabled={pending || (!automatic && requested === pass)} onClick={() => choose(pass)}>
          {label(pass, passAction)}
        </Button>
      </section>
      <section aria-labelledby={`${id}-pro`} className={cn(box, "border p-4")}>
        <p className={kicker}>Para revender</p>
        <h3 id={`${id}-pro`} className="text-base font-bold">{PLAN_COPY.pro_monthly.name}</h3>
        <p className="self-center text-xs text-muted-foreground">Para agencias y revendedores</p>
        <p className={figure}>{planPrice(offer.pro_monthly.amount)} <span className="text-xs font-medium text-muted-foreground [font-stretch:100%]">ARS</span></p>
        <p id={`${id}-pro-terms`} className="text-xs text-muted-foreground">{proTerms}</p>
        <p className="text-xs">{proSummary(pro)}</p>
        <Button type="button" variant="outline" className="mt-1 h-auto min-h-10 w-full self-end whitespace-normal py-2 md:min-h-9" aria-describedby={`${id}-pro-terms`}
          disabled={pending || (!automatic && requested === "pro_monthly")} onClick={() => choose("pro_monthly")}>
          {label("pro_monthly", proAction)}
        </Button>
      </section>
    </div>
    <a href={CUSTOM_PLAN.href} target="_blank" rel="noopener noreferrer" className="group flex items-center gap-3 rounded-lg border px-4 py-3 text-sm outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring">
      <SlidersHorizontal className="size-5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1"><span className="block font-medium">{CUSTOM_PLAN.cta}</span><span className="text-xs text-muted-foreground">Más búsquedas o una búsqueda a tu medida · a convenir</span></span>
      <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
    </a>
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    {requested && !automatic ? <p role="status" className="text-sm text-muted-foreground">{pilot ? `Registramos tu solicitud de ${PLAN_COPY[requested].name}. Coordinamos el pago y la activación.` : `Estás en la lista de espera de ${PLAN_COPY[requested].name}. Te avisamos cuando abramos las altas.`} La solicitud no genera un cobro.</p> : null}
    {!automatic && !requested ? <p className="text-xs leading-relaxed text-muted-foreground">{pilot ? "Coordinamos el pago y la activación. La solicitud no genera un cobro." : "Estos planes están en lista de espera. Te avisamos cuando abramos las altas; no se genera un cobro."}</p> : null}
    {automatic ? <p className="text-xs leading-relaxed text-muted-foreground">Al elegir Particular o Pro aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>. Pro se renueva cada mes; podés cancelar desde Ajustes.</p> : null}
  </div>;
}

/**
 * Rendered only after the account has received its entire free quota.
 * `opportunities`: this search's active «Alta oportunidad» results, the only
 * figure marked in yellow; 0 leaves the line out.
 */
export function FreeResultLimit({ limit, profileId, opportunities = 0, ...checkout }: { limit: number; profileId: number; opportunities?: number } & CheckoutOptions) {
  const [open, setOpen] = useState(true);
  const [feedback, setFeedback] = useState(false);
  const chosen = useRef(false);
  const viewed = useRef(false);
  const content = useRef<HTMLDivElement>(null);
  // Opened (also when it is reopened with «Elegir un plan»): once per tab session and search.
  useEffect(() => {
    if (!open || viewed.current) return;
    viewed.current = true;
    const key = `quota_popup_viewed:${profileId}`;
    try {
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, "1");
    } catch {
      // No storage (private mode): count it every time rather than never.
    }
    void trackQuotaPopup("viewed", profileId);
  }, [open, profileId]);
  function changeOpen(next: boolean) {
    // Closing without having picked a plan is the signal; picking one navigates away.
    if (!next && !chosen.current) void trackQuotaPopup("dismissed", profileId);
    setOpen(next);
  }
  function selectPlan(plan: WaitlistPlan) {
    chosen.current = true;
    void trackQuotaPopup("plan_selected", profileId, plan);
  }
  return <>
    <aside aria-label="Límite de la prueba gratis" className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card px-5 py-4 text-sm">
      <div className="space-y-1">
        <p className="font-medium">Completaste tu prueba de {limit} resultados</p>
        <p className="text-muted-foreground">Tus resultados siguen disponibles. Elegí un plan para recibir más.</p>
      </div>
      <Button onClick={() => setOpen(true)}>Elegir un plan <ArrowRight aria-hidden /></Button>
    </aside>
    <Dialog open={open} onOpenChange={changeOpen}>
      {/* Centered from sm up; on a phone, a sheet from the bottom whose footer stays in view. */}
      {/* Focus the dialog itself, not the first button: «7 días» would look chosen. */}
      <DialogContent data-testid="free-result-limit" ref={content} onOpenAutoFocus={(event) => { event.preventDefault(); content.current?.focus(); }}
        className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-[640px] max-sm:top-auto max-sm:bottom-0 max-sm:left-0 max-sm:max-h-[92dvh] max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-b-none">
        <div aria-hidden className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-border sm:hidden" />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <DialogHeader className="gap-3 px-5 pt-5 pb-5 sm:gap-4 sm:px-8 sm:pt-8 sm:pb-6">
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
              {feedback ? <><MessageSquare className="size-3.5" aria-hidden /> Tu experiencia</> : <><Check className="size-3.5" aria-hidden /> Prueba gratis completada</>}
            </span>
            <DialogTitle className="max-w-[22ch] pr-6 text-[26px] leading-[1.15] font-semibold tracking-tight sm:text-[32px]">{feedback ? "¿Qué podemos mejorar?" : `Tu prueba encontró ${limit} autos.`}</DialogTitle>
            <DialogDescription className="max-w-md leading-relaxed">{feedback ? "Contanos qué te faltó, qué no funcionó o qué te gustaría encontrar en Ese Auto." : <>
              {opportunities > 0 ? <>En esta búsqueda, <b className="mark font-semibold">{opportunities}</b> {opportunities === 1 ? "está" : "están"} por debajo del precio de autos comparables. </> : null}
              Elegí cómo seguir recibiendo los autos nuevos.</>}</DialogDescription>
          </DialogHeader>
          <div className="px-5 pb-4 sm:px-8">{feedback ? <ProductFeedback profileId={profileId} onBack={() => setFeedback(false)} /> : <FreeResultPlans {...checkout} onSelect={selectPlan} />}</div>
        </div>
        {!feedback ? <div className="flex shrink-0 flex-col border-t px-5 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:border-t-0 sm:px-8 sm:pt-0 sm:pb-5">
          <DialogClose asChild><Button variant="ghost" className="h-10 w-full text-muted-foreground md:h-10">Seguir viendo mis resultados</Button></DialogClose>
          <Button variant="link" className="h-9 gap-2 text-xs text-muted-foreground md:h-9" onClick={() => setFeedback(true)}><MessageSquare className="size-3.5" aria-hidden /> Enviar feedback</Button>
        </div> : null}
      </DialogContent>
    </Dialog>
  </>;
}
