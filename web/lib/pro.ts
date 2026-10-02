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
export const PLAN_COPY: Record<WaitlistPlan, { name: string; period: string; pitch: string; searches: number }> = {
  pass_30: { name: "Particular", period: "por 30 días", pitch: "Para encontrar tu próximo auto. Pago único.", searches: 3 },
  pro_monthly: { name: "Agencia", period: "por mes", pitch: "Para quienes buscan vehículos habitualmente.", searches: 10 },
};
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
  limits: { max_profiles?: number; max_visible_results?: number; immediate_alerts?: boolean };
};
export type ProCtaState = {
  show: boolean; reason: "activity" | "plan_limit" | null; plan?: string;
  alert_clicks?: number; waitlist_plan?: WaitlistPlan | null;
};
export function visibleResults(total: number, limits: PlanLimits | null): { cap: number | null; over: boolean } {
  const max = limits?.limits.max_visible_results;
  if (max == null) return { cap: null, over: false };
  return { cap: limits?.enforced ? max : null, over: total > max };
}
export function accessDate(value: string): string {
  return new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeStyle: "short",
    timeZone: "America/Argentina/Buenos_Aires" }).format(new Date(value));
}
export function accessDescription(access: PlanLimits): string {
  if (access.state === "pilot") return "Piloto abierto: los límites comerciales todavía no están habilitados.";
  if (access.state === "available") return "Tu prueba de 3 días empieza al activar la primera búsqueda.";
  if (access.state === "expired") return "Tu acceso venció. Conservamos los resultados y favoritos; elegí un plan para volver a monitorear.";
  if (access.expires_at) return `${access.state === "trial" ? "Prueba gratis" : PLAN_NAMES[access.plan]} vigente hasta ${accessDate(access.expires_at)} (hora argentina).`;
  return `${PLAN_NAMES[access.plan]} vigente.`;
}
