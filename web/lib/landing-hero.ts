/**
 * The landing's hero «para tocar» (design/variants/landing/index.html,
 * migration 20261219120000_landing_hero): the search is built by tapping a
 * model, a budget and a zone, and the proof is what was flagged today.
 *
 * It is measured against the hero of today: while app_config.landing_hero is
 * on, `share` % of the anonymous visitors see it (variant b) and the rest the
 * old one (variant a). Pure helpers, shared by the proxy, the page, the
 * client form and the signup.
 */

export const HERO_COOKIE = "hero_bucket";
export const HERO_MAX_AGE = 60 * 60 * 24 * 90;

export type LandingHeroConfig = { enabled: boolean; share: number };

/** Off without the row or without `enabled: true`; a share out of 0..100 is 50. */
export function landingHeroConfig(raw: unknown): LandingHeroConfig {
  const value = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const share = Number(value.share);
  return { enabled: value.enabled === true, share: Number.isFinite(share) && share >= 0 && share <= 100 ? Math.floor(share) : 50 };
}

export type HeroVariant = "a" | "b";

/** The visitor's bucket (0..99) as the proxy keeps it in the cookie; null when absent or not one. */
export function heroBucket(value: string | undefined | null): number | null {
  if (!value || !/^\d{1,2}$/.test(value)) return null;
  return Number(value);
}

/**
 * Which hero a visit gets. The new one only with the switch on, for a visitor
 * with a bucket under the share; a signed-in user, a visitor without a bucket
 * (tracking refused, a prefetch) or an unreadable config get today's.
 */
export function heroVariant(cfg: LandingHeroConfig | null, bucket: string | undefined | null, signedIn: boolean): HeroVariant {
  if (!cfg?.enabled || signedIn) return "a";
  const n = heroBucket(bucket);
  return n !== null && n < cfg.share ? "b" : "a";
}

// ---------------------------------------------------------------------------
// What the hero shows (public.landing_feed).

export type FeedRow = {
  /** «Volkswagen Polo»: what «Avisame de uno así» searches for. */
  model: string;
  /** «Volkswagen Polo Comfortline 2018». */
  name: string;
  km: number;
  usd: number;
  median: number;
  n: number;
  where: string;
  source: string;
  seenAt: string;
};

export type LandingFeed = { flagged24h: number; rows: FeedRow[]; models: string[] };

const SOURCE_NAMES: Record<string, string> = {
  mercadolibre: "MercadoLibre",
  facebook: "Facebook Marketplace",
  kavak: "Kavak",
  deruedas: "DeRuedas",
  rosariogarage: "Rosario Garage",
  autocosmos: "Autocosmos",
  v6: "V6",
};

const text = (v: unknown) => (typeof v === "string" ? v.trim() : "");
const positive = (v: unknown) => (typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null);

/** «Malvinas Argentinas - Bs.As. G.B.A. Norte» and «Rosario, Santa Fe» as the town alone. */
export function feedPlace(raw: string): string {
  return raw.split(/\s+-\s+|,/)[0].trim().slice(0, 40);
}

/** Tolerant: a row missing anything it prints is dropped, never shown half empty. */
export function parseLandingFeed(raw: unknown): LandingFeed {
  const value = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const rows: FeedRow[] = [];
  for (const item of Array.isArray(value.rows) ? value.rows : []) {
    if (item === null || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    const make = text(r.make), model = text(r.model), seenAt = text(r.seen_at), source = text(r.source);
    const year = positive(r.year), km = positive(r.km), usd = positive(r.usd), median = positive(r.median), n = positive(r.n);
    if (!make || !model || !year || !km || !usd || !median || !n || median <= usd || !Number.isFinite(Date.parse(seenAt))) continue;
    rows.push({
      model: `${make} ${model}`,
      name: [make, model, text(r.trim), String(year)].filter(Boolean).join(" "),
      km, usd, median, n,
      where: feedPlace(text(r.where)),
      source: SOURCE_NAMES[source] ?? (source ? source[0].toUpperCase() + source.slice(1) : ""),
      seenAt,
    });
  }
  const models: string[] = [];
  for (const item of Array.isArray(value.models) ? value.models : []) {
    if (item === null || typeof item !== "object") continue;
    const make = text((item as Record<string, unknown>).make), model = text((item as Record<string, unknown>).model);
    if (make && model && !models.includes(`${make} ${model}`)) models.push(`${make} ${model}`);
  }
  const flagged = Number(value.flagged_24h);
  return { flagged24h: Number.isFinite(flagged) && flagged > 0 ? Math.floor(flagged) : 0, rows: rows.slice(0, 4), models: models.slice(0, 10) };
}

/** «hace 35 min», «hace 3 h»: how long ago a row was first seen. */
export function feedAgo(seenAt: string, now: Date = new Date()): string {
  const minutes = Math.max(1, Math.round((now.getTime() - Date.parse(seenAt)) / 60000));
  return minutes < 60 ? `hace ${minutes} min` : `hace ${Math.round(minutes / 60)} h`;
}

// ---------------------------------------------------------------------------
// The options and the text they build.

/**
 * The most searched models of the 30 days before 14/11/2026, by people who
 * saved a search: what the chips show until landing_feed has six of its own.
 */
export const HERO_MODELS = ["Volkswagen Golf", "Ford Focus", "Volkswagen Gol Trend", "Volkswagen Gol", "Toyota Corolla", "Chevrolet Cruze", "Volkswagen Polo", "Volkswagen Vento", "Ford Fiesta", "Honda Civic"];
/** The six most typed USD ceilings of the saved searches (median USD 12.500). */
export const HERO_BUDGETS = [7000, 10000, 12000, 14000, 16000, 25000];
/** «Mi ubicación» first, then the zones of the saved searches, most used first. */
export const HERE = "Mi ubicación";
export const NATIONWIDE = "Todo el país";
export const HERO_ZONES = ["AMBA", NATIONWIDE, "Córdoba", "Rosario", "La Plata"];

export function heroModels(feed: LandingFeed | null): string[] {
  return feed && feed.models.length >= 6 ? feed.models : HERO_MODELS;
}

/** A chip's label: the model without its make («Gol Trend»). */
export function modelLabel(model: string): string {
  return model.split(" ").slice(1).join(" ") || model;
}

const usd = (n: number) => `USD ${new Intl.NumberFormat("es-AR").format(n)}`;
export const HERE_TAIL = " cerca de mi ubicación";

/**
 * `base` is what the search says about the car (a chip's «Busco Volkswagen
 * Golf» or whatever was typed); budget and zone are appended after it, and
 * `shown` is that tail as it sits in the box right now.
 */
export type Builder = { model: string; other: boolean; base: string; budget: number; zone: string; shown: string };

export const EMPTY_BUILDER: Builder = { model: "", other: false, base: "", budget: 0, zone: "", shown: "" };

function tail(s: Pick<Builder, "budget" | "zone">, withHere = true): string {
  const zone = !s.zone ? "" : s.zone === HERE ? (withHere ? HERE_TAIL : "") : s.zone === NATIONWIDE ? " en todo el país" : ` en ${s.zone}`;
  return (s.budget ? ` hasta ${usd(s.budget)}` : "") + zone;
}

const write = (s: Builder): Builder => ({ ...s, shown: s.base.trim() ? tail(s) : "" });

/** What the box shows. */
export function builderText(s: Builder): string {
  return s.base.trim() ? s.base.trimEnd() + s.shown : "";
}

/**
 * What is sent to be read. «cerca de mi ubicación» stays out: the place is
 * not in our list of zones, and the coordinates travel on their own
 * (lib/landing-here.ts).
 */
export function builderPrompt(s: Builder): string {
  if (!s.base.trim()) return "";
  return s.shown ? s.base.trimEnd() + tail(s, false) : s.base.trim();
}

/** Budget and zone can be tapped once a model is chosen or «Otro» is. */
export const builderPicking = (s: Builder) => Boolean(s.model) || s.other;

/** A model chip: a second tap lets go of everything. Budget and zone survive a change of model. */
export function pickModel(s: Builder, model: string): Builder {
  if (s.model === model) return EMPTY_BUILDER;
  return write({ ...s, model, other: false, base: `Busco ${model}` });
}

/** «Otro»: the model is typed, budget and zone are still tapped. */
export function pickOther(s: Builder): Builder {
  return s.other ? EMPTY_BUILDER : { ...EMPTY_BUILDER, other: true };
}

export function pickBudget(s: Builder, budget: number): Builder {
  return write({ ...s, budget: s.budget === budget ? 0 : budget });
}

export function pickZone(s: Builder, zone: string): Builder {
  return write({ ...s, zone: s.zone === zone ? "" : zone });
}

/** Typing: the tail, while intact, stays the chips'; edited by hand, the text is the user's and the chips let go. */
export function typed(s: Builder, value: string): Builder {
  if (s.shown && value.endsWith(s.shown)) return { ...s, base: value.slice(0, -s.shown.length) };
  return s.shown ? { ...s, base: value, budget: 0, zone: "", shown: "" } : { ...s, base: value };
}

/** Leaving the box: budget and zone tapped before the model was typed join the text. */
export function blurred(s: Builder): Builder {
  return !s.shown && s.base.trim() && tail(s) ? write(s) : s;
}
