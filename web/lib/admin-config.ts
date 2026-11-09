import { z } from "zod";

import { costEstimatorProblem } from "@/lib/cost-estimator";
import { proOffer } from "@/lib/pro";
import { RED_FLAGS_ORDER_MESSAGE, RedFlagsOrderInput } from "@/lib/red-flags";
import { RiskConfigInput } from "@/lib/risk-checklist";

export const MAX_CONFIG_INTEGER = 2_147_483_647;
/** commercial_payments and billing_checkouts use numeric(12,2). */
export const MAX_OFFER_ARS = 9_999_999_999;
/** Keep an admin's email validity bounded to 30 days; avoid date overflow and stale mail. */
export const MAX_LIFECYCLE_WINDOW_HOURS = 720;
const count = z.number().int().min(0).max(MAX_CONFIG_INTEGER);
const positiveCount = count.min(1);
const price = z.object({ amount: z.number().int().positive().max(MAX_OFFER_ARS), currency: z.literal("ARS"), days: z.literal(30) }).passthrough();
const weekPrice = price.extend({ days: z.literal(7) });
export const AdminOfferInput = z.object({ version: z.string().trim().min(1).max(80), pass_30: price, pass_7: weekPrice.optional(), pro_monthly: price }).passthrough();
const plan = z.object({
  max_profiles: count.optional(), max_visible_results: positiveCount.nullable().optional(),
  max_total_results: positiveCount.optional(),
  immediate_alerts_per_day: count.optional(), immediate_alerts: z.boolean().optional(),
  threshold_alerts: z.boolean().optional(), model_less_search: z.boolean().optional(),
  max_locations: positiveCount.nullable().optional(),
  total_cost: z.boolean().optional(),
  // PRO-01: the strict seller filter and the «mensaje listo» block in the opportunity email.
  seller_filter: z.boolean().optional(), contact_email: z.boolean().optional(),
  // PRO-02: the estimated dealer margin (line, order and threshold) and the smallest threshold in USD.
  dealer_margin: z.boolean().optional(), min_threshold_usd: positiveCount.max(1_000_000).optional(),
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

/** PRO-02: app_config.dealer_margin, the rules of worker/intelligence/margin.py parse_config. */
export const DEALER_MARGIN_MESSAGE = "dealer_margin necesita reconditioning.pct (0 a 100), reconditioning.min_usd (0 o más) y transfer.enabled (true/false); as_of en formato AAAA-MM-DD; plausible_ratio, si está, min entre 0 y 1 y max mayor que 1.";
export const DealerMarginInput = z.object({
  as_of: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  source: z.string().optional(),
  reconditioning: z.object({ pct: z.number().min(0).max(100), min_usd: z.number().min(0) }).passthrough(),
  transfer: z.object({ enabled: z.boolean() }).passthrough(),
  // Optional: without it the worker uses {min: 0.4, max: 3} (margin.PLAUSIBLE_RATIO); an invalid one is refused here.
  plausible_ratio: z.object({ min: z.number().gt(0).lt(1), max: z.number().gt(1) }).passthrough().optional(),
}).passthrough();

export const SourceValuesInput = z.object({
  enabled: z.boolean(),
  crawl_interval_seconds: z.number().int().min(60, "Mínimo 60 segundos.").max(86_400, "Máximo 86.400 segundos (un día)."),
}).strict();
export const SourceUpdateInput = SourceValuesInput.extend({
  id: z.string().min(1).max(100),
  expected: z.object({ enabled: z.boolean(), crawl_interval_seconds: z.number().int().positive().max(MAX_CONFIG_INTEGER) }).strict(),
}).strict();

/** F-02: same bounds as worker/intelligence/config.py seller_classification. */
export const SELLER_CLASSIFICATION_MESSAGE = "enabled debe ser true/false, min_listings un entero entre 2 y 100 y window_days entre 1 y 180.";
export const SellerClassificationInput = z.object({
  enabled: z.boolean(),
  min_listings: z.number().int().min(2).max(100),
  window_days: z.number().int().min(1).max(180),
}).strict();

/**
 * PAR-04: llm_limits.model_guide, the guide generation's switch and caps
 * (admin_request_model_guide and worker pipeline/llm_jobs.py read them). At most
 * 3 guide questions per listing: the backlog's «hasta 3» (the worker clamps too).
 */
export const MODEL_GUIDE_LIMITS_MESSAGE = "model_guide necesita enabled (true/false), per_day y per_month enteros de 0 a 10.000 (per_day no mayor que per_month), queued_ttl_minutes de 1 a 1.440, timeout_seconds de 10 a 900 y max_questions_in_listing de 0 a 3.";
export const ModelGuideLimitsInput = z.object({
  enabled: z.boolean(),
  per_day: z.number().int().min(0).max(10_000),
  per_month: z.number().int().min(0).max(10_000),
  queued_ttl_minutes: z.number().int().min(1).max(1_440).optional(),
  timeout_seconds: z.number().int().min(10).max(900).optional(),
  max_questions_in_listing: z.number().int().min(0).max(3).optional(),
}).passthrough().refine((v) => v.per_day <= v.per_month, { path: ["per_day"] });
export const LlmLimitsInput = z.object({
  per_user_hour: count.optional(),
  email_only_per_user_hour: count.optional(),
  model_guide: ModelGuideLimitsInput.optional(),
}).passthrough();
/** PAR-04: app_config.model_guides, the pilot's guide ids and the public events' caps (log_guide_event). */
export const MODEL_GUIDES_MESSAGE = "model_guides necesita pilot (lista de ids de guías) y, si está, events.per_guide_minute y events.per_guide_hour enteros de 1 a 100.000.";
export const ModelGuidesConfigInput = z.object({
  pilot: z.array(z.number().int().positive()).max(100),
  events: z.object({ per_guide_minute: z.number().int().min(1).max(100_000), per_guide_hour: z.number().int().min(1).max(100_000) }).passthrough().optional(),
}).passthrough();
/** PAR-05, Prueba B: app_config.sell_intent (lib/sell-intent.ts, worker/notifications/templates.py). */
export const SELL_INTENT_CONFIG_MESSAGE = "sell_intent necesita ask y agencies_contact true/false, y since una fecha ISO (AAAA-MM-DD o con hora).";
export const SellIntentConfigInput = z.object({
  ask: z.boolean(),
  agencies_contact: z.boolean(),
  since: z.string().refine((v) => /^\d{4}-\d{2}-\d{2}/.test(v) && Number.isFinite(Date.parse(v))),
}).passthrough();
/** Aviso de zona: app_config.zone_notice, the notice's switch (lib/zone-notice.ts zoneNoticeConfig). */
export const ZONE_NOTICE_CONFIG_MESSAGE = "zone_notice necesita enabled (true/false).";
export const ZoneNoticeConfigInput = z.object({ enabled: z.boolean() }).passthrough();
/** Prueba gratis: app_config.trial_reserve, room in the trial for new listings (lib/trial-reserve.ts). */
export const TRIAL_RESERVE_CONFIG_MESSAGE = "trial_reserve necesita enabled (true/false) y backfill_max (entero de 0 a 1000).";
export const TrialReserveConfigInput = z.object({ enabled: z.boolean(), backfill_max: z.number().int().min(0).max(1000) }).passthrough();

/**
 * Bounds of the scoring, re-score and alert keys: the same table as
 * worker/intelligence/config.py (Bound, _merge), which falls back to the
 * default key by key. Before them a threshold saved as "80", a 0 divisor or
 * every weight at 0 broke the scoring of every search within a minute.
 */
type NumberBound = { min: number; max: number; integer?: boolean; aboveMin?: boolean };
const share: NumberBound = { min: 0, max: 1 };
const whole = (min: number, max: number): NumberBound => ({ min, max, integer: true });
const SCORE_WEIGHT_DEFAULTS = { price: 35, match: 25, km: 15, trim: 10, recency: 10, completeness: 5 };
const LEVEL_THRESHOLD_DEFAULTS = { high: 85, good: 70, match: 50 };
const GUARD_DEFAULTS = { suspicious_pct: 50, partial_pct: 65 };
const SCORE_WEIGHT_BOUNDS = Object.fromEntries(Object.keys(SCORE_WEIGHT_DEFAULTS).map((k) => [k, { min: 0, max: 1000 }]));
const LEVEL_THRESHOLD_BOUNDS = Object.fromEntries(Object.keys(LEVEL_THRESHOLD_DEFAULTS).map((k) => [k, { min: 0, max: 100 }]));
const SCORE_CURVE_BOUNDS: Record<string, Record<string, NumberBound>> = {
  price: { base: share, pct_per_unit: { min: 0, max: 100, aboveMin: true } },
  match: { unknown_penalty: share },
  km: { base: share, slope: { min: 0, max: 10 } },
  trim: { preferred: share, unknown: share, other: share, no_preference: share },
  recency: { half_life_hours: { min: 0, max: 720, aboveMin: true } },
  completeness: { min_description_chars: whole(0, 5000), min_images: whole(0, 50) },
  // From 25% below the median a price is still a deal, not a down payment.
  guards: { suspicious_pct: { min: 25, max: 100 }, partial_pct: { min: 25, max: 100 } },
};
// public.comparables() casts year_tol, max_age_days and gone_max_age_days to integer.
const COMPARABLES_BOUNDS = {
  min_n: whole(1, 1000), year_tol: whole(0, 10), km_tol_pct: whole(0, 100), max_age_days: whole(1, 180),
  confirm_grace_hours: whole(0, 720), gone_max_age_days: whole(1, 180),
};
const RESCORE_BOUNDS = { days: whole(1, 180) };
// The re-score slots are hour + k · every_hours within the day (worker/pipeline/rescore.py next_slot),
// so only a divisor of 24 keeps them evenly spaced; the worker runs any other value once a day.
const RESCORE_EVERY_HOURS = [1, 2, 3, 4, 6, 8, 12, 24];
// SQL casts alerts_max_per_user_day to integer (immediate_alert_cap): a 7.5 would stop every batch.
const SCALAR_BOUNDS: Record<string, NumberBound> = {
  digest_top_n: whole(1, 50), price_drop_min_pct: { min: 0, max: 100 }, alerts_max_per_user_day: whole(0, MAX_CONFIG_INTEGER),
};

function formatBound(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}
function describeBound(b: NumberBound): string {
  const kind = b.integer ? "un entero" : "un número";
  return b.aboveMin ? `${kind} mayor que ${formatBound(b.min)} y hasta ${formatBound(b.max)}` : `${kind} de ${formatBound(b.min)} a ${formatBound(b.max)}`;
}
function withinBound(value: unknown, b: NumberBound): boolean {
  return typeof value === "number" && Number.isFinite(value) && (!b.integer || Number.isInteger(value))
    && (b.aboveMin ? value > b.min : value >= b.min) && value <= b.max;
}
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function unknownKeysProblem(path: string, value: Record<string, unknown>, known: readonly string[]): string | null {
  const unknown = Object.keys(value).filter((k) => !known.includes(k));
  return unknown.length ? `${path} no usa ${unknown.join(", ")}; sus claves son ${known.join(", ")}.` : null;
}
/** The first field of `value` outside its bound, as a message. Missing fields keep the worker's default. */
function boundsProblem(path: string, value: Record<string, unknown>, bounds: Record<string, NumberBound>, nullable: readonly string[] = []): string | null {
  for (const [name, bound] of Object.entries(bounds)) {
    if (!Object.hasOwn(value, name) || (value[name] === null && nullable.includes(name))) continue;
    if (!withinBound(value[name], bound)) return `${path}.${name} tiene que ser ${describeBound(bound)}.`;
  }
  return null;
}

export const SCORE_WEIGHTS_ZERO_MESSAGE = "score_weights no puede tener todos los pesos en 0: cada aviso sacaría 0 y nivel bajo (sin la clave: 35, 25, 15, 10, 10 y 5).";
export const LEVEL_THRESHOLDS_ORDER_MESSAGE = "level_thresholds tiene que cumplir high > good > match (sin la clave: 85, 70 y 50).";
export const SCORE_GUARDS_ORDER_MESSAGE = "score_curves.guards.suspicious_pct no puede superar partial_pct (sin la clave: 50 y 65).";
export const RESCORE_HOUR_MESSAGE = "rescore.hour tiene que ser un horario HH:MM entre 00:00 y 23:59 (hora argentina).";
export const RESCORE_EVERY_HOURS_MESSAGE = "rescore.every_hours tiene que dividir 24: 1, 2, 3, 4, 6, 8, 12 o 24 horas.";
export const CONFIRM_SOURCES_MESSAGE = "comparables.confirm_sources tiene que ser una lista de ids de fuentes (texto).";

/** score_weights, level_thresholds, score_curves, comparables, rescore and the scalar keys; null for any other key. */
function scoringConfigProblem(key: string, value: unknown): string | null {
  if (Object.hasOwn(SCALAR_BOUNDS, key)) return withinBound(value, SCALAR_BOUNDS[key]) ? null : `${key} tiene que ser ${describeBound(SCALAR_BOUNDS[key])}.`;
  if (!["score_weights", "level_thresholds", "score_curves", "comparables", "rescore"].includes(key)) return null;
  if (!isPlainObject(value)) return `${key} tiene que ser un objeto.`;
  if (key === "score_weights") {
    const problem = unknownKeysProblem(key, value, Object.keys(SCORE_WEIGHT_BOUNDS)) ?? boundsProblem(key, value, SCORE_WEIGHT_BOUNDS);
    if (problem) return problem;
    const weights = { ...SCORE_WEIGHT_DEFAULTS, ...value } as Record<string, number>;
    return Object.values(weights).some((w) => w > 0) ? null : SCORE_WEIGHTS_ZERO_MESSAGE;
  }
  if (key === "level_thresholds") {
    const problem = unknownKeysProblem(key, value, Object.keys(LEVEL_THRESHOLD_BOUNDS)) ?? boundsProblem(key, value, LEVEL_THRESHOLD_BOUNDS);
    if (problem) return problem;
    const t = { ...LEVEL_THRESHOLD_DEFAULTS, ...value } as Record<string, number>;
    return t.high > t.good && t.good > t.match ? null : LEVEL_THRESHOLDS_ORDER_MESSAGE;
  }
  if (key === "score_curves") {
    const unknown = unknownKeysProblem(key, value, Object.keys(SCORE_CURVE_BOUNDS));
    if (unknown) return unknown;
    for (const [name, bounds] of Object.entries(SCORE_CURVE_BOUNDS)) {
      if (!Object.hasOwn(value, name)) continue;
      const curve = value[name], path = `${key}.${name}`;
      if (!isPlainObject(curve)) return `${path} tiene que ser un objeto.`;
      const problem = unknownKeysProblem(path, curve, Object.keys(bounds)) ?? boundsProblem(path, curve, bounds);
      if (problem) return problem;
    }
    const guards = { ...GUARD_DEFAULTS, ...configObject(value.guards) } as Record<string, number>;
    return guards.suspicious_pct <= guards.partial_pct ? null : SCORE_GUARDS_ORDER_MESSAGE;
  }
  if (key === "comparables") {
    // Other keys pass: the SQL reads more than these (confirm_sources).
    const problem = boundsProblem(key, value, COMPARABLES_BOUNDS, ["gone_max_age_days"]);
    if (problem) return problem;
    const sources = value.confirm_sources;
    return sources === undefined || (Array.isArray(sources) && sources.length <= 50 && sources.every((s) => typeof s === "string" && s.trim() !== "")) ? null : CONFIRM_SOURCES_MESSAGE;
  }
  const problem = unknownKeysProblem(key, value, ["days", "hour", "every_hours"]) ?? boundsProblem(key, value, RESCORE_BOUNDS);
  if (problem) return problem;
  if (Object.hasOwn(value, "every_hours") && !RESCORE_EVERY_HOURS.includes(value.every_hours as number)) return RESCORE_EVERY_HOURS_MESSAGE;
  return !Object.hasOwn(value, "hour") || clock.safeParse(value.hour).success ? null : RESCORE_HOUR_MESSAGE;
}

export function configObject(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function shape(value: unknown): string {
  return value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
}
/** Keys whose feature was removed: hidden in /admin/config and not editable (X-01 notes, Juan 02/11). */
export const RETIRED_CONFIG_KEYS: ReadonlySet<string> = new Set(["listing_tracking"]);
export function visibleConfigRows<T extends { key: string }>(rows: readonly T[]): T[] {
  return rows.filter((row) => !RETIRED_CONFIG_KEYS.has(row.key));
}
export function validateConfigChange(key: string, value: unknown, current: unknown): string | null {
  if (RETIRED_CONFIG_KEYS.has(key)) return "Esta clave ya no se usa y no se puede editar.";
  if (key === "commercial_pilot") return "Habilitá el piloto desde Cobros para iniciar las pruebas y aplicar límites juntos.";
  if (!z.json().safeParse(value).success) return "El valor debe ser JSON con números finitos.";
  if (value === null) return "El valor no puede ser null.";
  if (shape(current) !== shape(value)) return `El valor tiene que ser ${shape(current)}, como el actual.`;
  if (key === "pro_offer") {
    if (!AdminOfferInput.safeParse(value).success) return "La oferta requiere versión (hasta 80 caracteres) y ambos planes con importe entero entre 1 y 9.999.999.999, moneda ARS y 30 días (7 en el pase de 7 días).";
    const before = proOffer(current), after = proOffer(value);
    if (JSON.stringify([before.pass_30.amount, before.pass_7.amount, before.pro_monthly.amount]) !== JSON.stringify([after.pass_30.amount, after.pass_7.amount, after.pro_monthly.amount]) && before.version === after.version) {
      return "Cambiá la versión de la oferta al modificar los importes. Cada confirmación debe identificar su precio.";
    }
  }
  if (key === "plan_limits") {
    if (!AdminPlanLimitsInput.safeParse(value).success) return "Revisá los límites: cantidades enteras entre 0 y 2.147.483.647, resultados y zonas desde 1 (o sin tope), funciones true/false.";
    if (configObject(value).enforced !== configObject(current).enforced) return "La aplicación de límites se cambia desde Cobros, junto con el piloto comercial.";
  }
  if (key === "price_track") {
    // PAR-03: the smallest fall, in %, that counts as a drop (public.price_track_min_drop_pct).
    if (!z.object({ min_drop_pct: z.number().min(0).max(100) }).safeParse(value).success) {
      return "min_drop_pct tiene que ser un número entre 0 y 100.";
    }
  }
  if (key === "llm_limits" && !LlmLimitsInput.safeParse(value).success) {
    const guide = configObject(value).model_guide;
    return guide !== undefined && !ModelGuideLimitsInput.safeParse(guide).success
      ? MODEL_GUIDE_LIMITS_MESSAGE
      : "per_user_hour y email_only_per_user_hour son enteros de 0 o más.";
  }
  if (key === "model_guides" && !ModelGuidesConfigInput.safeParse(value).success) return MODEL_GUIDES_MESSAGE;
  if (key === "seller_classification" && !SellerClassificationInput.safeParse(value).success) return SELLER_CLASSIFICATION_MESSAGE;
  if (key === "dealer_margin" && !DealerMarginInput.safeParse(value).success) return DEALER_MARGIN_MESSAGE;
  if (key === "sell_intent" && !SellIntentConfigInput.safeParse(value).success) return SELL_INTENT_CONFIG_MESSAGE;
  if (key === "zone_notice" && !ZoneNoticeConfigInput.safeParse(value).success) return ZONE_NOTICE_CONFIG_MESSAGE;
  if (key === "trial_reserve" && !TrialReserveConfigInput.safeParse(value).success) return TRIAL_RESERVE_CONFIG_MESSAGE;
  // PAR-01: every block with source and as_of, valid ranges and scales (lib/cost-estimator.ts, the parser's own rules).
  if (key === "cost_estimator") return costEstimatorProblem(value);
  if (key === "risk") {
    // PAR-02: the «Antes de señar» switch and its official links (https only).
    const parsed = RiskConfigInput.safeParse(value);
    if (!parsed.success) return parsed.error.issues[0]?.message ?? "Revisá checklist_enabled y los links.";
  }
  if (key === "red_flags") {
    // PAR-02: every much_cheaper band must stay reachable (worker/intelligence/red_flags.py).
    const v = configObject(value);
    const pick = (name: string, fallback: number) => (name in v ? v[name] : fallback);
    const [low, verify, high] = [pick("much_cheaper_pct", 25), pick("much_cheaper_verify_pct", 35), pick("anticipo_pct", 50)];
    if (![low, verify, high].every((n) => typeof n === "number" && Number.isFinite(n)) || !((low as number) < (verify as number) && (verify as number) <= (high as number))) {
      return "much_cheaper_verify_pct tiene que ser un número mayor que much_cheaper_pct y menor o igual que anticipo_pct (sin la clave: 25, 35 y 50).";
    }
    // PAR-02 resto: the email's priority of flags (worker/intelligence/config.py flag_order).
    if ("order" in v && !RedFlagsOrderInput.safeParse(v.order).success) return RED_FLAGS_ORDER_MESSAGE;
  }
  if (key === "lifecycle_emails") {
    const parsed = AdminLifecycleInput.safeParse(value);
    if (!parsed.success) return parsed.error.issues[0]?.message ?? "Revisá los horarios, tipos y topes de emails.";
  }
  return scoringConfigProblem(key, value);
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
  if (key === "pro_offer") return ({ version: "Versión de la oferta", "pass_30.amount": "Particular: importe (ARS)", "pass_7.amount": "Particular 7 días: importe (ARS)", "pro_monthly.amount": "Pro: importe (ARS)" } as Record<string, string>)[path] ?? path;
  if (key === "plan_limits") {
    const [tier, field] = path.split(".");
    const planName = ({ free: "Prueba gratis", pass: "Particular", pro: "Pro" } as Record<string, string>)[tier];
    const fieldName = ({ max_profiles: "búsquedas activas", max_visible_results: "resultados por búsqueda", max_total_results: "resultados acumulados durante la prueba", immediate_alerts_per_day: "avisos inmediatos por día", max_locations: "zonas por búsqueda", threshold_alerts: "umbral de oportunidad", model_less_search: "búsqueda sin modelo", total_cost: "costo total estimado", seller_filter: "filtro estricto de vendedor", contact_email: "mensaje listo en el email", dealer_margin: "margen estimado para agencias", min_threshold_usd: "umbral mínimo por margen (USD)" } as Record<string, string>)[field];
    if (planName) return fieldName ? `${planName}: ${fieldName}` : planName + (field ? `: ${field}` : "");
  }
  if (key === "risk") {
    if (path === "checklist_enabled") return "Checklist «Antes de señar» visible";
    const [group, name, ...rest] = path.split(".");
    const linkName = ({ dnrpa: "informe de dominio (DNRPA)", patentes: "patentes", infracciones: "infracciones", vtv: "VTV", form_08: "formulario 08" } as Record<string, string>)[name];
    if (group === "links" && linkName) return `Link oficial: ${linkName}${rest.length ? ` (${rest.join(".")})` : ""}`;
    // PAR-02 resto: the duplicate signals and the photo hash.
    if (group === "photo_hash" && name === "enabled") return "Hash de fotos prendido (descarga imágenes)";
    if (group === "signals" && name) return `Señal ${name} (on, shadow u off)`;
  }
  if (key === "llm_limits") {
    const label = ({ per_user_hour: "Jobs por usuario y hora", email_only_per_user_hour: "Jobs por hora (cuentas solo email)", "model_guide.enabled": "Guías: generación con IA prendida", "model_guide.per_day": "Guías: borradores por día", "model_guide.per_month": "Guías: borradores por mes", "model_guide.queued_ttl_minutes": "Guías: minutos en cola", "model_guide.timeout_seconds": "Guías: segundos por borrador", "model_guide.max_questions_in_listing": "Guías: preguntas por aviso (hasta 3)" } as Record<string, string>)[path];
    if (label) return label;
  }
  if (key === "sell_intent") {
    return ({ ask: "Pregunta «¿Tenés que vender tu auto?» (bienvenida y ficha)", agencies_contact: "Casilla «agencias me contacten» y su línea en Privacidad (solo con OK de Juan)", since: "Inicio de la prueba (métricas)" } as Record<string, string>)[path] ?? path;
  }
  if (key === "zone_notice" && path === "enabled") return "Aviso de zona visible (resultados y modo asistido)";
  if (key === "trial_reserve") {
    return ({ enabled: "Reserva de la prueba para autos nuevos", backfill_max: "Máximo de resultados ya publicados" } as Record<string, string>)[path] ?? path;
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
