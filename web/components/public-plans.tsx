import Link from "next/link";
import { Check } from "lucide-react";

import { PLAN_CARD, PlanFeatures } from "@/components/plan-card-parts";
import { PassCard, PlanCarousel, type PassVariant } from "@/components/public-plans-client";
import { Button } from "@/components/ui/button";
import type { WebConfig } from "@/lib/config";
import { alertsText, CUSTOM_PLAN, inWords, modelLessText, OFFER_DAYS, OFFER_TIER, PASS_GUARANTEE, PLAN_COPY, PLAN_NAMES, planFeatures, planPrice, resultsText, searchesText } from "@/lib/pro";
import { cn } from "@/lib/utils";

type PricingConfig = Pick<WebConfig, "proOffer" | "planLimits" | "automaticPayments" | "commercialPilot"> & Partial<Pick<WebConfig, "trialReserve">>;
type PublicPlan = {
  id: string;
  name: string;
  price: string;
  /** Paid plans: the price's currency, shown small next to it. */
  currency?: string;
  period: string;
  pitch: string;
  features: string[];
  terms: string;
  cta: string;
  href: string;
};

/**
 * Shared by the landing and the public Planes page: Prueba gratis, Particular
 * (7 or 30 days, one card) and Pro, with Custom below. Prices follow the
 * current offer and every limit comes from app_config.plan_limits, as the
 * backend applies it.
 */
export function PublicPlans({ cfg, signedIn }: { cfg: PricingConfig; signedIn: boolean }) {
  // The trial needs only an email: signed out, it starts at the landing's form.
  const start = signedIn ? "/app/searches/new" : "/#crear-busqueda";
  const destination = (plan: string) => signedIn ? `/app/pro?plan=${plan}` : `/login?next=${encodeURIComponent(`/app/pro?plan=${plan}`)}`;
  const verb = cfg.automaticPayments ? "Contratar" : cfg.commercialPilot ? "Solicitar" : "Lista de espera:";
  const trial = cfg.planLimits.free;
  const passCaps = cfg.planLimits.pass;
  const proCaps = cfg.planLimits[OFFER_TIER.pro_monthly];

  const trialPlan: PublicPlan = {
    id: "trial",
    name: "Prueba gratis",
    price: "Gratis",
    period: "por 3 días · sin tarjeta",
    pitch: "Probá cómo buscamos y comparamos autos antes de elegir un plan.",
    features: [searchesText(trial, false), resultsText(trial, cfg.trialReserve?.enabled ? cfg.trialReserve.backfillMax : null), alertsText(trial), "Historial y favoritos"],
    terms: "Las 72 horas empiezan al activar tu búsqueda. Sin contraseña: solo tu email. Una prueba por email, sin cobro automático. Al terminar te podemos escribir con opciones para seguir; te das de baja con un clic.",
    cta: "Probar gratis",
    href: start,
  };
  const passes: PassVariant[] = (["pass_7", "pass_30"] as const).map((plan) => ({
    plan,
    days: OFFER_DAYS[plan],
    price: planPrice(cfg.proOffer[plan].amount),
    period: `${PLAN_COPY[plan].period} · pago único`,
    pitch: plan === "pass_30"
      ? `Seguí hasta ${inWords(passCaps.maxProfiles)} opciones a la vez y recibí avisos para encontrar tu próximo auto.`
      : "Para probar una semana con todo.",
    terms: plan === "pass_30" ? "Sin renovación automática. Si todavía no lo encontraste, extendés 30 días con un clic."
      : "Sin renovación automática. Si te sirve, seguís con 30 días cuando quieras.",
    cta: `${verb} ${OFFER_DAYS[plan]} días`,
    href: destination(plan),
  }));
  const proPlan: PublicPlan = {
    id: "pro_monthly",
    name: PLAN_COPY.pro_monthly.name,
    price: planPrice(cfg.proOffer.pro_monthly.amount),
    currency: "ARS",
    period: PLAN_COPY.pro_monthly.period,
    pitch: PLAN_COPY.pro_monthly.pitch,
    features: planFeatures(proCaps),
    terms: cfg.automaticPayments ? "Renovación mensual automática. Cancelás desde Ajustes y conservás el período pagado."
      : cfg.commercialPilot ? "Durante el piloto: períodos de 30 días con renovación manual. Si pagás con una suscripción de Mercado Pago, la cancelás ahí."
        : "Durante el piloto: períodos de 30 días con renovación manual.",
    cta: `${verb} ${PLAN_COPY.pro_monthly.name}`,
    href: destination("pro_monthly"),
  };

  return (
    <>
      <PlanCarousel labels={["Prueba", PLAN_NAMES.pass, PLAN_NAMES.pro]} start={1}>
        <PlanCard plan={trialPlan} />
        <PassCard name={PLAN_NAMES.pass} badge="Para tu próximo auto" variants={passes} features={planFeatures(passCaps)} guarantee={PASS_GUARANTEE} initial="pass_30" />
        <PlanCard plan={proPlan} />
      </PlanCarousel>

      <section aria-labelledby="plan-custom" className="mt-5 grid gap-5 rounded-lg bg-muted p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_minmax(0,14rem)] lg:items-center">
        <div>
          <h3 id="plan-custom" className="text-xl font-bold">{CUSTOM_PLAN.name}</h3>
          <p className="mt-1"><span className="font-bold">{CUSTOM_PLAN.price}</span> <span className="text-sm text-muted-foreground">· {CUSTOM_PLAN.period}</span></p>
          <p className="mt-2 text-sm text-muted-foreground">{CUSTOM_PLAN.pitch}</p>
        </div>
        <ul className="grid gap-2.5 text-sm sm:grid-cols-2">
          {CUSTOM_PLAN.features.map((item) => (
            <li key={item} className="flex items-start gap-2.5"><Check aria-hidden className="mt-0.5 size-4 shrink-0" /><span>{item}</span></li>
          ))}
        </ul>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">{CUSTOM_PLAN.terms}</p>
          <Button asChild variant="outline" className="h-auto min-h-10 w-full whitespace-normal py-2 text-center">
            <a href={CUSTOM_PLAN.href} target="_blank" rel="noopener noreferrer">{CUSTOM_PLAN.cta}</a>
          </Button>
        </div>
      </section>

      <div className="mt-8 max-w-3xl space-y-2 border-t pt-6 text-sm text-muted-foreground">
        <p className="text-base text-foreground">Una búsqueda es un modelo, con sus versiones, años, kilómetros, presupuesto y zona. Si querés seguir varios modelos, cada uno cuenta como una búsqueda.{modelLessText(cfg.planLimits) ? ` ${modelLessText(cfg.planLimits)}` : ""}</p>
        <p>Todos los planes incluyen comparación con autos similares, explicación del precio y señales para revisar antes de contactar al vendedor. Los avisos que pasan el tope del día van al resumen. Las bajas de precio de tus favoritos se avisan de inmediato mientras el acceso siga vigente. La frecuencia de revisión depende de cada portal.</p>
        {/* Only Pro by Mercado Pago subscription renews by itself: automatic payments, or a pilot link. */}
        <p>{cfg.automaticPayments || cfg.commercialPilot
          ? "Los precios pueden actualizarse. Si tu plan se renueva solo, te avisamos por mail 30 días antes de un cambio de precio."
          : "Los precios pueden actualizarse. Ningún plan se renueva ni se cobra solo."}</p>
        <p>{cfg.automaticPayments
          ? "Pagás en Mercado Pago. Activamos el acceso cuando se aprueba el pago."
          : cfg.commercialPilot
            ? "Las altas y la confirmación de pagos se coordinan con la administración."
            : "Las altas pagas están en lista de espera."}</p>
      </div>
    </>
  );
}

/** Prueba gratis and Pro: the same eight rows as Particular, the duration row empty. */
function PlanCard({ plan }: { plan: PublicPlan }) {
  return (
    <article aria-label={plan.name} className={cn(PLAN_CARD, plan.id === "trial" && "bg-muted/40")}>
      <h3 className="text-xl font-bold">{plan.name}</h3>
      <div aria-hidden />
      <p className="mt-4 text-3xl font-bold"><span data-plan-price>{plan.price}</span>
        {plan.currency ? <span className="ml-1.5 text-sm font-medium text-muted-foreground">{plan.currency}</span> : null}</p>
      <p className="mt-1 text-sm text-muted-foreground">{plan.period}</p>
      <p className="mt-4 text-muted-foreground">{plan.pitch}</p>
      <PlanFeatures items={plan.features} />
      <p className="mt-5 text-sm text-muted-foreground">{plan.terms}</p>
      <div className="mt-auto pt-6">
        <Button asChild variant="outline" className="h-auto min-h-10 w-full whitespace-normal py-2 text-center">
          <Link href={plan.href}>{plan.cta}</Link>
        </Button>
      </div>
    </article>
  );
}
