/**
 * Admin «Demanda insatisfecha»: searches with few or no results, what would
 * unlock them, and what the free plan's cap hides. The worker precomputes
 * admin_unmet_demand and admin_unmet_demand_run every night
 * (worker/pipeline/unmet_demand.py); this module only shapes those rows. Pure.
 */
import type { Level } from "@/lib/copy";

export type DemandCause = "zone" | "price" | "trim" | "year" | "none";

export type DemandRow = {
  search_profile_id: number;
  user_id: string;
  make: string | null;
  model: string | null;
  zone_label: string | null;
  result_count: number;
  market: number;
  market_in_zone: number;
  relaxed_zone: number;
  relaxed_price: number;
  relaxed_trim: number;
  relaxed_year: number;
  cause: DemandCause;
  computed_at: string;
};

export type DemandRun = {
  computed_at: string;
  duration_ms: number;
  searches: number;
  skipped_model_less: number;
  max_results: number;
  min_age_hours: number;
  cap_enforced: boolean;
  hidden_by_level: Partial<Record<Level, number>> | null;
  hidden_accounts: number;
};

export const CAUSE_LABEL: Record<DemandCause, string> = {
  zone: "Zona",
  price: "Precio",
  trim: "Versión",
  year: "Año",
  none: "Sin oferta",
};
export const CAUSE_HELP: Record<DemandCause, string> = {
  zone: "ampliando la zona aparecen más autos que con cualquier otro cambio",
  price: "subiendo el precio máximo",
  trim: "aceptando otras versiones",
  year: "aceptando otros años",
  none: "ningún cambio suelto suma autos: casi no hay oferta del modelo",
};
const CAUSES: DemandCause[] = ["zone", "price", "trim", "year", "none"];

/** More than this since the last run and the job is probably not running. */
export const STALE_HOURS = 36;
const LEVELS: Level[] = ["high", "good", "match", "low"];

export type CauseBucket = { key: DemandCause; label: string; value: number; note: string };
export type ModelZoneRow = {
  key: string;
  model: string;
  zone: string;
  searches: number;
  /** Active listings of the model seen in the last 30 days, and the ones inside the zone. */
  listings: number;
  listingsInZone: number;
  cause: DemandCause;
};
export type AffectedSearch = DemandRow & { vehicle: string; unlocks: number };
export type HiddenBlock = {
  /** The job has run at least once. */
  known: boolean;
  enforced: boolean;
  total: number;
  accounts: number;
  levels: { level: Level; value: number }[];
};
export type DemandDashboard = {
  computedAt: string | null;
  seconds: number | null;
  stale: boolean;
  /** Searches with a row, and those the job left out for having no model. */
  total: number;
  skippedModelLess: number;
  threshold: { maxResults: number; minAgeHours: number } | null;
  causes: CauseBucket[];
  modelZones: ModelZoneRow[];
  affected: AffectedSearch[];
  hidden: HiddenBlock;
};

const GAIN = { zone: "relaxed_zone", price: "relaxed_price", trim: "relaxed_trim", year: "relaxed_year" } as const;

export function vehicleOf(r: Pick<DemandRow, "make" | "model">): string {
  return [r.make, r.model].filter(Boolean).join(" ") || "Sin modelo";
}

/** Listings the search's main cause would add: the relaxed count minus what it already has. */
function unlocks(r: DemandRow): number {
  return r.cause === "none" ? 0 : Math.max(0, r[GAIN[r.cause]] - r.result_count);
}

export function buildDemandDashboard(
  rows: DemandRow[],
  run: DemandRun | null,
  now: Date,
  limits: { models?: number; searches?: number } = {},
): DemandDashboard {
  const computedAt = run?.computed_at ?? null;
  const stale = !computedAt || now.getTime() - Date.parse(computedAt) > STALE_HOURS * 3_600_000;

  const causes = CAUSES.map((key) => ({ key, label: CAUSE_LABEL[key], value: rows.filter((r) => r.cause === key).length, note: CAUSE_HELP[key] }))
    .sort((a, b) => b.value - a.value);

  const groups = new Map<string, DemandRow[]>();
  for (const r of rows) {
    const key = `${vehicleOf(r)}|${r.zone_label ?? ""}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  const modelZones = [...groups].map(([key, list]) => {
    const tally = new Map<DemandCause, number>();
    for (const r of list) tally.set(r.cause, (tally.get(r.cause) ?? 0) + 1);
    const cause = [...tally].sort((a, b) => b[1] - a[1] || CAUSES.indexOf(a[0]) - CAUSES.indexOf(b[0]))[0][0];
    return {
      key,
      model: vehicleOf(list[0]),
      zone: list[0].zone_label ?? "Sin zona",
      searches: list.length,
      listings: Math.max(...list.map((r) => r.market)),
      listingsInZone: Math.max(...list.map((r) => r.market_in_zone)),
      cause,
    };
  }).sort((a, b) => b.searches - a.searches || a.listingsInZone - b.listingsInZone || a.key.localeCompare(b.key))
    .slice(0, limits.models ?? 30);

  const affected = rows
    .map((r) => ({ ...r, vehicle: vehicleOf(r), unlocks: unlocks(r) }))
    .sort((a, b) => b.unlocks - a.unlocks || a.result_count - b.result_count || a.search_profile_id - b.search_profile_id)
    .slice(0, limits.searches ?? 100);

  const byLevel = run?.hidden_by_level ?? {};
  const levels = LEVELS.map((level) => ({ level, value: Number(byLevel[level] ?? 0) })).filter((l) => l.value > 0);
  const hidden: HiddenBlock = {
    known: Boolean(run),
    enforced: Boolean(run?.cap_enforced),
    total: levels.reduce((n, l) => n + l.value, 0),
    accounts: run?.hidden_accounts ?? 0,
    levels,
  };

  return {
    computedAt,
    seconds: run ? Math.round(run.duration_ms / 100) / 10 : null,
    stale,
    total: rows.length,
    skippedModelLess: run?.skipped_model_less ?? 0,
    threshold: run ? { maxResults: run.max_results, minAgeHours: Number(run.min_age_hours) } : null,
    causes,
    modelZones,
    affected,
    hidden,
  };
}
