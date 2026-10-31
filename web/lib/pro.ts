/** Ese Auto: route B. Keep the existing database plan identifiers. */
export const WAITLIST_PLANS = ["pass_30", "pro_monthly"] as const;
export type WaitlistPlan = (typeof WAITLIST_PLANS)[number];
export const PLACEMENTS = ["dashboard", "results", "settings", "plans"] as const;
export type Placement = (typeof PLACEMENTS)[number];
export function isWaitlistPlan(value: unknown): value is WaitlistPlan {
  return typeof value === "string" && (WAITLIST_PLANS as readonly string[]).includes(value);
}
export function isPlacement(value: unknown): value is Placement {
  return typeof value === "string" && (PLACEMENTS as readonly string[]).includes(value);
}
export const PLAN_NAMES = { free: "Prueba gratis", pass: "Particular", pro: "Pro" } as const;
export type PlanTier = keyof typeof PLAN_NAMES;
/** The plan each offer buys (profiles.plan). */
export const OFFER_TIER: Record<WaitlistPlan, Exclude<PlanTier, "free">> = { pass_30: "pass", pro_monthly: "pro" };
export const PLAN_COPY: Record<WaitlistPlan, { name: string; period: string; pitch: string }> = {
  pass_30: { name: "Particular", period: "por 30 días", pitch: "Para encontrar tu próximo auto. Pago único." },
  pro_monthly: { name: "Pro", period: "por mes", pitch: "Para agencias y revendedores que necesitan llegar primero." },
};

/**
 * What each plan includes: app_config.plan_limits, the same values the
 * database and the worker apply. Pages show these, never their own numbers.
 * maxVisibleResults null = all of them; immediateAlertsPerDay 0 = digest only.
 * thresholdAlerts: the per-search opportunity threshold (3.2), Pro's.
 * modelLessSearch: searching by body type without a model (docs/CARROCERIA.md).
 */
export type PlanCaps = {
  maxProfiles: number; maxVisibleResults: number | null; immediateAlertsPerDay: number;
  /** Distinct publications across the whole free trial, including recreated searches. */
  maxTotalResults?: number;
  thresholdAlerts: boolean; modelLessSearch: boolean;
  /** Places one search may look in (its own and the ones it adds); null = no cap. */
  maxLocations: number | null;
};
export type PlanLimitsConfig = Record<PlanTier, PlanCaps>;
export const DEFAULT_PLAN_LIMITS: PlanLimitsConfig = {
  free: { maxProfiles: 1, maxVisibleResults: 50, maxTotalResults: 50, immediateAlertsPerDay: 3, thresholdAlerts: false, modelLessSearch: false, maxLocations: 3 },
  pass: { maxProfiles: 3, maxVisibleResults: null, immediateAlertsPerDay: 10, thresholdAlerts: false, modelLessSearch: true, maxLocations: null },
  pro: { maxProfiles: 20, maxVisibleResults: null, immediateAlertsPerDay: 50, thresholdAlerts: true, modelLessSearch: true, maxLocations: null },
};
function whole(value: unknown, min: number): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min ? value : null;
}
/** As public.plan_alert_cap: the legacy boolean immediate_alerts means the global cap or none. */
export function alertCap(limits: Record<string, unknown>, globalCap: number): number {
  if ("immediate_alerts_per_day" in limits) return whole(limits.immediate_alerts_per_day, 0) ?? 0;
  return limits.immediate_alerts === true ? globalCap : 0;
}
/** Reads app_config.plan_limits; a plan missing from it keeps its default. */
export function planLimits(value: unknown, globalCap = 10): PlanLimitsConfig {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const out = { ...DEFAULT_PLAN_LIMITS };
  for (const tier of Object.keys(DEFAULT_PLAN_LIMITS) as PlanTier[]) {
    const plan = raw[tier];
    if (!plan || typeof plan !== "object") continue;
    const limits = plan as Record<string, unknown>;
    out[tier] = {
      ...(tier === "free" ? { maxTotalResults: whole(limits.max_total_results, 1) ?? 50 } : {}),
      maxProfiles: whole(limits.max_profiles, 0) ?? DEFAULT_PLAN_LIMITS[tier].maxProfiles,
      maxVisibleResults: whole(limits.max_visible_results, 1),
      immediateAlertsPerDay: alertCap(limits, globalCap),
      thresholdAlerts: limits.threshold_alerts === true,
      modelLessSearch: limits.model_less_search === true,
      // Absent keeps the plan's default (the free plan's 3); present and not a count = no cap.
      maxLocations: "max_locations" in limits ? whole(limits.max_locations, 1) : DEFAULT_PLAN_LIMITS[tier].maxLocations,
    };
  }
  return out;
}
const WORDS = ["cero", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"];
/** "tres opciones": small counts in words, the rest in digits. */
export function inWords(n: number): string {
  return WORDS[n] ?? String(n);
}
function counted(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}
export function searchesText(caps: PlanCaps, upTo = true): string {
  return `${upTo ? "Hasta " : ""}${counted(caps.maxProfiles, "búsqueda activa", "búsquedas activas")}`;
}
export function resultsText(caps: PlanCaps): string {
  if (caps.maxTotalResults != null) return `Hasta ${caps.maxTotalResults} resultados en total durante la prueba`;
  return caps.maxVisibleResults == null ? "Todos los resultados disponibles" : `Hasta ${caps.maxVisibleResults} resultados`;
}
/** "Particular incluye hasta 10 avisos inmediatos … y Pro, hasta 50 …; …" */
export function alertCapsText(limits: PlanLimitsConfig): string {
  const pass = limits.pass.immediateAlertsPerDay, pro = limits.pro.immediateAlertsPerDay;
  const threshold = limits.pro.thresholdAlerts ? ", o sin tope para las oportunidades que elegís" : "";
  return `Particular incluye hasta ${counted(pass, "aviso inmediato", "avisos inmediatos")} de nuevas coincidencias por día y Pro, hasta ${pro}${threshold}; los que pasan el tope van al resumen.`;
}
/** Pro: the daily cap still applies; only what reaches a search's threshold goes out past it. */
export function thresholdFeature(caps: PlanCaps): string {
  return `Hasta ${counted(caps.immediateAlertsPerDay, "aviso inmediato", "avisos inmediatos")} por día, sin tope para las oportunidades que superan tu umbral`;
}
export const MODEL_LESS_FEATURE = "Búsqueda por carrocería, sin modelo";
/** A paid plan's card lines: what plan_limits says it includes (Pro: the threshold). */
export function planFeatures(caps: PlanCaps): string[] {
  return [searchesText(caps), resultsText(caps), caps.thresholdAlerts ? thresholdFeature(caps) : alertsText(caps),
    ...(caps.modelLessSearch ? [MODEL_LESS_FEATURE] : []), "Historial y favoritos"];
}
/**
 * "Con Particular y Pro también podés buscar por carrocería…", from the plans
 * plan_limits gives model_less_search; null when no plan has it.
 */
export function modelLessText(limits: PlanLimitsConfig): string | null {
  const plans = (["pass", "pro"] as const).filter((tier) => limits[tier].modelLessSearch).map((tier) => PLAN_NAMES[tier]);
  if (!plans.length) return null;
  return `Con ${plans.join(" y ")} también podés buscar por carrocería, sin elegir modelo (por ejemplo, cualquier SUV hasta un precio máximo): cuenta como una búsqueda.`;
}
export function alertsText(caps: PlanCaps): string {
  const n = caps.immediateAlertsPerDay;
  return n > 0 ? `Hasta ${counted(n, "aviso inmediato", "avisos inmediatos")} por día y resumen diario` : "Resumen diario de coincidencias";
}
export const PRO_BENEFITS = ["Avisos cuando detectamos coincidencias", "Comparación de precios publicados",
  "Puntaje explicado y señales para revisar", "Historial, favoritos y varias búsquedas"];
export type OfferPrice = { amount: number; currency: "ARS"; days: 30 };
export type ProOffer = Record<WaitlistPlan, OfferPrice> & { version: string };
/** As app_config.pro_offer since fase 3 (20261026120000_pro_price): only a fallback. */
export const DEFAULT_PRO_OFFER: ProOffer = {
  version: "ars-pro-2026-10", pass_30: { amount: 15_000, currency: "ARS", days: 30 },
  pro_monthly: { amount: 100_000, currency: "ARS", days: 30 },
};
export function proOffer(value: unknown): ProOffer {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const out = { ...DEFAULT_PRO_OFFER };
  if (typeof raw.version === "string" && raw.version.trim()) out.version = raw.version;
  for (const plan of WAITLIST_PLANS) {
    const price = raw[plan] as Partial<OfferPrice> | undefined;
    // A legacy price_usd must never become a peso amount by changing its symbol.
    if (price?.currency === "ARS" && price.days === 30 && typeof price.amount === "number"
      && Number.isSafeInteger(price.amount) && price.amount > 0) out[plan] = price as OfferPrice;
  }
  return out;
}
export function planPrice(amount: number): string {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 }).format(amount);
}
export type PlanLimits = {
  plan: "free" | "pro" | "pass"; enforced: boolean; active?: boolean;
  state?: "pilot" | "available" | "trial" | "paid" | "expired";
  expires_at?: string | null; trial_started_at?: string | null; trial_expires_at?: string | null;
  active_searches?: number;
  free_results_used?: number; free_results_limit?: number | null;
  limits: {
    max_profiles?: number; max_visible_results?: number; max_total_results?: number; immediate_alerts_per_day?: number; immediate_alerts?: boolean;
    threshold_alerts?: boolean; model_less_search?: boolean; max_locations?: number;
    seller_filter?: boolean; contact_email?: boolean;
  };
};
/** Custom is arranged over WhatsApp. wa.me wants the full international number: 54 9 11 3345-4741. */
export const CUSTOM_WHATSAPP = "5491133454741";
export const CUSTOM_PLAN = {
  id: "custom" as const,
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
  href: `https://wa.me/${CUSTOM_WHATSAPP}?text=${encodeURIComponent("Hola, me interesa un plan Custom de Ese Auto.\n\nNecesito buscar:\nCantidad de búsquedas:\nModelos y zonas:\nDuración estimada:\n")}`,
};
export type PlanChoice = WaitlistPlan | typeof CUSTOM_PLAN.id;
/** The snapshot resolves expiry; a stored plan name alone doesn't prove paid access. */
export function canAcquirePlan(access: PlanLimits | null): boolean {
  if (!access) return false;
  return access.plan === "free" || access.active === false;
}
/** A running Particular can be extended: the new 30 days add up to its end (2.4). */
export function extendsPass(access: PlanLimits | null): boolean {
  return access?.plan === "pass" && access.state === "paid" && access.active !== false;
}
export type ProCtaState = {
  show: boolean; reason: "activity" | "plan_limit" | null; plan?: string;
  alert_clicks?: number; waitlist_plan?: WaitlistPlan | null;
};
export type BannerReason = "activity" | "plan_limit" | "results";

/** The plans banner. No fixed limits: `maxResults` is what the account's plan shows. */
export function bannerCopy(reason: BannerReason, maxResults: number | null = null): { title: string; body: string } {
  if (reason === "activity") {
    return { title: "Seguí buscando con Ese Auto", body: "Particular y Pro suman búsquedas activas y más avisos inmediatos por día." };
  }
  if (reason === "plan_limit") {
    return { title: "Elegí capacidad para tus búsquedas", body: "Llegaste al máximo de búsquedas activas de tu plan. Particular y Pro permiten seguir más modelos a la vez." };
  }
  return {
    title: "¿Querés ver todos los resultados?",
    body: `${maxResults != null ? `Tu plan muestra hasta ${maxResults} publicaciones por búsqueda.` : "Tu plan muestra parte de los resultados."} Particular y Pro muestran todos los resultados disponibles.`,
  };
}
/** Daily immediate alerts of the account's plan; null while the pilot doesn't enforce limits. */
export function accountAlertCap(access: PlanLimits | null, limits: PlanLimitsConfig): number | null {
  return access?.enforced ? limits[access.plan].immediateAlertsPerDay : null;
}
/** Whether the account gets immediate alerts at all (false: digest only, with enforced limits). */
export function includesImmediateAlerts(access: PlanLimits | null): boolean {
  return !access?.enforced || alertCap(access.limits, 1) > 0;
}
/**
 * How many more searches the account can activate: null without enforced
 * limits (the open pilot) or an unknown plan. The database still decides.
 */
export function searchCapacity(access: PlanLimits | null): number | null {
  if (!access?.enforced || access.limits.max_profiles == null) return null;
  return Math.max(access.limits.max_profiles - (access.active_searches ?? 0), 0);
}
/**
 * How many places one search may look in (its own plus the ones it adds):
 * null without enforced limits or a cap (Particular and Pro). The web checks
 * it on save; the free plan's is app_config.plan_limits.free.max_locations.
 */
export function locationCap(access: PlanLimits | null): number | null {
  if (!access?.enforced) return null;
  // A config without the key (before its migration) keeps the plan's default.
  const plan = access.plan as PlanTier | undefined;
  const cap = "max_locations" in access.limits
    ? access.limits.max_locations
    : plan && plan in DEFAULT_PLAN_LIMITS ? DEFAULT_PLAN_LIMITS[plan].maxLocations : null;
  return typeof cap === "number" && cap >= 1 ? cap : null;
}
/** "Con la prueba gratis podés buscar en hasta 3 zonas…", null when there is no cap. */
export function locationCapText(cap: number | null): string | null {
  return cap == null ? null : `Tu plan permite buscar en hasta ${inWords(cap)} ${cap === 1 ? "zona" : "zonas"} por búsqueda.`;
}
export function visibleResults(total: number, limits: PlanLimits | null): { cap: number | null; over: boolean } {
  const max = limits?.limits.max_visible_results;
  if (max == null) return { cap: null, over: false };
  return { cap: limits?.enforced ? max : null, over: total > max };
}
/** Account usage, independent of this search's current filters, sort, or count. */
export function freeResultQuota(access: PlanLimits | null): { used: number; limit: number; reached: boolean } | null {
  if (!access?.enforced || access.plan !== "free" || access.free_results_limit == null) return null;
  const limit = access.free_results_limit;
  const used = access.free_results_used ?? 0;
  return { used, limit, reached: used >= limit };
}
export function accessDate(value: string): string {
  return new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeStyle: "short",
    timeZone: "America/Argentina/Buenos_Aires" }).format(new Date(value));
}
/**
 * Precio fundador: the first Agencia subscriptions (Pro since fase 3) keep
 * the amount they started with until founder_price_until (billing_checkouts).
 * Null otherwise.
 */
export function founderNote(checkout: { amount: number; founder_number?: number | null; founder_price_until?: string | null }): string | null {
  if (checkout.founder_number == null || !checkout.founder_price_until) return null;
  const until = new Intl.DateTimeFormat("es-AR", { dateStyle: "long", timeZone: "America/Argentina/Buenos_Aires" })
    .format(new Date(checkout.founder_price_until));
  return `Precio fundador: ${planPrice(checkout.amount)} por mes, fijo hasta el ${until}.`;
}
export function accessDescription(access: PlanLimits): string {
  if (access.state === "pilot") {
    const trialEnd = access.trial_expires_at ? ` Tu prueba termina el ${accessDate(access.trial_expires_at)} (hora argentina).` : "";
    return `Durante el piloto todavía no aplicamos los límites de los planes.${trialEnd}`;
  }
  if (access.state === "available") return "Tu prueba de 3 días empieza al activar la primera búsqueda.";
  if (access.state === "expired") return "Tu acceso venció. Conservamos los resultados y favoritos; elegí un plan para volver a monitorear.";
  if (access.expires_at) return `${access.state === "trial" ? "Prueba gratis" : PLAN_NAMES[access.plan]} vigente hasta ${accessDate(access.expires_at)} (hora argentina).`;
  return `${PLAN_NAMES[access.plan]} vigente.`;
}
