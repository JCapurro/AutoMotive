/**
 * Admin «Búsquedas» dashboard: what people look for (model, budget, zone),
 * which searches find nothing, and how their alerts are clicked. Pure builder.
 */
import { bodyTypesText } from "@/lib/copy";

export type SearchRow = {
  id: number;
  user_id: string;
  email: string | null;
  name: string;
  filters: unknown;
  enabled: boolean;
  notification_frequency: string | null;
  notify_min_level: string | null;
  channels: string[] | null;
  bootstrapped_at: string | null;
  rematch_requested_at: string | null;
  created_at: string;
  matches: number | null;
  high_matches: number | null;
  alerts: number | null;
  radius_km?: number | null;
};
export type SearchNotificationRow = { search_profile_id: number | null; opened_at: string | null; clicked_at: string | null };

export type SearchStats = SearchRow & { sent: number; opened: number; clicked: number; noResults: boolean };
export type Bucket = { label: string; value: number; note?: string; key?: string };

const DAY = 86_400_000;

type Filters = { make?: string; model?: string; body_types?: string[]; price_max?: number | string; currency?: string; year_min?: number | string; location_label?: string };

/** Without results: active, matched at least a day ago, and nothing found. */
export function hasNoResults(s: SearchRow, now: number): boolean {
  return s.enabled && Boolean(s.bootstrapped_at) && Date.parse(s.bootstrapped_at!) < now - DAY && !s.matches;
}

function counted(values: string[], top = 12): Bucket[] {
  const map = new Map<string, number>();
  for (const v of values) map.set(v, (map.get(v) ?? 0) + 1);
  return [...map].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value).slice(0, top);
}

/** Each value goes to the first bucket whose max (inclusive) it does not exceed. */
function inBuckets(values: number[], edges: { max: number; label: string }[], none: number, noneLabel: string): Bucket[] {
  const out = edges.map((e) => ({ label: e.label, value: 0 }));
  for (const v of values) {
    const i = edges.findIndex((e) => v <= e.max);
    out[i === -1 ? edges.length - 1 : i].value += 1;
  }
  return [...out, { label: noneLabel, value: none }].filter((b) => b.value);
}

const USD = [
  { max: 8_000, label: "Hasta USD 8.000" },
  { max: 12_000, label: "USD 8.000–12.000" },
  { max: 16_000, label: "USD 12.000–16.000" },
  { max: 20_000, label: "USD 16.000–20.000" },
  { max: 30_000, label: "USD 20.000–30.000" },
  { max: Infinity, label: "Más de USD 30.000" },
];
const ARS = [
  { max: 10_000_000, label: "Hasta $10 M" },
  { max: 15_000_000, label: "$10–15 M" },
  { max: 20_000_000, label: "$15–20 M" },
  { max: 30_000_000, label: "$20–30 M" },
  { max: Infinity, label: "Más de $30 M" },
];
const RADIUS = [
  { max: 30, label: "Hasta 30 km" },
  { max: 60, label: "31–60 km" },
  { max: 100, label: "61–100 km" },
  { max: 300, label: "101–300 km" },
  { max: Infinity, label: "Más de 300 km" },
];
const YEARS = [
  { max: 2009, label: "Antes de 2010" },
  { max: 2014, label: "2010–2014" },
  { max: 2019, label: "2015–2019" },
  { max: Infinity, label: "2020 o más nuevo" },
];

export function vehicleOf(filters: unknown): string {
  const f = (filters ?? {}) as Filters;
  if (f.make && f.model) return `${f.make} ${f.model}`;
  if (f.make) return `${f.make} (cualquier modelo)`;
  const body = bodyTypesText(Array.isArray(f.body_types) ? f.body_types : []);
  return body ? `Sin modelo: ${body}` : "Sin vehículo";
}

export function buildSearchesDashboard(searches: SearchRow[], notifications: SearchNotificationRow[], now: Date, periodDays: number | null) {
  const nowMs = now.getTime();
  const sent = new Map<number, { sent: number; opened: number; clicked: number }>();
  for (const n of notifications) {
    if (n.search_profile_id == null) continue;
    const s = sent.get(n.search_profile_id) ?? { sent: 0, opened: 0, clicked: 0 };
    s.sent += 1;
    if (n.opened_at || n.clicked_at) s.opened += 1;
    if (n.clicked_at) s.clicked += 1;
    sent.set(n.search_profile_id, s);
  }
  const all: SearchStats[] = searches.map((s) => ({ ...s, ...(sent.get(s.id) ?? { sent: 0, opened: 0, clicked: 0 }), noResults: hasNoResults(s, nowMs) }));
  const since = periodDays ? nowMs - periodDays * DAY : -Infinity;
  const inPeriod = all.filter((s) => Date.parse(s.created_at) >= since);
  const active = all.filter((s) => s.enabled);
  const f = (s: SearchRow) => (s.filters ?? {}) as Filters;

  const prices = (cur: "USD" | "ARS") =>
    inPeriod.filter((s) => f(s).currency === cur && f(s).price_max).map((s) => Number(f(s).price_max)).filter(Number.isFinite);
  const noPrice = inPeriod.filter((s) => !f(s).price_max).length;
  const radii = inPeriod.map((s) => s.radius_km).filter((r): r is number => typeof r === "number");
  const years = inPeriod.map((s) => Number(f(s).year_min)).filter((y) => Number.isFinite(y) && y > 1900);

  // Models: how many searches, and how many of the active ones find nothing.
  const models = new Map<string, { value: number; zero: number; matches: number }>();
  for (const s of inPeriod) {
    const key = vehicleOf(s.filters);
    const m = models.get(key) ?? { value: 0, zero: 0, matches: 0 };
    m.value += 1;
    if (s.noResults) m.zero += 1;
    m.matches += s.matches ?? 0;
    models.set(key, m);
  }
  const topModels: Bucket[] = [...models]
    .sort((a, b) => b[1].value - a[1].value)
    .slice(0, 15)
    .map(([label, m]) => ({ label, value: m.value, note: m.zero ? `${m.zero} sin resultados` : `${Math.round(m.matches / m.value)} matches prom.` }));

  const sentTotal = inPeriod.reduce((a, s) => a + s.sent, 0);
  const clickedTotal = inPeriod.reduce((a, s) => a + s.clicked, 0);
  const openedTotal = inPeriod.reduce((a, s) => a + s.opened, 0);
  const matchCounts = inPeriod.filter((s) => s.bootstrapped_at).map((s) => s.matches ?? 0).sort((a, b) => a - b);
  const median = matchCounts.length ? matchCounts[Math.floor(matchCounts.length / 2)] : 0;

  return {
    all,
    inPeriod,
    kpis: {
      total: all.length,
      active: active.length,
      created: inPeriod.length,
      users: new Set(inPeriod.map((s) => s.user_id)).size,
      noResults: inPeriod.filter((s) => s.noResults).length,
      activeInPeriod: inPeriod.filter((s) => s.enabled).length,
      pending: active.filter((s) => !s.bootstrapped_at || s.rematch_requested_at).length,
      medianMatches: median,
      sent: sentTotal,
      openRate: sentTotal ? Math.round((openedTotal / sentTotal) * 100) : 0,
      clickRate: sentTotal ? Math.round((clickedTotal / sentTotal) * 100) : 0,
    },
    topModels,
    makes: counted(inPeriod.map((s) => f(s).make ?? "Sin marca"), 10),
    usd: inBuckets(prices("USD"), USD, 0, ""),
    ars: inBuckets(prices("ARS"), ARS, 0, ""),
    noPrice,
    zones: counted(inPeriod.map((s) => f(s).location_label ?? "Sin zona"), 10),
    radius: inBuckets(radii, RADIUS, inPeriod.length - radii.length, "Todo el país"),
    years: inBuckets(years, YEARS, inPeriod.length - years.length, "Sin año mínimo"),
    frequency: counted(inPeriod.map((s) => (s.notification_frequency === "immediate" ? "Inmediata" : "Diaria"))),
  };
}
