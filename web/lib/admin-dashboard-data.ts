import "server-only";

import { z } from "zod";

import { requireAdmin } from "@/lib/admin";
import { dashboardLlmSchema, dashboardSnapshotSchema, dashboardSourcesSchema, getDashboardPeriod,
  type DashboardData, type DashboardSection } from "@/lib/admin-dashboard";
import { createAdminClient } from "@/lib/supabase/admin";

type PageResult<T> = { data: T[] | null; error: unknown; count?: number | null };
class MissingMetricsMigration extends Error {}

function readFailure(label: string): { data: null; error: string } {
  return { data: null, error: `No se pudieron cargar ${label}. Volvé a intentar.` };
}

/** Read aggregated health rows without silently trusting the REST row limit. */
async function readPages<T>(read: (from: number, to: number) => PromiseLike<PageResult<T>>): Promise<T[]> {
  const rows: T[] = [];
  for (;;) {
    const result = await read(rows.length, rows.length + 499);
    if (result.error) throw new Error("dashboard_read_failed");
    if (!result.data) throw new Error("dashboard_missing_data");
    rows.push(...result.data);
    if (result.count != null ? rows.length >= result.count : result.data.length < 500) return rows;
    if (!result.data.length) throw new Error("dashboard_incomplete_page");
  }
}

async function section<T>(read: () => PromiseLike<unknown>, schema: z.ZodType<T>, label: string): Promise<DashboardSection<T>> {
  try {
    const result = schema.safeParse(await read());
    if (!result.success) throw new Error("dashboard_invalid_response");
    return { data: result.data, error: null };
  } catch (error) {
    // Do not expose SQL diagnostics, environment values or provider details.
    if (error instanceof MissingMetricsMigration) return { data: null,
      error: "Las métricas requieren la migración admin_decision_metrics en este entorno. Aplicala y reintentá." };
    return readFailure(label);
  }
}

export async function loadAdminDashboard(raw?: string | string[], now = new Date()): Promise<DashboardData> {
  await requireAdmin();
  const period = getDashboardPeriod(raw, now);
  let admin: ReturnType<typeof createAdminClient>;
  try {
    admin = createAdminClient();
  } catch {
    return { period, metrics: readFailure("las métricas"), sources: readFailure("las fuentes"), llm: readFailure("los trabajos de IA") };
  }
  const [metrics, sources, llm] = await Promise.all([
    section(async () => {
      const { data, error } = await admin.rpc("admin_decision_metrics", {
        p_start: period.start, p_end: period.end, p_as_of: period.asOf,
      });
      if (error?.code === "PGRST202" || error?.code === "42883") throw new MissingMetricsMigration();
      if (error) throw new Error("dashboard_metrics_failed");
      const snapshot = dashboardSnapshotSchema.parse(data);
      if (Date.parse(snapshot.start) !== Date.parse(period.start) || Date.parse(snapshot.end) !== Date.parse(period.end)
        || Date.parse(snapshot.previousStart) !== Date.parse(period.previousStart) || Date.parse(snapshot.asOf) !== Date.parse(period.asOf)
        || snapshot.daily.length !== period.days || snapshot.daily.some((day, i) =>
          day.day !== new Date(Date.parse(period.start) + i * 86_400_000).toISOString().slice(0, 10))) {
        throw new Error("dashboard_wrong_period");
      }
      return snapshot;
    }, dashboardSnapshotSchema, "las métricas"),
    section(() => readPages((from, to) => admin.from("admin_source_health")
      .select("id,name,enabled,consecutive_failures,last_ok_at,last_run_at,last_run_status,last_error,runs_24h,failed_24h", { count: "exact" })
      .order("id").range(from, to)), dashboardSourcesSchema, "las fuentes"),
    // The existing view groups jobs by UTC day, so query complete UTC dates
    // corresponding to the selected local calendar labels, and label this in UI.
    section(() => readPages((from, to) => admin.from("llm_job_stats")
      .select("day,provider,kind,jobs,failed,latency_p50_ms,latency_p95_ms", { count: "exact" })
      .gte("day", `${period.start.slice(0, 10)}T00:00:00Z`).lt("day", `${period.end.slice(0, 10)}T00:00:00Z`)
      .order("day", { ascending: false }).order("provider").order("kind").range(from, to)), dashboardLlmSchema, "los trabajos de IA"),
  ]);
  return { period, metrics, sources, llm };
}
