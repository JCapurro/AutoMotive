import { Check } from "lucide-react";
import type { Metadata } from "next";

import { ProPlans } from "@/components/app/pro-plans";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { isPlacement, isWaitlistPlan, PRO_BENEFITS } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Automotive Pro" };

// §52 / sección 9: the plans screen. No charge yet: it measures intent with the waitlist.
export default async function ProPage({ searchParams }: PageProps<"/app/pro">) {
  await requireUser();
  const { from } = await searchParams;
  const supabase = await createClient();
  const [{ data: waitlist }, cfg] = await Promise.all([
    supabase.from("pro_waitlist").select("plan").maybeSingle(),
    webConfig(),
  ]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <p className="text-sm font-medium text-amber-700">Automotive Pro</p>
        <h1 className="text-2xl font-semibold tracking-tight">¿Querés enterarte antes?</h1>
        <p className="text-muted-foreground">
          Todavía no cobramos. Elegí el plan que te sirve y sumate a la lista de espera: te avisamos cuando esté disponible.
          Mientras dure el piloto, tenés todo habilitado.
        </p>
      </header>

      <ul className="grid gap-2 sm:grid-cols-2">
        {PRO_BENEFITS.map((b) => (
          <li key={b} className="flex items-center gap-2 text-sm">
            <Check className="size-4 shrink-0 text-emerald-600" aria-hidden />
            {b}
          </li>
        ))}
      </ul>

      <ProPlans
        offer={cfg.proOffer}
        current={isWaitlistPlan(waitlist?.plan) ? waitlist.plan : null}
        placement={isPlacement(from) ? from : "plans"}
      />
    </div>
  );
}
