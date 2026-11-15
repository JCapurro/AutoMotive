/**
 * Admin «Experimentos»: one card per experiment (table admin_experiments, migration
 * 20261220120000) joined to the live state of its switch (app_config) and to the
 * history of changes of that key (admin_config_audit). Pure builder: no I/O.
 *
 * Results are entered by hand; nothing here measures anything.
 */

export type ExperimentStatus = "running" | "won" | "lost" | "inconclusive" | "paused";

export type ExperimentRow = {
  slug: string;
  title: string;
  config_key: string | null;
  hypothesis: string;
  metric: string;
  baseline_text: string | null;
  baseline_value: number | null;
  started_at: string | null;
  /** A calendar day, «2026-11-21». */
  review_at: string | null;
  status: ExperimentStatus;
  result_text: string | null;
  result_value: number | null;
  verdict_note: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ConfigRow = { key: string; value: unknown };
export type AuditRow = {
  id: number;
  target_type: string;
  target_key: string;
  actor_email: string | null;
  actor_id: string;
  before_value: unknown;
  after_value: unknown;
  created_at: string;
};

export const DECIDED: ExperimentStatus[] = ["won", "lost", "inconclusive"];
export const isDecided = (s: ExperimentStatus) => DECIDED.includes(s);

export const STATUS_LABEL: Record<ExperimentStatus, string> = {
  running: "En marcha",
  won: "Ganó",
  lost: "Perdió",
  inconclusive: "Sin conclusión",
  paused: "Pausado",
};

// ---------------------------------------------------------------------------
// Argentina has no daylight saving time: its day is UTC−3 all year.

const HOUR = 3_600_000;
const DAY = 86_400_000;
const ART_OFFSET = 3 * HOUR;

/** «2026-11-14»: the calendar day in Argentina at that instant. */
export function artDay(at: Date): string {
  return new Date(at.getTime() - ART_OFFSET).toISOString().slice(0, 10);
}

/** An instant as a `datetime-local` value in Argentina time, «2026-11-14T11:13». */
export function toArtInput(iso: string | null): string {
  if (!iso || !Number.isFinite(Date.parse(iso))) return "";
  return new Date(Date.parse(iso) - ART_OFFSET).toISOString().slice(0, 16);
}

/** The inverse of toArtInput: a `datetime-local` value typed in Argentina time as an ISO instant; null when empty or not a date. */
export function fromArtInput(value: string): string | null {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/.exec(value.trim());
  if (!m) return null;
  const at = Date.parse(`${m[1]}T${m[2]}:00Z`);
  return Number.isFinite(at) ? new Date(at + ART_OFFSET).toISOString() : null;
}

// ---------------------------------------------------------------------------
// When to measure

export type ReviewState =
  | { kind: "none"; label: string }
  | { kind: "upcoming"; days: number; label: string }
  | { kind: "due"; days: number; label: string };

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Days from today (Argentina) to the re-measure day: positive = still to come, 0 = today, negative = overdue. */
export function daysLeft(reviewAt: string | null, now: Date): number | null {
  if (!reviewAt || !/^\d{4}-\d{2}-\d{2}$/.test(reviewAt)) return null;
  const review = Date.parse(`${reviewAt}T00:00:00Z`);
  if (!Number.isFinite(review)) return null;
  return Math.round((review - Date.parse(`${artDay(now)}T00:00:00Z`)) / DAY);
}

/** «Listo para medir» from the re-measure day on; before it, «faltan N días». */
export function reviewState(reviewAt: string | null, now: Date): ReviewState {
  const days = daysLeft(reviewAt, now);
  if (days === null) return { kind: "none", label: "Sin fecha para medir" };
  if (days > 0) return { kind: "upcoming", days, label: `Faltan ${plural(days, "día", "días")}` };
  if (days === 0) return { kind: "due", days, label: "Listo para medir (desde hoy)" };
  return { kind: "due", days, label: `Listo para medir (hace ${plural(-days, "día", "días")})` };
}

// ---------------------------------------------------------------------------
// The switch and its history

export type SwitchState =
  | { kind: "none"; label: string }
  | { kind: "missing"; label: string }
  | { kind: "on" | "off"; label: string; detail: string | null }
  | { kind: "unknown"; label: string };

const isObject = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);

/** What the experiment's app_config key says right now: on or off, and the share when it has one. */
export function switchState(key: string | null, config: ConfigRow[]): SwitchState {
  if (!key) return { kind: "none", label: "Sin interruptor" };
  const row = config.find((c) => c.key === key);
  if (!row) return { kind: "missing", label: `La clave ${key} no existe en la configuración` };
  const value = row.value;
  if (!isObject(value) || typeof value.enabled !== "boolean") return { kind: "unknown", label: "Sin campo enabled: mirá la configuración" };
  const share = typeof value.share === "number" && Number.isFinite(value.share) ? value.share : null;
  const detail = value.enabled && share !== null ? `lo ve el ${share} % de los visitantes` : null;
  return value.enabled ? { kind: "on", label: "Prendido", detail } : { kind: "off", label: "Apagado", detail: null };
}

export type HistoryEntry = { id: number; at: string; who: string; text: string };

const short = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v) ?? "—");

/** One line for a change of an app_config key: «Se prendió», «Se apagó», or what else changed. */
export function describeChange(before: unknown, after: unknown): string {
  if (!isObject(before) || !isObject(after)) return "Cambió el valor";
  const lines: string[] = [];
  if (before.enabled !== after.enabled && typeof after.enabled === "boolean") lines.push(after.enabled ? "Se prendió" : "Se apagó");
  for (const k of Object.keys({ ...before, ...after })) {
    if (k === "enabled") continue;
    if (JSON.stringify(before[k]) !== JSON.stringify(after[k])) lines.push(`${k}: ${short(before[k])} → ${short(after[k])}`);
  }
  return lines.join(" · ") || "Se guardó sin cambios";
}

/** The changes of one config key, newest first. */
export function historyOf(key: string | null, audit: AuditRow[], limit = 8): HistoryEntry[] {
  if (!key) return [];
  return audit
    .filter((a) => a.target_type === "app_config" && a.target_key === key)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id)
    .slice(0, limit)
    .map((a) => ({ id: a.id, at: a.created_at, who: a.actor_email ?? a.actor_id, text: describeChange(a.before_value, a.after_value) }));
}

// ---------------------------------------------------------------------------
// The board

export type ExperimentCard = ExperimentRow & { review: ReviewState; switch: SwitchState; history: HistoryEntry[] };
export type ExperimentsBoard = { open: ExperimentCard[]; decided: ExperimentCard[]; due: number };

/**
 * Open ones first (running and due, the most overdue first; then running by
 * re-measure day, those without a day last; then paused), decided ones below,
 * the latest decision first.
 */
export function buildExperimentsBoard(rows: ExperimentRow[], config: ConfigRow[], audit: AuditRow[], now: Date): ExperimentsBoard {
  const cards: ExperimentCard[] = rows.map((r) => ({
    ...r,
    review: isDecided(r.status) ? { kind: "none", label: "Decidido" } : reviewState(r.review_at, now),
    switch: switchState(r.config_key, config),
    history: historyOf(r.config_key, audit),
  }));
  const rank = (c: ExperimentCard) => (c.status === "paused" ? 3 : c.review.kind === "due" ? 0 : c.review.kind === "upcoming" ? 1 : 2);
  const days = (c: ExperimentCard) => ("days" in c.review ? c.review.days : 0);
  const open = cards
    .filter((c) => !isDecided(c.status))
    .sort((a, b) => rank(a) - rank(b) || days(a) - days(b) || a.title.localeCompare(b.title, "es"));
  const decided = cards
    .filter((c) => isDecided(c.status))
    .sort((a, b) => Date.parse(b.decided_at ?? "") - Date.parse(a.decided_at ?? "") || a.title.localeCompare(b.title, "es"));
  return { open, decided, due: open.filter((c) => c.status === "running" && c.review.kind === "due").length };
}

/** A number typed by hand («48», «48,5»); null when empty or not a number. */
export function parseNumber(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

// ---------------------------------------------------------------------------
// «Hoy»: experiments that reached their re-measure day

export type DueExperimentRow = Pick<ExperimentRow, "slug" | "title" | "metric" | "review_at" | "status">;
export type DueExperimentItem = { title: string; detail: string; href: string; action: string };

/** One pending item per running experiment whose re-measure day has come, the most overdue first. */
export function dueExperimentItems(rows: DueExperimentRow[], now: Date): DueExperimentItem[] {
  return rows
    .filter((r) => r.status === "running")
    .map((r) => ({ r, days: daysLeft(r.review_at, now) }))
    .filter((x): x is { r: DueExperimentRow; days: number } => x.days !== null && x.days <= 0)
    .sort((a, b) => a.days - b.days || a.r.title.localeCompare(b.r.title, "es"))
    .map(({ r, days }) => ({
      title: `Experimento listo para medir: ${r.title}`,
      detail: `${days === 0 ? "Se puede medir desde hoy" : `Se puede medir desde hace ${plural(-days, "día", "días")}`}. Qué medir: ${r.metric}`,
      href: `/admin/experiments#${r.slug}`,
      action: "Medir y decidir",
    }));
}
