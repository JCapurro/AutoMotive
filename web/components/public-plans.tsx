import Link from "next/link";
import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WebConfig } from "@/lib/config";
import { PLAN_COPY, planPrice, WAITLIST_PLANS } from "@/lib/pro";

type PricingConfig = Pick<WebConfig, "proOffer" | "automaticPayments" | "commercialPilot">;
type PublicPlan = {
  id: string;
  label: string;
  name: string;
  price: string;
  period: string;
  pitch: string;
  features: string[];
  terms: string;
  cta: string;
  href: string;
};

/** Shared by the landing and public Pricing page; prices follow the current offer. */
export function PublicPlans({ cfg, signedIn }: { cfg: PricingConfig; signedIn: boolean }) {
  const start = signedIn ? "/app/searches/new" : "/login?next=/app/searches/new";
  const plans: PublicPlan[] = [
    {
      id: "trial",
      label: "Para conocer Ese Auto",
      name: "Prueba gratis",
      price: "Gratis",
      period: "por 3 días · sin tarjeta",
      pitch: "Probá cómo buscamos y comparamos autos antes de elegir un plan.",
      features: ["1 búsqueda activa", "Hasta 50 resultados por búsqueda", "Resumen diario de coincidencias", "Historial y favoritos"],
      terms: "Las 72 horas empiezan al activar tu primera búsqueda. Una prueba por cuenta, sin cobro automático.",
      cta: "Probar gratis",
      href: start,
    },
    ...WAITLIST_PLANS.map((plan) => {
      const copy = PLAN_COPY[plan];
      const destination = `/app/pro?plan=${plan}`;
      return {
        id: plan,
        label: plan === "pass_30" ? "Para comprar tu próximo auto" : "Para buscar vehículos habitualmente",
        name: copy.name,
        price: planPrice(cfg.proOffer[plan].amount),
        period: `${copy.period} · pesos argentinos`,
        pitch: plan === "pass_30"
          ? "Seguí hasta tres opciones a la vez y recibí avisos para encontrar tu próximo auto."
          : "Monitoreá más modelos y oportunidades de compra desde una misma cuenta.",
        features: [
          `Hasta ${copy.searches} búsquedas activas`,
          "Todos los resultados disponibles",
          "Avisos al detectar coincidencias",
          "Historial y favoritos",
        ],
        terms: plan === "pass_30" ? "Pago único. Sin renovación automática."
          : cfg.automaticPayments ? "Renovación mensual automática. Cancelás desde Ajustes y conservás el período pagado."
            : "Durante el piloto: períodos de 30 días y renovación manual, sin débito automático.",
        cta: cfg.automaticPayments ? `Contratar ${copy.name}`
          : cfg.commercialPilot ? `Solicitar ${copy.name}` : `Lista de espera: ${copy.name}`,
        href: signedIn ? destination : `/login?next=${encodeURIComponent(destination)}`,
      };
    }),
    {
      id: "custom",
      label: "Para necesidades específicas",
      name: "Custom",
      price: "A convenir",
      period: "según alcance y duración",
      pitch: "Si necesitás más capacidad o una búsqueda particular, armamos una propuesta con vos.",
      features: [
        "Cantidad de búsquedas a acordar",
        "Modelos, zonas y filtros definidos juntos",
        "Modalidad de alertas a acordar",
        "Acompañamiento en la configuración",
      ],
      terms: "Acordamos el alcance, el precio y las condiciones antes de activar el servicio.",
      cta: "Consultar Custom",
      href: `mailto:contacto@eseauto.com.ar?subject=${encodeURIComponent("Consulta por plan Custom")}&body=${encodeURIComponent("Hola, me interesa un plan Custom de Ese Auto.\n\nNecesito buscar:\nCantidad de búsquedas:\nModelos y zonas:\nDuración estimada:\n")}`,
    },
  ];

  return (
    <>
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {plans.map((plan) => (
          <article key={plan.id} className={`row-span-8 grid grid-rows-subgrid gap-y-0 rounded-lg border p-5 ${plan.id === "trial" ? "bg-muted/40" : ""}`}>
            <p className="text-sm text-muted-foreground">{plan.label}</p>
            <h3 className="mt-2 text-xl font-bold">{plan.name}</h3>
            <p data-plan-price className="mt-5 text-3xl font-bold">{plan.price}</p>
            <p className="mt-1 text-sm text-muted-foreground">{plan.period}</p>
            <p className="mt-4 text-muted-foreground">{plan.pitch}</p>
            <Features items={plan.features} />
            <p className="mt-5 text-sm text-muted-foreground">{plan.terms}</p>
            <div className="pt-6">
              <Button asChild variant={plan.id === "pass_30" ? "default" : "outline"} className="h-auto min-h-10 w-full whitespace-normal py-2 text-center">
                {plan.id === "custom" ? <a href={plan.href}>{plan.cta}</a> : <Link href={plan.href}>{plan.cta}</Link>}
              </Button>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-8 border-t pt-6">
        <h3 className="text-lg font-bold">En todos los planes</h3>
        <p className="mt-2 max-w-3xl text-muted-foreground">Comparación con autos similares, explicación del precio y señales para revisar antes de contactar al vendedor. Prueba gratis, Particular y Agencia son para una cuenta individual; en Custom definimos el alcance de la propuesta.</p>
        <p className="mt-4 text-sm text-muted-foreground">{cfg.automaticPayments
          ? "Pagás en Mercado Pago. Activamos el acceso cuando se aprueba el pago."
          : cfg.commercialPilot
            ? "Las altas y la confirmación de pagos se coordinan con la administración."
            : "Las altas pagas están en lista de espera."}</p>
        <p className="mt-2 text-sm text-muted-foreground">Particular y Agencia incluyen hasta 10 avisos inmediatos de nuevas coincidencias por día; los restantes van al resumen. En Custom, las condiciones de alertas se definen en la propuesta. Las bajas de precio de favoritos se avisan de inmediato mientras el acceso siga vigente. La frecuencia de revisión depende de cada portal.</p>
        <p className="mt-2 text-sm text-muted-foreground">Al vencer el acceso se detienen nuevas coincidencias y alertas; conservamos historial y favoritos. Pausar o reemplazar una búsqueda no reinicia la prueba gratis.</p>
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
