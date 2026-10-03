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
  const user = await requireUser();
  const { from, plan } = await searchParams;
  const supabase = await createClient();
  const [{ data: waitlist }, cfg, { data: checkouts }] = await Promise.all([
    supabase.from("pro_waitlist").select("plan").maybeSingle(),
    webConfig(),
    supabase.from("billing_checkouts").select("id,offer,amount,status,init_point,next_payment_at,sync_error").order("created_at", { ascending: false }).limit(3),
  ]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <p className="text-sm font-medium text-amber-700">Planes de Ese Auto</p>
        <h1 className="text-2xl font-semibold tracking-tight">Elegí cuánto querés buscar</h1>
        <p className="text-muted-foreground">
          Particular acompaña la compra de tu próximo auto. Agencia sirve para buscar vehículos habitualmente.
          {cfg.automaticPayments ? " Pagás en Mercado Pago y activamos tu acceso al confirmar el pago." : cfg.commercialPilot ? " Coordinamos el pago y verificamos cada alta durante este piloto." : " Las altas pagas todavía están en lista de espera."}
        </p>
      </header>

      <section className="rounded-xl border bg-card p-5 text-sm">
        <h2 className="font-semibold">Prueba gratis por 3 días</h2>
        <p className="mt-1 text-muted-foreground">Una búsqueda activa, hasta 50 resultados y resumen diario.
          Las 72 horas empiezan al activar la primera búsqueda; pausar, editar o reemplazarla no reinicia el plazo.
          Sin tarjeta ni cobro automático. Al vencer, conservamos historial y favoritos.</p>
      </section>

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
        recommended={isWaitlistPlan(plan) ? plan : undefined}
        placement={isPlacement(from) ? from : "plans"}
        pilot={cfg.commercialPilot}
        automatic={cfg.automaticPayments}
        email={user.email ?? ""}
      />
      {(checkouts ?? []).map((checkout) => <BillingStatus key={checkout.id} checkout={checkout} />)}
      <p className="text-sm text-muted-foreground">Cada modelo guardado cuenta como una búsqueda; pausar libera capacidad.
        Hasta 10 avisos inmediatos de nuevas coincidencias por día y cuenta; los restantes van al resumen.
        Las bajas de precio de favoritos pueden avisarse de inmediato mientras tu acceso siga vigente.
        La detección depende de la disponibilidad de cada fuente.</p>
    </div>
  );
}
