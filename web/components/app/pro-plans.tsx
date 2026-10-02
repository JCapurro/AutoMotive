"use client";
import { CheckCircle2 } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { joinWaitlist } from "@/app/app/pro/actions";
import { Button } from "@/components/ui/button";
import { PLAN_COPY, planPrice, type Placement, type ProOffer, WAITLIST_PLANS, type WaitlistPlan } from "@/lib/pro";
import { cn } from "@/lib/utils";
export function ProPlans({ offer, current, placement, pilot = false, recommended }: {
  offer: ProOffer; current: WaitlistPlan | null; placement: Placement | null; pilot?: boolean; recommended?: WaitlistPlan;
}) {
  const [plan, setPlan] = useState<WaitlistPlan>(recommended ?? current ?? "pass_30");
  const [joined, setJoined] = useState<WaitlistPlan | null>(current);
  const [pending, start] = useTransition();
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault();
      start(async () => {
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
                <input type="radio" name="plan" value={p} checked={plan === p} onChange={() => setPlan(p)} className="size-4 accent-primary" />
              </span>
              <span className="text-2xl font-semibold tracking-tight">{planPrice(offer[p].amount)}
                <span className="ml-1 text-sm font-normal text-muted-foreground">{copy.period}</span>
              </span>
              <span className="text-sm text-muted-foreground">Pesos argentinos · {copy.pitch}</span>
              <span className="text-sm font-medium">Hasta {copy.searches} búsquedas activas · una cuenta</span>
              <span className="text-sm text-muted-foreground">
                {p === "pro_monthly" ? "En este piloto: períodos de 30 días y renovación manual, sin débito automático." : "Sin renovación automática."}
              </span>
              {joined === p ? <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700"><CheckCircle2 className="size-3.5" aria-hidden /> {pilot ? "Solicitud registrada" : "Estás en la lista"}</span> : null}
            </label>
          );
        })}
      </fieldset>
      {joined ? <p role="status" data-testid="waitlist-joined" className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200">
        {pilot ? <>Registramos tu solicitud de <strong>{PLAN_COPY[joined].name}</strong>. La administración coordina el pago y activa el período después de verificarlo. Esta solicitud no genera un cobro.</>
          : <>Estás en la lista de espera de <strong>{PLAN_COPY[joined].name}</strong>. Te avisamos cuando abramos las altas; no se genera ningún cobro.</>}
      </p> : null}
      <Button type="submit" size="lg" className="h-11 w-full px-5 text-base sm:w-auto" disabled={pending || joined === plan}>
        {joined && joined !== plan ? "Cambiar mi solicitud" : pilot ? `Solicitar ${PLAN_COPY[plan].name}` : "Sumarme a la lista de espera"}
      </Button>
    </form>
  );
}
