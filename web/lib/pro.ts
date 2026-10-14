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
export const PLAN_NAMES = { free: "Prueba gratis", pass: "Particular", pro: "Agencia" } as const;
export type PlanTier = keyof typeof PLAN_NAMES;
/** The plan each offer buys (profiles.plan). */
export const OFFER_TIER: Record<WaitlistPlan, Exclude<PlanTier, "free">> = { pass_30: "pass", pro_monthly: "pro" };
export const PLAN_COPY: Record<WaitlistPlan, { name: string; period: string; pitch: string }> = {
  pass_30: { name: "Particular", period: "por 30 días", pitch: "Para encontrar tu próximo auto. Pago único." },
  pro_monthly: { name: "Agencia", period: "por mes", pitch: "Para quienes buscan vehículos habitualmente." },
};

/**
 * What each plan includes: app_config.plan_limits, the same values the
 * database and the worker apply. Pages show these, never their own numbers.
 * maxVisibleResults null = all of them; immediateAlertsPerDay 0 = digest only.
 */
export type PlanCaps = { maxProfiles: number; maxVisibleResults: number | null; immediateAlertsPerDay: number };
export type PlanLimitsConfig = Record<PlanTier, PlanCaps>;
export const DEFAULT_PLAN_LIMITS: PlanLimitsConfig = {
  free: { maxProfiles: 1, maxVisibleResults: 100, immediateAlertsPerDay: 3 },
  pass: { maxProfiles: 3, maxVisibleResults: null, immediateAlertsPerDay: 10 },
  pro: { maxProfiles: 20, maxVisibleResults: null, immediateAlertsPerDay: 50 },
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
      maxProfiles: whole(limits.max_profiles, 0) ?? DEFAULT_PLAN_LIMITS[tier].maxProfiles,
      maxVisibleResults: whole(limits.max_visible_results, 1),
      immediateAlertsPerDay: alertCap(limits, globalCap),
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
  return caps.maxVisibleResults == null ? "Todos los resultados disponibles" : `Hasta ${caps.maxVisibleResults} resultados`;
}
/** "Particular incluye hasta 10 avisos inmediatos … y Agencia, hasta 50; …" */
export function alertCapsText(limits: PlanLimitsConfig): string {
  const pass = limits.pass.immediateAlertsPerDay, pro = limits.pro.immediateAlertsPerDay;
  return `Particular incluye hasta ${counted(pass, "aviso inmediato", "avisos inmediatos")} de nuevas coincidencias por día y Agencia, hasta ${pro}; los que pasan el tope van al resumen.`;
}
export function alertsText(caps: PlanCaps): string {
  const n = caps.immediateAlertsPerDay;
  return n > 0 ? `Hasta ${counted(n, "aviso inmediato", "avisos inmediatos")} por día y resumen diario` : "Resumen diario de coincidencias";
}
export const PRO_BENEFITS = ["Avisos cuando detectamos coincidencias", "Comparación de precios publicados",
  "Puntaje explicado y señales para revisar", "Historial, favoritos y varias búsquedas"];
export type OfferPrice = { amount: number; currency: "ARS"; days: 30 };
export type ProOffer = Record<WaitlistPlan, OfferPrice> & { version: string };
export const DEFAULT_PRO_OFFER: ProOffer = {
  version: "ars-launch-2026-10", pass_30: { amount: 15_000, currency: "ARS", days: 30 },
  pro_monthly: { amount: 75_000, currency: "ARS", days: 30 },
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
  limits: { max_profiles?: number; max_visible_results?: number; immediate_alerts_per_day?: number; immediate_alerts?: boolean };
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
export type ProCtaState = {
  show: boolean; reason: "activity" | "plan_limit" | null; plan?: string;
  alert_clicks?: number; waitlist_plan?: WaitlistPlan | null;
};
export type BannerReason = "activity" | "plan_limit" | "results";

/** The plans banner. No fixed limits: `maxResults` is what the account's plan shows. */
export function bannerCopy(reason: BannerReason, maxResults: number | null = null): { title: string; body: string } {
  if (reason === "activity") {
    return { title: "Seguí buscando con Ese Auto", body: "Particular y Agencia suman búsquedas activas y más avisos inmediatos por día." };
  }
  if (reason === "plan_limit") {
    return { title: "Elegí capacidad para tus búsquedas", body: "Llegaste al máximo de búsquedas activas de tu plan. Particular y Agencia permiten seguir más modelos a la vez." };
  }
  return {
    title: "¿Querés ver todos los resultados?",
    body: `${maxResults != null ? `Tu plan muestra hasta ${maxResults} publicaciones por búsqueda.` : "Tu plan muestra parte de los resultados."} Particular y Agencia muestran todos los resultados disponibles.`,
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
export function visibleResults(total: number, limits: PlanLimits | null): { cap: number | null; over: boolean } {
  const max = limits?.limits.max_visible_results;
  if (max == null) return { cap: null, over: false };
  return { cap: limits?.enforced ? max : null, over: total > max };
}
export function accessDate(value: string): string {
  return new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeStyle: "short",
    timeZone: "America/Argentina/Buenos_Aires" }).format(new Date(value));
}
/**
 * Precio fundador: the first Agencia subscriptions keep the amount they
 * started with until founder_price_until (billing_checkouts). Null otherwise.
 */
export function founderNote(checkout: { amount: number; founder_number?: number | null; founder_price_until?: string | null }): string | null {
  if (checkout.founder_number == null || !checkout.founder_price_until) return null;
  const until = new Intl.DateTimeFormat("es-AR", { dateStyle: "long", timeZone: "America/Argentina/Buenos_Aires" })
    .format(new Date(checkout.founder_price_until));
  return `Precio fundador: ${planPrice(checkout.amount)} por mes, fijo hasta el ${until}.`;
}
export function accessDescription(access: PlanLimits): string {
  if (access.state === "pilot") return "Piloto abierto: los límites comerciales todavía no están habilitados.";
  if (access.state === "available") return "Tu prueba de 3 días empieza al activar la primera búsqueda.";
  if (access.state === "expired") return "Tu acceso venció. Conservamos los resultados y favoritos; elegí un plan para volver a monitorear.";
  if (access.expires_at) return `${access.state === "trial" ? "Prueba gratis" : PLAN_NAMES[access.plan]} vigente hasta ${accessDate(access.expires_at)} (hora argentina).`;
  return `${PLAN_NAMES[access.plan]} vigente.`;
}
