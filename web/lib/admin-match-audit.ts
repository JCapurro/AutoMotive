import { LEVELS, type Level } from "@/lib/copy";

/**
 * Auditoría semanal de matches (/admin/matches/audit). Puro: da forma a lo que
 * devuelven las RPC admin_match_review_queue / _stats y valida un veredicto.
 */

export const SAMPLE_SIZE = 60;
/** Debajo de esto, un porcentaje se marca como «muestra chica». */
export const SMALL_SAMPLE = 20;

export const VERDICTS = ["good", "fair", "bad"] as const;
export type Verdict = (typeof VERDICTS)[number];
export const VERDICT_LABEL: Record<Verdict, string> = { good: "Bien", fair: "Regular", bad: "Mal" };

export const REASONS = ["version", "zone", "price", "year", "not_a_car", "duplicate", "ended", "other"] as const;
export type Reason = (typeof REASONS)[number];
export const REASON_LABEL: Record<Reason, string> = {
  version: "Versión distinta",
  zone: "Zona",
  price: "Precio",
  year: "Año",
  not_a_car: "No es un auto",
  duplicate: "Repetido",
  ended: "Ya terminó",
  other: "Otra",
};

export function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && (VERDICTS as readonly string[]).includes(v);
}
export function isReason(v: unknown): v is Reason {
  return typeof v === "string" && (REASONS as readonly string[]).includes(v);
}

/** Regular y Mal piden al menos una razón; Bien no lleva razones. */
export function verdictProblem(verdict: Verdict, reasons: readonly Reason[]): string | null {
  if (verdict !== "good" && reasons.length === 0) return "Elegí al menos una razón.";
  return null;
}

export type ReviewItem = {
  id: number;
  matchId: number | null;
  level: Level;
  source: string;
  score: number | null;
  verdict: Verdict | null;
  reasons: Reason[];
  note: string;
  listing: {
    id: number; title: string; make: string | null; model: string | null; trim: string | null; year: number | null;
    priceUsd: number | null; price: number | null; currency: string | null; mileageKm: number | null;
    locationText: string | null; url: string | null; status: string | null;
  } | null;
  search: { id: number; name: string; filters: Record<string, unknown>; rawQuery: string | null; radiusKm: number | null } | null;
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

/** The queue RPC's jsonb → typed items (anything malformed is dropped, never thrown). */
export function parseQueue(json: unknown): ReviewItem[] {
  if (!Array.isArray(json)) return [];
  const items: ReviewItem[] = [];
  for (const raw of json) {
    const r = obj(raw);
    const id = r && num(r.id);
    if (!r || id == null) continue;
    const level = (LEVELS as string[]).includes(String(r.level)) ? (r.level as Level) : "low";
    const l = obj(r.listing);
    const s = obj(r.search);
    items.push({
      id,
      matchId: num(r.match_id),
      level,
      source: str(r.source) ?? "?",
      score: num(r.score),
      verdict: isVerdict(r.verdict) ? r.verdict : null,
      reasons: Array.isArray(r.reasons) ? r.reasons.filter(isReason) : [],
      note: str(r.note) ?? "",
      listing: l && num(l.id) != null
        ? {
            id: num(l.id)!, title: str(l.title) ?? "Sin título", make: str(l.make), model: str(l.model), trim: str(l.trim),
            year: num(l.year), priceUsd: num(l.price_usd), price: num(l.price), currency: str(l.currency),
            mileageKm: num(l.mileage_km), locationText: str(l.location_text), url: str(l.url), status: str(l.status),
          }
        : null,
      search: s && num(s.id) != null
        ? { id: num(s.id)!, name: str(s.name) ?? "", filters: obj(s.filters) ?? {}, rawQuery: str(s.raw_query), radiusKm: num(s.radius_km) }
        : null,
    });
  }
  return items;
}

/** «12 de 60»: how many are reviewed, and the first one still pending (or null). */
export function progress(items: readonly ReviewItem[]): { done: number; total: number; firstPending: number | null } {
  const idx = items.findIndex((i) => i.verdict === null);
  return { done: items.filter((i) => i.verdict !== null).length, total: items.length, firstPending: idx === -1 ? null : idx };
}

/** Next pending index after `from` (wrapping around), or null when everything is reviewed. */
export function nextPending(items: readonly ReviewItem[], from: number): number | null {
  for (let step = 1; step <= items.length; step++) {
    const i = (from + step) % items.length;
    if (items[i].verdict === null) return i;
  }
  return null;
}

/** The search's criteria as label/value lines, in plain Spanish. Empty values are skipped. */
export function criteriaLines(search: ReviewItem["search"]): { label: string; value: string }[] {
  if (!search) return [];
  const f = search.filters;
  const list = (v: unknown) => (Array.isArray(v) ? v.filter((x) => typeof x === "string" && x).join(", ") : "");
  const money = (n: unknown) => (typeof n === "number" ? n.toLocaleString("es-AR") : String(n));
  const lines: { label: string; value: string }[] = [];
  const add = (label: string, value: string | null | undefined) => {
    if (value) lines.push({ label, value });
  };
  add("Modelo", [f.make, f.model].filter(Boolean).join(" "));
  add("Versión", list(f.trims) + (f.trim_strict ? " (estricta)" : ""));
  add("Carrocería", list(f.body_types));
  const yearMin = f.year_min, yearMax = f.year_max;
  add("Años", yearMin || yearMax ? `${yearMin ?? "…"} a ${yearMax ?? "…"}` : Array.isArray(f.years) ? (f.years as unknown[]).join(", ") : "");
  add("Precio máximo", f.price_max ? `${f.currency ?? "USD"} ${money(f.price_max)}` : "");
  add("Kilómetros", f.km_min || f.km_max ? `${f.km_min ? money(f.km_min) : "0"} a ${f.km_max ? money(f.km_max) : "…"} km` : "");
  add("Caja", typeof f.transmission === "string" ? f.transmission : "");
  add("Combustible", typeof f.fuel === "string" ? f.fuel : list(f.fuel));
  add("Zona", [f.location_label, search.radiusKm ? `a ${Math.round(search.radiusKm)} km` : ""].filter(Boolean).join(" "));
  add("Vendedor", list(f.seller_types));
  add("Fuentes", list(f.sources));
  add("Texto original", search.rawQuery);
  return lines;
}

// ---------------------------------------------------------------- statistics

export type StatsRow = { week: string; level: Level; source: string; sampled: number; good: number; fair: number; bad: number };
export type ReasonRow = { week: string; reason: Reason; verdict: "fair" | "bad"; n: number };
export type Stats = { rows: StatsRow[]; reasons: ReasonRow[] };

export function parseStats(json: unknown): Stats {
  const o = obj(json) ?? {};
  const rows: StatsRow[] = [];
  for (const raw of Array.isArray(o.rows) ? o.rows : []) {
    const r = obj(raw);
    if (!r || !str(r.week) || !str(r.source)) continue;
    rows.push({
      week: String(r.week), level: (LEVELS as string[]).includes(String(r.level)) ? (r.level as Level) : "low", source: String(r.source),
      sampled: num(r.sampled) ?? 0, good: num(r.good) ?? 0, fair: num(r.fair) ?? 0, bad: num(r.bad) ?? 0,
    });
  }
  const reasons: ReasonRow[] = [];
  for (const raw of Array.isArray(o.reasons) ? o.reasons : []) {
    const r = obj(raw);
    if (!r || !isReason(r.reason) || (r.verdict !== "fair" && r.verdict !== "bad")) continue;
    reasons.push({ week: String(r.week), reason: r.reason, verdict: r.verdict, n: num(r.n) ?? 0 });
  }
  return { rows, reasons };
}

export type Tally = {
  key: string;
  sampled: number;
  /** Revisados: el tamaño de la muestra detrás de cada porcentaje. */
  reviewed: number;
  good: number;
  fair: number;
  bad: number;
  /** Bien / revisados, 0..1 (null sin revisados). */
  goodShare: number | null;
  /** (Bien + Regular) / revisados. */
  goodOrFairShare: number | null;
  smallSample: boolean;
};

function tally(key: string, rows: readonly StatsRow[]): Tally {
  const sum = (f: (r: StatsRow) => number) => rows.reduce((a, r) => a + f(r), 0);
  const good = sum((r) => r.good), fair = sum((r) => r.fair), bad = sum((r) => r.bad);
  const reviewed = good + fair + bad;
  return {
    key, sampled: sum((r) => r.sampled), reviewed, good, fair, bad,
    goodShare: reviewed ? good / reviewed : null,
    goodOrFairShare: reviewed ? (good + fair) / reviewed : null,
    smallSample: reviewed < SMALL_SAMPLE,
  };
}

function groupBy(rows: readonly StatsRow[], key: (r: StatsRow) => string): Map<string, StatsRow[]> {
  const m = new Map<string, StatsRow[]>();
  for (const r of rows) m.set(key(r), [...(m.get(key(r)) ?? []), r]);
  return m;
}

/** One tally per sample week, newest first. */
export function byWeek(rows: readonly StatsRow[]): Tally[] {
  return [...groupBy(rows, (r) => r.week)].map(([k, v]) => tally(k, v)).sort((a, b) => b.key.localeCompare(a.key));
}

/** One tally per level (high → low), over the given rows. */
export function byLevel(rows: readonly StatsRow[]): Tally[] {
  const g = groupBy(rows, (r) => r.level);
  return LEVELS.filter((l) => g.has(l)).map((l) => tally(l, g.get(l)!));
}

/** One tally per source, the biggest sample first. */
export function bySource(rows: readonly StatsRow[]): Tally[] {
  return [...groupBy(rows, (r) => r.source)].map(([k, v]) => tally(k, v)).sort((a, b) => b.reviewed - a.reviewed || a.key.localeCompare(b.key));
}

export function overall(rows: readonly StatsRow[]): Tally {
  return tally("all", rows);
}

/** Reasons given on Regular and Mal, most frequent first. */
export function topReasons(rows: readonly ReasonRow[], weeks?: readonly string[]): { reason: Reason; n: number; fair: number; bad: number }[] {
  const m = new Map<Reason, { fair: number; bad: number }>();
  for (const r of rows) {
    if (weeks && !weeks.includes(r.week)) continue;
    const cur = m.get(r.reason) ?? { fair: 0, bad: 0 };
    cur[r.verdict] += r.n;
    m.set(r.reason, cur);
  }
  return [...m]
    .map(([reason, c]) => ({ reason, n: c.fair + c.bad, ...c }))
    .sort((a, b) => b.n - a.n || REASONS.indexOf(a.reason) - REASONS.indexOf(b.reason));
}

/** «52 % (13 de 25)»: the share always carries its sample. «—» when nothing is reviewed. */
export function shareText(part: number, reviewed: number): string {
  if (!reviewed) return "—";
  return `${Math.round((part / reviewed) * 100)} % (${part} de ${reviewed})`;
}
