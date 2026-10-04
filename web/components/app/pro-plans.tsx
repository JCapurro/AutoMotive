"use client";
import { CheckCircle2 } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { joinWaitlist } from "@/app/app/pro/actions";
import { startPayment } from "@/app/app/pro/billing-actions";
import { Button } from "@/components/ui/button";
import { pixel } from "@/lib/meta-pixel";
import { PLAN_COPY, planPrice, type Placement, type ProOffer, WAITLIST_PLANS, type WaitlistPlan } from "@/lib/pro";
import { cn } from "@/lib/utils";
export function ProPlans({ offer, current, placement, pilot = false, recommended, automatic = false, email = "" }: {
  offer: ProOffer; current: WaitlistPlan | null; placement: Placement | null; pilot?: boolean; recommended?: WaitlistPlan; automatic?: boolean; email?: string;
}) {
  const [plan, setPlan] = useState<WaitlistPlan>(recommended ?? current ?? "pass_30");
  const [joined, setJoined] = useState<WaitlistPlan | null>(current);
  const [pending, start] = useTransition();
  const [billingEmail, setBillingEmail] = useState(email);
  const [accepted, setAccepted] = useState(false);
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault();
      start(async () => {
        if (automatic) {
          const result = await startPayment(plan, billingEmail.trim(), accepted, offer.version, offer[plan].amount);
          if (result.error) toast.error(result.error);
          else if (result.url) {
            pixel("InitiateCheckout", { content_ids: [plan], value: offer[plan].amount, currency: offer[plan].currency });
            window.location.assign(result.url);
          }
          return;
        }
        const res = await joinWaitlist(plan, placement);
        if (res.error) { toast.error(res.error); return; }
        setJoined(plan);
      });
    }}>
      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="sr-only">Elegí un plan</legend>
        {WAITLIST_PLANS.map((p) => {
          const copy = PLAN_COPY[p];
          return (
            <label key={p} className={cn("flex cursor-pointer flex-col gap-2 rounded-xl bg-card p-5 ring-1 ring-foreground/10 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50", plan === p && "ring-2 ring-primary")}>
              <span className="flex items-center justify-between gap-2">
                <span className="font-medium">{copy.name}</span>
                <input type="radio" name="plan" value={p} checked={plan === p} onChange={() => { setPlan(p); setAccepted(false); }} className="size-4 accent-primary" />
              </span>
              <span className="text-2xl font-semibold tracking-tight">{planPrice(offer[p].amount)}
                <span className="ml-1 text-sm font-normal text-muted-foreground">{copy.period}</span>
              </span>
              <span className="text-sm text-muted-foreground">Pesos argentinos · {copy.pitch}</span>
              <span className="text-sm font-medium">Hasta {copy.searches} búsquedas activas · una cuenta</span>
              <span className="text-sm text-muted-foreground">
                {p === "pro_monthly" ? automatic ? "Renovación mensual automática. Podés cancelar desde Ajustes." : "En este piloto: períodos de 30 días y renovación manual, sin débito automático." : "Sin renovación automática."}
              </span>
              {joined === p ? <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700"><CheckCircle2 className="size-3.5" aria-hidden /> {pilot ? "Solicitud registrada" : "Estás en la lista"}</span> : null}
            </label>
          );
        })}
      </fieldset>
      {joined && !automatic ? <p role="status" data-testid="waitlist-joined" className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200">
        {pilot ? <>Registramos tu solicitud de <strong>{PLAN_COPY[joined].name}</strong>. La administración coordina el pago y activa el período después de verificarlo. Esta solicitud no genera un cobro.</>
          : <>Estás en la lista de espera de <strong>{PLAN_COPY[joined].name}</strong>. Te avisamos cuando abramos las altas; no se genera ningún cobro.</>}
      </p> : null}
      {automatic ? <div className="space-y-3 text-sm">
        <label className="block space-y-1">Email de tu cuenta de Mercado Pago
          <input type="email" required maxLength={254} value={billingEmail} onChange={(e) => setBillingEmail(e.target.value)} className="block h-10 w-full rounded-md border px-3" autoComplete="email" />
        </label>
        <label className="flex items-start gap-2"><input type="checkbox" required checked={accepted} onChange={(e) => setAccepted(e.target.checked)} className="mt-1" />
          <span>Acepto los <a href="/terminos" target="_blank" rel="noreferrer" className="underline">términos</a> y {plan === "pro_monthly" ? `el cobro de ${planPrice(offer[plan].amount)} ARS cada mes hasta cancelar.` : `el pago único de ${planPrice(offer[plan].amount)} ARS por 30 días.`}</span>
        </label>
      </div> : null}
      <Button type="submit" size="lg" className="h-11 w-full px-5 text-base sm:w-auto" disabled={pending || (!automatic && joined === plan)}>
        {automatic ? "Continuar en Mercado Pago" : joined && joined !== plan ? "Cambiar mi solicitud" : pilot ? `Solicitar ${PLAN_COPY[plan].name}` : "Sumarme a la lista de espera"}
      </Button>
    </form>
  );
}
