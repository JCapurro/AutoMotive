import { z } from "zod";

import { proOffer } from "@/lib/pro";

export const MAX_CONFIG_INTEGER = 2_147_483_647;
/** commercial_payments and billing_checkouts use numeric(12,2). */
export const MAX_OFFER_ARS = 9_999_999_999;
/** Keep an admin's email validity bounded to 30 days; avoid date overflow and stale mail. */
export const MAX_LIFECYCLE_WINDOW_HOURS = 720;
const count = z.number().int().min(0).max(MAX_CONFIG_INTEGER);
const positiveCount = count.min(1);
const price = z.object({ amount: z.number().int().positive().max(MAX_OFFER_ARS), currency: z.literal("ARS"), days: z.literal(30) }).passthrough();
export const AdminOfferInput = z.object({ version: z.string().trim().min(1).max(80), pass_30: price, pro_monthly: price }).passthrough();
const plan = z.object({
  max_profiles: count.optional(), max_visible_results: positiveCount.nullable().optional(),
  max_total_results: positiveCount.optional(),
  immediate_alerts_per_day: count.optional(), immediate_alerts: z.boolean().optional(),
  threshold_alerts: z.boolean().optional(), model_less_search: z.boolean().optional(),
  max_locations: positiveCount.nullable().optional(),
}).passthrough();
export const AdminPlanLimitsInput = z.object({ enforced: z.boolean().optional(), free: plan.optional(), pass: plan.optional(), pro: plan.optional() }).passthrough();

/** Must match worker/notifications/lifecycle.py: KINDS and DEFAULTS. Missing kinds keep their default. */
export const LIFECYCLE_KINDS = {
  trial_no_matches: { label: "Prueba sin coincidencias (24 h)", enabled: true },
  trial_ended: { label: "Fin de la prueba", enabled: true },
  pass_expiring: { label: "Particular próximo a vencer", enabled: true },
  pass_expires_today: { label: "Particular vence hoy", enabled: true },
  count_after_expiry: { label: "Conteo después del vencimiento", enabled: true },
  search_activated: { label: "Bienvenida a la primera búsqueda", enabled: true },
  search_abandoned: { label: "Búsqueda abandonada", enabled: false },
  search_not_started: { label: "Cuenta sin búsqueda", enabled: false },
  search_feedback: { label: "Opinión sobre la búsqueda", enabled: false },
  bonus_trial_offer: { label: "Oferta de prueba adicional", enabled: false },
  bonus_trial_ending: { label: "Prueba adicional por vencer", enabled: false },
  bonus_trial_ended: { label: "Fin de la prueba adicional", enabled: false },
} as const;
export const LIFECYCLE_DEFAULTS = { enabled: true, send_from: "09:00", send_until: "21:00", window_hours: 48, max_per_day: 30 };
const clock = z.string().regex(/^(?:[01]\d|2[0-3]):[0-5]\d$/, "Usá un horario HH:MM entre 00:00 y 23:59.");
const kindShape = Object.fromEntries(Object.keys(LIFECYCLE_KINDS).map((kind) => [kind, z.boolean().optional()]));
export const AdminLifecycleInput = z.object({
  enabled: z.boolean().optional(), send_from: clock.optional(), send_until: clock.optional(),
  window_hours: positiveCount.max(MAX_LIFECYCLE_WINDOW_HOURS, "La vigencia máxima es de 720 horas (30 días).").optional(), max_per_day: count.optional(),
  kinds: z.object(kindShape).passthrough().optional(),
}).passthrough().superRefine((value, context) => {
  const from = value.send_from ?? LIFECYCLE_DEFAULTS.send_from;
  const until = value.send_until ?? LIFECYCLE_DEFAULTS.send_until;
  if (from >= until) context.addIssue({ code: "custom", path: ["send_until"], message: "El horario de cierre debe ser posterior al de inicio, dentro del mismo día." });
  const minutes = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3));
  const night = 24 - (minutes(until) - minutes(from)) / 60;
  if ((value.window_hours ?? LIFECYCLE_DEFAULTS.window_hours) <= night) context.addIssue({ code: "custom", path: ["window_hours"], message: "La vigencia debe superar las horas fuera del horario de envío para no perder emails nocturnos." });
});

export const SourceValuesInput = z.object({
  enabled: z.boolean(),
  crawl_interval_seconds: z.number().int().min(60, "Mínimo 60 segundos.").max(86_400, "Máximo 86.400 segundos (un día)."),
}).strict();
export const SourceUpdateInput = SourceValuesInput.extend({
  id: z.string().min(1).max(100),
  expected: z.object({ enabled: z.boolean(), crawl_interval_seconds: z.number().int().positive().max(MAX_CONFIG_INTEGER) }).strict(),
}).strict();

export function configObject(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function shape(value: unknown): string {
  return value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
}
export function validateConfigChange(key: string, value: unknown, current: unknown): string | null {
  if (key === "commercial_pilot") return "Habilitá el piloto desde Cobros para iniciar las pruebas y aplicar límites juntos.";
  if (!z.json().safeParse(value).success) return "El valor debe ser JSON con números finitos.";
  if (value === null) return "El valor no puede ser null.";
  if (shape(current) !== shape(value)) return `El valor tiene que ser ${shape(current)}, como el actual.`;
  if (key === "pro_offer") {
    if (!AdminOfferInput.safeParse(value).success) return "La oferta requiere versión (hasta 80 caracteres) y ambos planes con importe entero entre 1 y 9.999.999.999, moneda ARS y 30 días.";
    const before = proOffer(current), after = proOffer(value);
    if (JSON.stringify([before.pass_30.amount, before.pro_monthly.amount]) !== JSON.stringify([after.pass_30.amount, after.pro_monthly.amount]) && before.version === after.version) {
      return "Cambiá la versión de la oferta al modificar los importes. Cada confirmación debe identificar su precio.";
    }
  }
  if (key === "plan_limits") {
    if (!AdminPlanLimitsInput.safeParse(value).success) return "Revisá los límites: cantidades enteras entre 0 y 2.147.483.647, resultados y zonas desde 1 (o sin tope), funciones true/false.";
    if (configObject(value).enforced !== configObject(current).enforced) return "La aplicación de límites se cambia desde Cobros, junto con el piloto comercial.";
  }
  if (key === "lifecycle_emails") {
    const parsed = AdminLifecycleInput.safeParse(value);
    if (!parsed.success) return parsed.error.issues[0]?.message ?? "Revisá los horarios, tipos y topes de emails.";
  }
  return null;
}

/** Object key order does not make a setting change. Arrays retain their order. */
export function sameConfig(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => sameConfig(v, b[i]));
  if (a && b && typeof a === "object" && typeof b === "object") {
    const left = Object.keys(a), right = Object.keys(b);
    return left.length === right.length && left.every((key) => key in b && sameConfig((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]));
  }
  return false;
}

export type ConfigDifference = { path: string; before: unknown; after: unknown };
export function configFieldLabel(key: string, path: string): string {
  if (key === "pro_offer") return ({ version: "Versión de la oferta", "pass_30.amount": "Particular: importe (ARS)", "pro_monthly.amount": "Pro: importe (ARS)" } as Record<string, string>)[path] ?? path;
  if (key === "plan_limits") {
    const [tier, field] = path.split(".");
    const planName = ({ free: "Prueba gratis", pass: "Particular", pro: "Pro" } as Record<string, string>)[tier];
    const fieldName = ({ max_profiles: "búsquedas activas", max_visible_results: "resultados por búsqueda", max_total_results: "resultados acumulados durante la prueba", immediate_alerts_per_day: "avisos inmediatos por día", max_locations: "zonas por búsqueda", threshold_alerts: "umbral de oportunidad", model_less_search: "búsqueda sin modelo" } as Record<string, string>)[field];
    if (planName) return fieldName ? `${planName}: ${fieldName}` : planName + (field ? `: ${field}` : "");
  }
  if (key === "lifecycle_emails") {
    if (path.startsWith("kinds.")) return LIFECYCLE_KINDS[path.slice(6) as keyof typeof LIFECYCLE_KINDS]?.label ?? path;
    return ({ enabled: "Envío de emails del plan", send_from: "Enviar desde (hora argentina)", send_until: "Enviar hasta (hora argentina)", window_hours: "Vigencia del evento (horas)", max_per_day: "Emails del plan por día" } as Record<string, string>)[path] ?? path;
  }
  return path;
}
export function configDifferences(before: unknown, after: unknown, prefix = ""): ConfigDifference[] {
  if (sameConfig(before, after)) return [];
  if (before && after && typeof before === "object" && typeof after === "object" && !Array.isArray(before) && !Array.isArray(after)) {
    return [...new Set([...Object.keys(before), ...Object.keys(after)])].flatMap((key) => configDifferences((before as Record<string, unknown>)[key], (after as Record<string, unknown>)[key], prefix ? `${prefix}.${key}` : key));
  }
  return [{ path: prefix || "valor", before, after }];
}

export type ConfigAudit = { id: number; target_type: string; target_key: string; actor_id: string | null; actor_email: string | null; before_value: unknown; after_value: unknown; created_at: string };
