"use client";

import { CheckCircle2 } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { joinWaitlist } from "@/app/app/pro/actions";
import { Button } from "@/components/ui/button";
import { PLAN_COPY, type Placement, type ProOffer, WAITLIST_PLANS, type WaitlistPlan } from "@/lib/pro";
import { cn } from "@/lib/utils";

/** Pro mensual vs Search Pass 30/90 días (§33–34) and "Sumarme a la lista de espera". */
export function ProPlans({
  offer,
  current,
  placement,
}: {
  offer: ProOffer;
  current: WaitlistPlan | null;
  placement: Placement | null;
}) {
  const [plan, setPlan] = useState<WaitlistPlan>(current ?? "pass_30");
  const [joined, setJoined] = useState<WaitlistPlan | null>(current);
  const [pending, start] = useTransition();

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const res = await joinWaitlist(plan, placement);
          if (res.error) {
            toast.error(res.error);
            return;
          }
          setJoined(plan);
        });
      }}
    >
      <fieldset className="grid gap-3 sm:grid-cols-3">
        <legend className="sr-only">Elegí un plan</legend>
        {WAITLIST_PLANS.map((p) => {
          const copy = PLAN_COPY[p];
          const checked = plan === p;
          return (
            <label
              key={p}
              className={cn(
                "flex cursor-pointer flex-col gap-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-shadow has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
                checked && "ring-2 ring-primary",
              )}
            >
              <span className="flex items-center justify-between gap-2">
                <span className="font-medium">{copy.name}</span>
                <input type="radio" name="plan" value={p} checked={checked} onChange={() => setPlan(p)} className="size-4 accent-primary" />
              </span>
              <span className="text-2xl font-semibold tracking-tight">
                USD {offer[p].price_usd}
                <span className="ml-1 text-sm font-normal text-muted-foreground">{copy.period}</span>
              </span>
              <span className="text-sm text-muted-foreground">{copy.pitch}</span>
              {joined === p ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                  <CheckCircle2 className="size-3.5" aria-hidden /> Estás en la lista
                </span>
              ) : null}
            </label>
          );
        })}
      </fieldset>

      {joined ? (
        <p role="status" data-testid="waitlist-joined" className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200">
          ¡Listo! Estás en la lista de espera de <strong>{PLAN_COPY[joined].name}</strong>. Te avisamos cuando esté disponible; no
          te vamos a cobrar nada sin preguntarte.
        </p>
      ) : null}

      <Button type="submit" size="lg" className="h-11 w-full px-5 text-base sm:w-auto" disabled={pending || joined === plan}>
        {joined && joined !== plan ? "Cambiar a este plan" : "Sumarme a la lista de espera"}
      </Button>
    </form>
  );
}
