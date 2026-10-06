import { Check } from "lucide-react";
import type { Metadata } from "next";

import { ProPlans } from "@/components/app/pro-plans";
import { BillingStatus } from "@/components/app/billing-status";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { isPlacement, isWaitlistPlan, PRO_BENEFITS } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Planes" };

export default async function ProPage({ searchParams }: PageProps<"/app/pro">) {
  await requireUser();
  const { from, plan } = await searchParams;
  const supabase = await createClient();
  const [{ data: waitlist }, cfg, { data: checkouts }] = await Promise.all([
    supabase.from("pro_waitlist").select("plan").maybeSingle(),
    webConfig(),
    supabase.from("billing_checkouts").select("id,offer,amount,status,init_point,next_payment_at,sync_error,created_at").order("created_at", { ascending: false }).limit(3),
  ]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-2">
        <p className="text-sm font-medium text-amber-700">Planes de Ese Auto</p>
        <h1 className="text-2xl font-semibold tracking-tight">Elegí cuánto querés buscar</h1>
        <p className="text-muted-foreground">
          Particular acompaña la compra de tu próximo auto. Agencia sirve para buscar vehículos habitualmente.
          Custom se adapta a tus necesidades, con alcance y precio a convenir.
          {cfg.automaticPayments ? " Particular y Agencia se pagan en Mercado Pago; activamos tu acceso al confirmar el pago." : cfg.commercialPilot ? " Coordinamos el pago y verificamos cada alta durante este piloto." : " Particular y Agencia todavía están en lista de espera."}
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
        recommended={isWaitlistPlan(plan) || plan === "custom" ? plan : undefined}
        placement={isPlacement(from) ? from : "plans"}
        pilot={cfg.commercialPilot}
        automatic={cfg.automaticPayments}
      />
      {(checkouts ?? []).map((checkout) => <BillingStatus key={checkout.id} checkout={checkout} />)}
      <p className="text-sm text-muted-foreground">Cada modelo guardado cuenta como una búsqueda; pausar libera capacidad.
        Particular y Agencia incluyen hasta 10 avisos inmediatos de nuevas coincidencias por día y cuenta; los restantes van al resumen.
        En Custom, las condiciones se definen en la propuesta.
        Las bajas de precio de favoritos pueden avisarse de inmediato mientras tu acceso siga vigente.
        La detección depende de la disponibilidad de cada fuente.</p>
    </div>
  );
}
