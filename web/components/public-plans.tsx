import Link from "next/link";
import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WebConfig } from "@/lib/config";
import { alertsText, CUSTOM_PLAN, inWords, OFFER_TIER, PLAN_COPY, planFeatures, planPrice, resultsText, searchesText, WAITLIST_PLANS } from "@/lib/pro";

type PricingConfig = Pick<WebConfig, "proOffer" | "planLimits" | "automaticPayments" | "commercialPilot">;
type PublicPlan = {
  id: string;
  name: string;
  price: string;
  period: string;
  pitch: string;
  features: string[];
  terms: string;
  cta: string;
  href: string;
};

/**
 * Shared by the landing and the public Planes page. Prices follow the current
 * offer and every limit comes from app_config.plan_limits, as the backend applies it.
 */
export function PublicPlans({ cfg, signedIn }: { cfg: PricingConfig; signedIn: boolean }) {
  // The trial needs only an email: signed out, it starts at the landing's form.
  const start = signedIn ? "/app/searches/new" : "/#crear-busqueda";
  const trial = cfg.planLimits.free;
  const plans: PublicPlan[] = [
    {
      id: "trial",
      name: "Prueba gratis",
      price: "Gratis",
      period: "por 3 días · sin tarjeta",
      pitch: "Probá cómo buscamos y comparamos autos antes de elegir un plan.",
      features: [searchesText(trial, false), resultsText(trial), alertsText(trial), "Historial y favoritos"],
      terms: "Las 72 horas empiezan al activar tu búsqueda. Sin contraseña: solo tu email. Una prueba por email, sin cobro automático.",
      cta: "Probar gratis",
      href: start,
    },
    ...WAITLIST_PLANS.map((plan) => {
      const copy = PLAN_COPY[plan];
      const caps = cfg.planLimits[OFFER_TIER[plan]];
      const destination = `/app/pro?plan=${plan}`;
      return {
        id: plan,
        name: copy.name,
        price: planPrice(cfg.proOffer[plan].amount),
        period: plan === "pass_30" ? `${copy.period} · pago único` : copy.period,
        pitch: plan === "pass_30"
          ? `Seguí hasta ${inWords(caps.maxProfiles)} opciones a la vez y recibí avisos para encontrar tu próximo auto.`
          : copy.pitch,
        features: planFeatures(caps),
        terms: plan === "pass_30" ? "Sin renovación automática. Si todavía no lo encontraste, extendés 30 días con un clic."
          : cfg.automaticPayments ? "Renovación mensual automática. Cancelás desde Ajustes y conservás el período pagado."
            : "Durante el piloto: períodos de 30 días y renovación manual, sin débito automático.",
        cta: cfg.automaticPayments ? `Contratar ${copy.name}`
          : cfg.commercialPilot ? `Solicitar ${copy.name}` : `Lista de espera: ${copy.name}`,
        href: signedIn ? destination : `/login?next=${encodeURIComponent(destination)}`,
      };
    }),
    CUSTOM_PLAN,
  ];

  return (
    <>
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {plans.map((plan) => (
          <article key={plan.id} className={`row-span-7 grid grid-rows-subgrid gap-y-0 rounded-lg border p-5 ${plan.id === "trial" ? "bg-muted/40" : ""}`}>
            <h3 className="text-xl font-bold">{plan.name}</h3>
            <p data-plan-price className="mt-5 text-3xl font-bold">{plan.price}</p>
            <p className="mt-1 text-sm text-muted-foreground">{plan.period}</p>
            <p className="mt-4 text-muted-foreground">{plan.pitch}</p>
            <Features items={plan.features} />
            <p className="mt-5 text-sm text-muted-foreground">{plan.terms}</p>
            <div className="pt-6">
              <Button asChild className="h-auto min-h-10 w-full whitespace-normal py-2 text-center">
                {plan.id === "custom" ? <a href={plan.href} target="_blank" rel="noopener noreferrer">{plan.cta}</a> : <Link href={plan.href}>{plan.cta}</Link>}
              </Button>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-8 max-w-3xl space-y-2 border-t pt-6 text-sm text-muted-foreground">
        <p className="text-base text-foreground">Una búsqueda es un modelo, con sus versiones, años, kilómetros, presupuesto y zona. Si querés seguir varios modelos, cada uno cuenta como una búsqueda.</p>
        <p>Todos los planes incluyen comparación con autos similares, explicación del precio y señales para revisar antes de contactar al vendedor. Los avisos que pasan el tope del día van al resumen. Las bajas de precio de tus favoritos se avisan de inmediato mientras el acceso siga vigente. La frecuencia de revisión depende de cada portal.</p>
        <p>Los precios pueden actualizarse. Si tu plan se renueva solo, te avisamos por mail 30 días antes.</p>
        <p>{cfg.automaticPayments
          ? "Pagás en Mercado Pago. Activamos el acceso cuando se aprueba el pago."
          : cfg.commercialPilot
            ? "Las altas y la confirmación de pagos se coordinan con la administración."
            : "Las altas pagas están en lista de espera."}</p>
      </div>
    </>
  );
}

function Features({ items }: { items: string[] }) {
  return (
    <ul className="mt-5 space-y-3 border-t pt-5 text-sm">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2.5">
          <Check aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}
