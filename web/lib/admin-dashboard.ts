import { z } from "zod";

import { type CostReview, costEstimatorReview, parseCostEstimator } from "@/lib/cost-estimator";
import { isoDayMonth } from "@/lib/format";

export const DASHBOARD_DAYS = [7, 30, 90] as const;
export type DashboardDays = (typeof DASHBOARD_DAYS)[number];
export type DashboardPeriod = { days: DashboardDays; start: string; end: string; previousStart: string; asOf: string };

const DAY_MS = 86_400_000;
const ARGENTINA_OFFSET_MS = -3 * 3_600_000;

/** Half-open windows of complete Argentina days; Argentina has no DST. */
export function getDashboardPeriod(raw?: string | string[], now = new Date()): DashboardPeriod {
  const days: DashboardDays = typeof raw === "string" && ["7", "30", "90"].includes(raw) ? Number(raw) as DashboardDays : 30;
  const end = Math.floor((now.getTime() + ARGENTINA_OFFSET_MS) / DAY_MS) * DAY_MS - ARGENTINA_OFFSET_MS;
  return { days, start: new Date(end - days * DAY_MS).toISOString(), end: new Date(end).toISOString(),
    previousStart: new Date(end - 2 * days * DAY_MS).toISOString(), asOf: now.toISOString() };
}

export function metricRate(numerator: number, denominator: number): number | null {
  return denominator > 0 ? numerator / denominator * 100 : null;
}

export function metricChange(current: number, previous: number): number | null {
  return previous > 0 ? (current - previous) / previous * 100 : null;
}

const count = z.number().int().nonnegative();
const amount = z.number().nonnegative();
const timestamp = z.iso.datetime({ offset: true });

export const dashboardMetricsSchema = z.object({
  signups: count, activationEligible: count, activatedWithin24h: count, activeUsers: count,
  searchesCreated: count, firstValueEligible: count, firstValueUnobserved: count, firstValueWithin24h: count,
  firstValueMedianHours: amount.nullable(), grossRevenue: amount, refunds: amount,
  particularSales: count, agencyPayments: count, firstPayingUsers: count,
}).refine((m) => m.activationEligible <= m.signups && m.activatedWithin24h <= m.activationEligible
  && m.firstValueEligible + m.firstValueUnobserved <= m.searchesCreated && m.firstValueWithin24h <= m.firstValueEligible
  && (m.firstValueMedianHours === null || m.firstValueMedianHours <= 24), "Invalid cohort counts");
export type DashboardMetrics = z.infer<typeof dashboardMetricsSchema>;

export const dashboardSnapshotSchema = z.object({
  asOf: timestamp, start: timestamp, end: timestamp, previousStart: timestamp, firstValueTrackingSince: timestamp,
  current: dashboardMetricsSchema, previous: dashboardMetricsSchema,
  daily: z.array(z.object({ day: z.iso.date(), signups: count, activeUsers: count,
    searchesCreated: count, grossRevenue: amount, refunds: amount })),
  currentState: z.object({ enabledSearches: count, searchesWithoutValue24h: count,
    pendingNotifications: count, failedNotifications: count, pendingCheckouts: count, checkoutSyncErrors: count,
    agencyMonthlyEquivalent: amount, authorizedRecurringMrr: amount }),
});
export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>;
export type DashboardDaily = DashboardSnapshot["daily"][number];
export type DashboardCurrentState = DashboardSnapshot["currentState"];

export const dashboardSourcesSchema = z.array(z.object({ id: z.string(), name: z.string(), enabled: z.boolean(),
  consecutive_failures: count, last_ok_at: timestamp.nullable(), last_run_at: timestamp.nullable(),
  last_run_status: z.string().nullable(), last_error: z.string().nullable(), runs_24h: count, failed_24h: count }));
export type DashboardSourceHealth = z.infer<typeof dashboardSourcesSchema>[number];
export const dashboardLlmSchema = z.array(z.object({ day: timestamp, provider: z.string(), kind: z.string(),
  jobs: count, failed: count, latency_p50_ms: amount.nullable(), latency_p95_ms: amount.nullable() }));
export type DashboardLlmHealth = z.infer<typeof dashboardLlmSchema>[number];
export type DashboardSection<T> = { data: T | null; error: string | null };
export type DashboardData = { period: DashboardPeriod; metrics: DashboardSection<DashboardSnapshot>;
  sources: DashboardSection<DashboardSourceHealth[]>; llm: DashboardSection<DashboardLlmHealth[]>;
  /** PAR-01: whether app_config.cost_estimator needs a review (null: not read). */
  costReview?: CostReviewState | null };

// ---------------------------------------------------------------------------
// PAR-01: the cost estimator's review notice (/admin and /admin/config)
// ---------------------------------------------------------------------------

export type CostReviewState = { status: CostReview; asOf: string | null; maxAgeDays: number | null; months: number[] };

const AR_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires", year: "numeric", month: "2-digit", day: "2-digit" });
const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

/** The review state of the raw app_config.cost_estimator value on Argentina's day of `now`. */
export function costReviewState(raw: unknown, now: Date = new Date()): CostReviewState {
  const cfg = parseCostEstimator(raw);
  const review = cfg?.blocks.review ?? null;
  return { status: costEstimatorReview(cfg, AR_DAY.format(now)), asOf: cfg?.as_of ?? null,
    maxAgeDays: review?.max_age_days ?? null, months: review?.months ?? [] };
}

/** The attention item, or null when nothing is due. */
export function costReviewItem(state: CostReviewState | null | undefined): { title: string; detail: string; href: string; action: string } | null {
  if (!state?.status) return null;
  const href = "/admin/config#cost_estimator", action = "Revisar parámetros";
  if (state.status === "stale" && state.asOf) {
    return { title: `Costo total: parámetros al ${isoDayMonth(state.asOf)}, más de ${state.maxAgeDays} días`, detail: "Revisá MRPA, aranceles, sellos y patentes y actualizá as_of.", href, action };
  }
  if (state.status === "due") {
    return { title: `Costo total: ${state.months.map((m) => MONTHS[m - 1]).join("/")}, revisar leyes impositivas y MRPA`, detail: `Parámetros al ${state.asOf ? isoDayMonth(state.asOf) : "—"}. Cuando los revises, actualizá as_of.`, href, action };
  }
  return { title: "Costo total: sin parámetros válidos", detail: "Falta cost_estimator, su as_of o su bloque review: la ficha, las tarjetas y los emails no muestran el costo total.", href, action };
}
