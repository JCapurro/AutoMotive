import "server-only";

import { requireAdmin } from "@/lib/admin";
import type { DemandRow, DemandRun } from "@/lib/admin-demand-data";
import { readAll } from "@/lib/admin-load";
import { createAdminClient } from "@/lib/supabase/admin";

/** What «Demanda insatisfecha» needs: the rows the worker's nightly job precomputed, read with the service role. */
export async function loadDemandInput(): Promise<{ rows: DemandRow[]; run: DemandRun | null }> {
  await requireAdmin();
  const db = createAdminClient();
  const [rows, run] = await Promise.all([
    readAll<DemandRow>((a, b) => db.from("admin_unmet_demand").select("*").order("search_profile_id").range(a, b)),
    db.from("admin_unmet_demand_run").select("*").maybeSingle(),
  ]);
  if (run.error) throw new Error(`admin read failed: ${run.error.message}`);
  return { rows, run: (run.data as DemandRun | null) ?? null };
}
