"use client";

import { useState, useTransition } from "react";

import { setDealerAlerts } from "@/app/agencia/actions";

/**
 * Fase 1: the agency's alert emails (market moved, a cheaper one nearby, a car
 * taking long, new searches). On by default for the agency; the program's
 * switch (dealer_program.alerts_enabled) decides whether any go at all.
 */
export function DealerAlertsToggle({ initial, every }: { initial: boolean; every: number }) {
  const [on, setOn] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [pending, run] = useTransition();
  return (
    <div className="space-y-1.5">
      <label className="flex items-start gap-2.5 text-[15px]">
        <input
          type="checkbox"
          className="mt-1 size-4 shrink-0 accent-foreground"
          checked={on}
          disabled={pending}
          data-testid="dealer-alerts"
          onChange={(e) => {
            const next = e.target.checked;
            setOn(next);
            setError(null);
            run(async () => {
              const result = await setDealerAlerts(next).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }));
              if (result.error) {
                setOn(!next);
                setError(result.error);
              }
            });
          }}
        />
        <span>
          <b className="font-semibold">Avisarme por email</b> cuando se mueve el mercado de uno de mis autos, aparece uno parecido más barato cerca,
          un auto tarda más de lo normal o entran búsquedas nuevas que lo aceptan.
          <span className="block text-sm text-muted-foreground">
            Un solo resumen, como mucho cada {every === 24 ? "día" : `${every} horas`}. Nunca te decimos quién busca.
          </span>
        </span>
      </label>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
