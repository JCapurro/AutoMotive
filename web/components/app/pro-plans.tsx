"use client";
import { CheckCircle2 } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { joinWaitlist } from "@/app/app/pro/actions";
import { startPayment } from "@/app/app/pro/billing-actions";
import { Button } from "@/components/ui/button";
import { pixel } from "@/lib/meta-pixel";
import { analyticsEvent } from "@/lib/google-analytics";
import { CUSTOM_PLAN, PLAN_COPY, planPrice, type Placement, type PlanChoice, type ProOffer, WAITLIST_PLANS, type WaitlistPlan } from "@/lib/pro";
import { cn } from "@/lib/utils";
export function ProPlans({ offer, current, placement, pilot = false, recommended, automatic = false }: {
  offer: ProOffer; current: WaitlistPlan | null; placement: Placement | null; pilot?: boolean; recommended?: PlanChoice; automatic?: boolean;
}) {
  const [plan, setPlan] = useState<PlanChoice>(recommended ?? current ?? "pass_30");
  const [joined, setJoined] = useState<WaitlistPlan | null>(current);
  const [pending, start] = useTransition();
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault();
      if (plan === "custom") return;
      start(async () => {
        if (automatic) {
          const result = await startPayment(plan, true, offer.version, offer[plan].amount);
          if (result.error) toast.error(result.error);
          else if (result.url) {
            pixel("InitiateCheckout", { content_ids: [plan], value: offer[plan].amount, currency: offer[plan].currency });
            analyticsEvent("begin_checkout", { currency: offer[plan].currency, value: offer[plan].amount, items: [{ item_id: plan, item_name: PLAN_COPY[plan].name }] });
            window.location.assign(result.url);
          }
          return;
        }
        const res = await joinWaitlist(plan, placement);
        if (res.error) { toast.error(res.error); return; }
        setJoined(plan);
      });
    }}>
      <fieldset className="grid gap-3 md:grid-cols-3">
        <legend className="sr-only">Elegí un plan</legend>
        {WAITLIST_PLANS.map((p) => {
          const copy = PLAN_COPY[p];
          return (
            <label key={p} className={cn("row-span-7 grid cursor-pointer grid-rows-subgrid gap-2 rounded-xl bg-card p-5 ring-1 ring-foreground/10 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50", plan === p && "ring-2 ring-primary")}>
              <span className="flex items-center justify-between gap-2">
                <span data-plan-name className="font-medium">{copy.name}</span>
                <input type="radio" name="plan" value={p} checked={plan === p} onChange={() => setPlan(p)} className="size-4 accent-primary" />
              </span>
              <span data-plan-price className="text-2xl font-semibold tracking-tight">{planPrice(offer[p].amount)}</span>
              <span className="text-sm text-muted-foreground">{copy.period} · pesos argentinos</span>
              <span className="text-sm text-muted-foreground">{copy.pitch}</span>
              <span className="text-sm font-medium">Hasta {copy.searches} búsquedas activas · una cuenta</span>
              <span className="text-sm text-muted-foreground">
                {p === "pro_monthly" ? automatic ? "Renovación mensual automática. Podés cancelar desde Ajustes." : "En este piloto: períodos de 30 días y renovación manual, sin débito automático." : "Sin renovación automática."}
              </span>
              <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                {joined === p ? <><CheckCircle2 className="size-3.5" aria-hidden /> {pilot ? "Solicitud registrada" : "Estás en la lista"}</> : null}
              </span>
            </label>
          );
        })}
        <label className={cn("row-span-7 grid cursor-pointer grid-rows-subgrid gap-2 rounded-xl bg-card p-5 ring-1 ring-foreground/10 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50", plan === "custom" && "ring-2 ring-primary")}>
          <span className="flex items-center justify-between gap-2">
            <span data-plan-name className="font-medium">{CUSTOM_PLAN.name}</span>
            <input type="radio" name="plan" value="custom" checked={plan === "custom"} onChange={() => setPlan("custom")} className="size-4 accent-primary" />
          </span>
          <span data-plan-price className="text-2xl font-semibold tracking-tight">{CUSTOM_PLAN.price}</span>
          <span className="text-sm text-muted-foreground">{CUSTOM_PLAN.period}</span>
          <span className="text-sm text-muted-foreground">{CUSTOM_PLAN.pitch}</span>
          <span className="grid gap-1 text-sm font-medium">
            {CUSTOM_PLAN.features.map((feature) => <span key={feature}>{feature}</span>)}
          </span>
          <span className="text-sm text-muted-foreground">{CUSTOM_PLAN.terms}</span>
          <span />
        </label>
      </fieldset>
      {joined && !automatic && plan !== "custom" ? <p role="status" data-testid="waitlist-joined" className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200">
        {pilot ? <>Registramos tu solicitud de <strong>{PLAN_COPY[joined].name}</strong>. La administración coordina el pago y activa el período después de verificarlo. Esta solicitud no genera un cobro.</>
          : <>Estás en la lista de espera de <strong>{PLAN_COPY[joined].name}</strong>. Te avisamos cuando abramos las altas; no se genera ningún cobro.</>}
      </p> : null}
      {plan === "custom" ? <Button asChild size="lg" className="h-11 w-full px-5 text-base sm:w-auto">
        <a href={CUSTOM_PLAN.href}>{CUSTOM_PLAN.cta}</a>
      </Button> : <Button type="submit" size="lg" className="h-11 w-full px-5 text-base sm:w-auto" disabled={pending || (!automatic && joined === plan)}>
        {automatic ? "Continuar en Mercado Pago" : joined && joined !== plan ? "Cambiar mi solicitud" : pilot ? `Solicitar ${PLAN_COPY[plan].name}` : "Sumarme a la lista de espera"}
      </Button>}
      {automatic && plan !== "custom" ? <p className="text-sm text-muted-foreground">
        Al adquirir este plan, usted está de acuerdo con <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-4">términos y condiciones</a>.
      </p> : null}
    </form>
  );
}
