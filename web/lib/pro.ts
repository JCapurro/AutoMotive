/**
 * "Probar Automotive Pro" (§52, sección 9): the plans the waitlist offers
 * (§33–34), where the CTA can appear, and the plan limits the web reads.
 * No charge yet: the prices are hypotheses (app_config.pro_offer).
 */

export const WAITLIST_PLANS = ["pro_monthly", "pass_30", "pass_90"] as const;
export type WaitlistPlan = (typeof WAITLIST_PLANS)[number];

export const PLACEMENTS = ["dashboard", "results", "settings", "plans"] as const;
export type Placement = (typeof PLACEMENTS)[number];

export function isWaitlistPlan(value: unknown): value is WaitlistPlan {
  return typeof value === "string" && (WAITLIST_PLANS as readonly string[]).includes(value);
}

export function isPlacement(value: unknown): value is Placement {
  return typeof value === "string" && (PLACEMENTS as readonly string[]).includes(value);
}

export const PLAN_COPY: Record<WaitlistPlan, { name: string; period: string; pitch: string }> = {
  pro_monthly: { name: "Pro mensual", period: "por mes", pitch: "Para seguir buscando sin fecha de cierre." },
  pass_30: { name: "Search Pass 30 días", period: "pago único", pitch: "Para una búsqueda corta: un mes de Pro." },
  pass_90: { name: "Search Pass 90 días", period: "pago único", pitch: "Si todavía estás mirando opciones." },
};

// §52: what Pro adds.
export const PRO_BENEFITS = [
  "Búsqueda cada pocos minutos",
  "Alertas inmediatas",
  "Opportunity Score",
  "Análisis de precios",
  "Múltiples búsquedas",
];

export type ProOffer = Record<WaitlistPlan, { price_usd: number }>;

export const DEFAULT_PRO_OFFER: ProOffer = {
  pro_monthly: { price_usd: 15 },
  pass_30: { price_usd: 12 },
  pass_90: { price_usd: 25 },
};

/** app_config.pro_offer, with the defaults for a missing or broken plan. */
export function proOffer(value: unknown): ProOffer {
  const raw = (value ?? {}) as Record<string, { price_usd?: unknown } | undefined>;
  return Object.fromEntries(
    WAITLIST_PLANS.map((plan) => {
      const price = Number(raw[plan]?.price_usd);
      return [plan, { price_usd: Number.isFinite(price) && price > 0 ? price : DEFAULT_PRO_OFFER[plan].price_usd }];
    }),
  ) as ProOffer;
}

/** my_plan_limits(): the user's effective plan and its limits (sección 12). */
export type PlanLimits = {
  plan: "free" | "pro" | "pass";
  enforced: boolean;
  limits: { max_profiles?: number; max_visible_results?: number; immediate_alerts?: boolean };
};

/** pro_cta_state(): whether to show the CTA and why. */
export type ProCtaState = {
  show: boolean;
  reason: "activity" | "plan_limit" | null;
  plan?: string;
  alert_clicks?: number;
  waitlist_plan?: WaitlistPlan | null;
};

/**
 * Results a plan lets the user see: all of them unless the limit is enforced
 * and the plan has one. `over` says the limit was passed (enforced or not).
 */
export function visibleResults(total: number, limits: PlanLimits | null): { cap: number | null; over: boolean } {
  const max = limits?.limits.max_visible_results;
  if (max == null) return { cap: null, over: false };
  return { cap: limits?.enforced ? max : null, over: total > max };
}
