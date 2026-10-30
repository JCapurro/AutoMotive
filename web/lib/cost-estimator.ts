/**
 * PAR-01: the estimated total cost of buying a listing (price, DNRPA fee,
 * stamp tax, forms and the annual patente), as a range
 * (docs/superpowers/specs/2026-10-30-par01-costo-total-design.md).
 *
 * The twin of worker/intelligence/cost_estimator.py: the same formulas in the
 * same order, so both sides produce the same IEEE doubles, checked by the
 * shared golden vectors (worker/tests/fixtures/cost_estimator/golden.json).
 * No number lives here: every figure comes from app_config.cost_estimator.
 * The tolerant parser drops an invalid block (its terms are told as missing);
 * the strict validator (costEstimatorProblem, /admin/config) rejects it with
 * the first error. Pure: the buyer's jurisdiction is resolved by
 * lib/buyer-jurisdiction.ts (server-only, it loads the localities) and passed in.
 */
import { z } from "zod";

import { COST_ESTIMATE } from "@/lib/copy";
import { ceilTo, floorTo, formatRange } from "@/lib/format";
import { publishedIsPartial } from "@/lib/price";
import { effectiveSeller } from "@/lib/seller";

export type Jurisdiction = "caba" | "ba" | "rest";
export const JURISDICTIONS: Jurisdiction[] = ["caba", "ba", "rest"];
export type TermCode = "arancel" | "sellos" | "formularios" | "patente";
/** The terms of the total, in the order of the header's "(sin …)". */
export const TERMS: TermCode[] = ["arancel", "sellos", "formularios", "patente"];
export type MissingReason = "params" | "base" | "no_zone" | "no_year" | "pre_min_year" | "no_fx";
export type Seller = "private" | "dealer" | null;

export const BLOCKS = [
  "review", "fx", "buyer_zone", "vf_from_price_k", "transfer_base", "mrpa_ars", "dnrpa",
  "fixed_ars.form_08", "fixed_ars.form_12", "domain_report",
  "stamp_tax_pct.caba", "stamp_tax_pct.ba", "stamp_tax_pct.rest",
  "patente.caba", "patente.ba", "patente.rest", "patente.values_year", "gestoria",
] as const;
export type BlockName = (typeof BLOCKS)[number];

// ---------------------------------------------------------------------------
// Block schemas: the tolerant parser and the strict validator share them
// ---------------------------------------------------------------------------

const DATE = /^\d{4}-\d{2}-\d{2}$/;
export function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !DATE.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const day = new Date(Date.UTC(y, m - 1, d));
  return day.getUTCFullYear() === y && day.getUTCMonth() === m - 1 && day.getUTCDate() === d;
}

const num = z.number("tiene que ser un número");
const nonNeg = num.min(0, "no puede ser negativo");
const pct = num.min(0, "no puede ser negativo").max(100, "un porcentaje no puede superar 100");
const whole = z.number("tiene que ser un número").int("tiene que ser un entero");

const range = (isPct = false) =>
  z
    .object({ min: isPct ? pct : nonNeg, max: isPct ? pct : nonNeg })
    .passthrough()
    .refine((v) => v.min <= v.max, "min tiene que ser menor o igual que max");

const common = {
  source: z.string("falta source").refine((s) => s.trim().length > 0, "source no puede estar vacío"),
  as_of: z.string("falta as_of").refine(isIsoDate, "as_of tiene que ser una fecha AAAA-MM-DD"),
};
const block = <T extends z.ZodRawShape>(shape: T) => z.object({ ...common, ...shape }).passthrough();

const brackets = z
  .array(z.object({ from: num, fixed: nonNeg, pct }).passthrough(), "tiene que ser una lista de tramos")
  .min(1, "tiene que tener al menos un tramo")
  .refine((b) => b[0]?.from === 0, 'el primer "from" tiene que ser 0')
  .refine((b) => b.every((r, i) => i === 0 || b[i - 1].from < r.from), 'los "from" deben crecer');

const bands = z
  .array(z.object({ pct, vf_upto: num.nullable() }).passthrough(), "tiene que ser una lista de bandas")
  .min(1, "tiene que tener al menos una banda")
  .refine((b) => b[b.length - 1]?.vf_upto === null, 'el último "vf_upto" tiene que ser null')
  .refine((b) => b.slice(0, -1).every((r) => r.vf_upto !== null && r.vf_upto > 0), 'los "vf_upto" (salvo el último) tienen que ser números positivos')
  .refine((b) => b.slice(0, -1).every((r, i, a) => i === 0 || (a[i - 1].vf_upto as number) < (r.vf_upto as number)), 'los "vf_upto" deben crecer');

const stamp = block({ private: range(true), dealer: range(true) });

export const BLOCK_SCHEMAS: Record<Exclude<BlockName, "patente.values_year">, z.ZodType> = {
  review: block({
    max_age_days: whole.min(1, "tiene que ser mayor que 0"),
    months: z.array(whole.min(1, "los meses van de 1 a 12").max(12, "los meses van de 1 a 12"), "tiene que ser una lista de meses").min(1, "tiene que tener al menos un mes"),
  }),
  fx: block({ max_age_days: whole.min(1, "tiene que ser mayor que 0") }),
  buyer_zone: block({ max_locality_km: num.gt(0, "tiene que ser mayor que 0") }),
  vf_from_price_k: block({ min: num.gt(0, "tiene que ser mayor que 0"), max: num.max(1, "no puede superar 1 (base = precio)") }).refine(
    (v) => v.min <= v.max,
    "min tiene que ser menor o igual que max",
  ),
  transfer_base: block({ value: z.string("falta value").refine((s) => s.trim().length > 0, "value no puede estar vacío") }),
  mrpa_ars: block({ min: nonNeg, max: nonNeg }).refine((v) => v.min <= v.max, "min tiene que ser menor o igual que max"),
  dnrpa: block({ pct: range(true), dealer_pct: range(true), min_mrpa: nonNeg }),
  "fixed_ars.form_08": block({ min: nonNeg, max: nonNeg }).refine((v) => v.min <= v.max, "min tiene que ser menor o igual que max"),
  "fixed_ars.form_12": block({ min: nonNeg, max: nonNeg }).refine((v) => v.min <= v.max, "min tiene que ser menor o igual que max"),
  domain_report: block({ mrpa: nonNeg, in_total: z.literal(false, "in_total tiene que ser false: va fuera del total") }),
  "stamp_tax_pct.caba": stamp,
  "stamp_tax_pct.ba": stamp,
  "stamp_tax_pct.rest": stamp,
  "patente.caba": block({
    brackets,
    cap_pct_of_vf: pct,
    min_ars: nonNeg,
    pickup_flat_pct: pct,
    pickup_body_types: z.array(z.string(), "tiene que ser una lista de carrocerías"),
    subte_factor: range(),
    old_model_min_zero: z.object({ age_years: whole.min(0, "no puede ser negativo") }, "falta old_model_min_zero").passthrough(),
  }),
  "patente.ba": block({ brackets, ipc_factor: range(), discount_pct: pct, min_model_year: whole }),
  "patente.rest": block({
    min_pct: pct,
    old_model: z.object({ max_year: whole, min_pct: pct }, "falta old_model").passthrough(),
    max_pct_bands: bands,
  }),
  gestoria: block({
    in_total: z.literal(false, "in_total tiene que ser false: va fuera del total"),
    official_value: z.null("official_value tiene que ser null: no hay tarifa oficial"),
  }),
};

function at(raw: unknown, path: string): unknown {
  let node: unknown = raw;
  for (const key of path.split(".")) {
    if (!node || typeof node !== "object" || Array.isArray(node)) return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return node;
}

type Range = { min: number; max: number };
type Bracket = { from: number; fixed: number; pct: number };
type Blocks = {
  review: { max_age_days: number; months: number[] } | null;
  fx: { max_age_days: number } | null;
  buyer_zone: { max_locality_km: number } | null;
  vf_from_price_k: Range | null;
  transfer_base: { value: string } | null;
  mrpa_ars: Range | null;
  dnrpa: { pct: Range; dealer_pct: Range; min_mrpa: number } | null;
  "fixed_ars.form_08": Range | null;
  "fixed_ars.form_12": Range | null;
  domain_report: { mrpa: number } | null;
  "stamp_tax_pct.caba": { private: Range; dealer: Range } | null;
  "stamp_tax_pct.ba": { private: Range; dealer: Range } | null;
  "stamp_tax_pct.rest": { private: Range; dealer: Range } | null;
  "patente.caba": {
    brackets: Bracket[]; cap_pct_of_vf: number; min_ars: number; pickup_flat_pct: number;
    pickup_body_types: string[]; subte_factor: Range; old_model_min_zero: { age_years: number };
  } | null;
  "patente.ba": { brackets: Bracket[]; ipc_factor: Range; discount_pct: number; min_model_year: number } | null;
  "patente.rest": { min_pct: number; old_model: { max_year: number; min_pct: number }; max_pct_bands: { pct: number; vf_upto: number | null }[] } | null;
  "patente.values_year": number | null;
  gestoria: Record<string, unknown> | null;
};
export type CostConfig = { as_of: string; blocks: Blocks; raw: Record<string, unknown> };

/** Tolerant: {as_of, blocks}; null without a valid root as_of. Never throws, never fills a default. */
export function parseCostEstimator(raw: unknown): CostConfig | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const root = raw as Record<string, unknown>;
  if (!isIsoDate(root.as_of)) return null;
  const blocks = {} as Record<BlockName, unknown>;
  for (const name of BLOCKS) {
    const value = at(raw, name);
    if (name === "patente.values_year") blocks[name] = Number.isInteger(value) ? value : null;
    else blocks[name] = BLOCK_SCHEMAS[name].safeParse(value).success ? value : null;
  }
  return { as_of: root.as_of, blocks: blocks as Blocks, raw: root };
}

/** Strict, for /admin/config: the first problem in Spanish, or null. */
export function costEstimatorProblem(raw: unknown): string | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return "cost_estimator: tiene que ser un objeto.";
  if (!isIsoDate((raw as Record<string, unknown>).as_of)) return "cost_estimator.as_of: tiene que ser una fecha AAAA-MM-DD (la de tu última revisión).";
  for (const name of BLOCKS) {
    const value = at(raw, name);
    if (name === "patente.values_year") {
      if (!Number.isInteger(value)) return "cost_estimator.patente.values_year: tiene que ser un año entero.";
      continue;
    }
    if (value === undefined) return `cost_estimator.${name}: falta el bloque.`;
    const parsed = BLOCK_SCHEMAS[name].safeParse(value);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      const where = [name, ...(issue?.path ?? []).map(String)].join(".");
      return `cost_estimator.${where}: ${issue?.message ?? "valor inválido"}.`;
    }
  }
  return null;
}

/** The same rules as a zod schema, for callers that compose schemas. */
export const CostEstimatorInput = z.unknown().superRefine((value, context) => {
  const problem = costEstimatorProblem(value);
  if (problem) context.addIssue({ code: "custom", message: problem });
});

// ---------------------------------------------------------------------------
// Zones and the calculator's input
// ---------------------------------------------------------------------------

export type Zone = { lat: number | null; lon: number | null; label: string | null };
export type ZoneSource = {
  lat: number | null | undefined;
  lon: number | null | undefined;
  label?: string | null;
  extra_locations?: unknown;
};

function finite(x: unknown): number | null {
  return typeof x === "number" && Number.isFinite(x) ? x : null;
}

/** A search's zones: its origin and each filters.extra_locations[]. No origin, none of it. */
export function searchZones(search: ZoneSource | null | undefined): Zone[] {
  if (!search) return [];
  const zones: Zone[] = [];
  if (search.lat != null && search.lon != null) zones.push({ lat: finite(search.lat), lon: finite(search.lon), label: search.label ?? null });
  for (const z of Array.isArray(search.extra_locations) ? search.extra_locations : []) {
    if (z && typeof z === "object" && !Array.isArray(z)) {
      const e = z as Record<string, unknown>;
      zones.push({ lat: finite(e.lat), lon: finite(e.lon), label: typeof e.label === "string" ? e.label : null });
    }
  }
  return zones;
}

export type FxQuote = { rate: number; kind: string | null; date: string };
export type CostRow = {
  price: number | null;
  currency: string | null;
  price_usd: number | null;
  price_partial?: boolean | null;
  description_facts: unknown;
  seller_type?: string | null;
  dealer_inferred?: boolean | null;
  year: number | null;
  body_type: string | null;
};
export type CostListing = {
  price: number;
  currency: "ARS" | "USD";
  fx_rate: number | null;
  cash: boolean;
  year: number | null;
  body_type: string | null;
};
export type CostInput = { listing: CostListing; jurisdiction: Jurisdiction[] | null; seller: Seller; fx_latest: FxQuote | null };
export type JurisdictionResolver = (zones: Zone[], cfg: CostConfig | null) => Jurisdiction[] | null;

function daysBetween(from: string, to: string): number {
  const ms = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));
  return Math.round((ms(to) - ms(from)) / 86_400_000);
}

/**
 * The calculator's input from a listings row, or null when there is nothing
 * to estimate: no config, no price, a partial price (publishedIsPartial, the
 * worker's published_partial) or an unknown currency. An ARS listing's dollar
 * is the one its price_usd was computed with (price / price_usd); a USD
 * listing's is the latest stored quote, only while at most fx.max_age_days old.
 * `today` is "YYYY-MM-DD" (Argentina).
 */
export function buildCostInput(
  row: CostRow,
  zones: Zone[],
  fxLatest: FxQuote | null,
  cfg: CostConfig | null,
  today: string,
  resolve: JurisdictionResolver,
): CostInput | null {
  if (!cfg) return null;
  const price = finite(row.price);
  if (price == null || price <= 0 || publishedIsPartial({ description_facts: row.description_facts, price_partial: row.price_partial })) return null;
  if (row.currency !== "ARS" && row.currency !== "USD") return null;
  const usd = finite(row.price_usd);
  const facts = row.description_facts && typeof row.description_facts === "object" ? (row.description_facts as Record<string, unknown>) : {};
  const check = facts.price_check && typeof facts.price_check === "object" ? (facts.price_check as Record<string, unknown>) : {};
  const listing: CostListing = {
    price,
    currency: row.currency,
    fx_rate: row.currency === "ARS" && usd && usd > 0 ? price / usd : null,
    cash: check.effective_kind === "cash",
    year: Number.isInteger(row.year) ? row.year : null,
    body_type: row.body_type || null,
  };
  let fx: FxQuote | null = null;
  const fxCfg = cfg.blocks.fx;
  if (row.currency === "USD" && fxLatest && fxCfg) {
    const rate = finite(fxLatest.rate);
    if (rate && rate > 0 && isIsoDate(fxLatest.date) && daysBetween(fxLatest.date, today) <= fxCfg.max_age_days) {
      fx = { rate, kind: fxLatest.kind, date: fxLatest.date };
    }
  }
  return { listing, jurisdiction: resolve(zones, cfg), seller: effectiveSeller(row), fx_latest: fx };
}

// ---------------------------------------------------------------------------
// The calculator
// ---------------------------------------------------------------------------

export type Term = { code: TermCode; min: number; max: number; blocks: string[] };
export type Extra = { code: "domain_report" | "gestoria"; min: number | null; max: number | null; blocks: string[] };
export type Missing = { code: TermCode | "fx"; reason: MissingReason };
export type Estimate = {
  p_ars: number | null;
  p_orig: { amount: number; currency: "ARS" | "USD" };
  price_label: "cash" | "published";
  rate: { value: number; kind: string | null; date: string | null } | null;
  terms: Term[];
  extras: Extra[];
  missing: Missing[];
  total_ars: Range | null;
  total_usd: Range | null;
  jurisdiction: Jurisdiction[] | null;
  seller: Seller;
  as_of: string;
};

type Result = { ok: true; min: number; max: number; blocks: string[] } | { ok: false; reason: MissingReason };

function sellerRange<K extends string>(block: Record<K, Range>, seller: Seller, priv: K, dealer: K): [number, number] {
  const pairs = seller === "private" ? [block[priv]] : seller === "dealer" ? [block[dealer]] : [block[priv], block[dealer]];
  return [Math.min(...pairs.map((p) => p.min)), Math.max(...pairs.map((p) => p.max))];
}

function scale(brackets: Bracket[], vf: number): number {
  const rows = brackets.filter((r) => r.from <= vf);
  const row = rows[rows.length - 1];
  return row.fixed + ((vf - row.from) * row.pct) / 100;
}

function arancel(p: number, seller: Seller, b: Blocks): Result {
  const { dnrpa, mrpa_ars: mrpa, transfer_base: base } = b;
  if (!dnrpa || !mrpa || !base) return { ok: false, reason: "params" };
  if (base.value !== "price") return { ok: false, reason: "base" };
  const [lo, hi] = sellerRange(dnrpa, seller, "pct", "dealer_pct");
  return {
    ok: true,
    min: Math.max((p * lo) / 100, dnrpa.min_mrpa * mrpa.min),
    max: Math.max((p * hi) / 100, dnrpa.min_mrpa * mrpa.max),
    blocks: ["dnrpa", "mrpa_ars", "transfer_base"],
  };
}

function sellos(p: number, jurisdiction: Jurisdiction[] | null, seller: Seller, b: Blocks): Result {
  const base = b.transfer_base;
  if (!base) return { ok: false, reason: "params" };
  if (base.value !== "price") return { ok: false, reason: "base" };
  if (!jurisdiction?.length) return { ok: false, reason: "no_zone" };
  const names = jurisdiction.map((j) => `stamp_tax_pct.${j}` as const);
  if (names.some((n) => !b[n])) return { ok: false, reason: "params" };
  const ranges = names.map((n) => sellerRange(b[n]!, seller, "private", "dealer"));
  return {
    ok: true,
    min: Math.min(...ranges.map(([lo]) => (p * lo) / 100)),
    max: Math.max(...ranges.map(([, hi]) => (p * hi) / 100)),
    blocks: names,
  };
}

function formularios(b: Blocks): Result {
  const f08 = b["fixed_ars.form_08"], f12 = b["fixed_ars.form_12"];
  if (!f08 || !f12) return { ok: false, reason: "params" };
  return { ok: true, min: f08.min + f12.min, max: f08.max + f12.max, blocks: ["fixed_ars.form_08", "fixed_ars.form_12"] };
}

function patenteCaba(c: NonNullable<Blocks["patente.caba"]>, vfLo: number, vfHi: number, year: number, valuesYear: number, bodyType: string | null): [number, number] {
  // Inciso a) the scale with its cap; b) the pick-up's flat rate. No body
  // type: the union of both. The minimum and the Subte factor apply to both.
  const incisos = bodyType != null && c.pickup_body_types.includes(bodyType) ? ["b"] : bodyType == null ? ["a", "b"] : ["a"];
  const floor = year <= valuesYear - c.old_model_min_zero.age_years ? 0 : c.min_ars;
  const t = (vf: number, inciso: string, factor: number) => {
    const base = inciso === "a" ? Math.min(scale(c.brackets, vf), (vf * c.cap_pct_of_vf) / 100) : (vf * c.pickup_flat_pct) / 100;
    return Math.max(base, floor) * factor;
  };
  return [
    Math.min(...incisos.map((i) => t(vfLo, i, c.subte_factor.min))),
    Math.max(...incisos.map((i) => t(vfHi, i, c.subte_factor.max))),
  ];
}

function patenteBa(c: NonNullable<Blocks["patente.ba"]>, vfLo: number, vfHi: number): [number, number] {
  return [
    (scale(c.brackets, vfLo) * c.ipc_factor.min * (100 - c.discount_pct)) / 100,
    (scale(c.brackets, vfHi) * c.ipc_factor.max * (100 - c.discount_pct)) / 100,
  ];
}

function patenteRest(c: NonNullable<Blocks["patente.rest"]>, vfLo: number, vfHi: number, year: number): [number, number] {
  const loPct = year <= c.old_model.max_year ? c.old_model.min_pct : c.min_pct;
  const band = c.max_pct_bands.find((r) => r.vf_upto === null || vfHi <= r.vf_upto)!;
  return [(vfLo * loPct) / 100, (vfHi * band.pct) / 100];
}

function patente(p: number, listing: CostListing, jurisdiction: Jurisdiction[] | null, b: Blocks): Result {
  const k = b.vf_from_price_k, valuesYear = b["patente.values_year"];
  if (!k || valuesYear == null) return { ok: false, reason: "params" };
  if (!jurisdiction?.length) return { ok: false, reason: "no_zone" };
  const year = listing.year;
  if (year == null) return { ok: false, reason: "no_year" };
  const names = jurisdiction.map((j) => `patente.${j}` as const);
  if (names.some((n) => !b[n])) return { ok: false, reason: "params" };
  const vfLo = p * k.min, vfHi = p * k.max;
  const ranges: [number, number][] = [];
  for (const j of jurisdiction) {
    if (j === "caba") ranges.push(patenteCaba(b["patente.caba"]!, vfLo, vfHi, year, valuesYear, listing.body_type));
    else if (j === "ba") {
      const c = b["patente.ba"]!;
      if (year < c.min_model_year) return { ok: false, reason: "pre_min_year" };
      ranges.push(patenteBa(c, vfLo, vfHi));
    } else ranges.push(patenteRest(b["patente.rest"]!, vfLo, vfHi, year));
  }
  return { ok: true, min: Math.min(...ranges.map(([lo]) => lo)), max: Math.max(...ranges.map(([, hi]) => hi)), blocks: ["vf_from_price_k", ...names] };
}

/**
 * The estimate, or null without a config (no root as_of) or a price. A USD
 * listing without a dollar gets an empty estimate (missing fx): the scales
 * are in pesos, nothing can be computed.
 */
export function estimateCost(
  listing: CostListing,
  jurisdiction: Jurisdiction[] | null,
  seller: Seller,
  fxLatest: FxQuote | null,
  cfg: CostConfig | null,
): Estimate | null {
  if (!cfg) return null;
  const price = finite(listing.price);
  if (price == null || price <= 0 || (listing.currency !== "ARS" && listing.currency !== "USD")) return null;
  const b = cfg.blocks;
  const base = {
    p_orig: { amount: price, currency: listing.currency },
    price_label: listing.cash ? ("cash" as const) : ("published" as const),
    jurisdiction: jurisdiction?.length ? [...jurisdiction] : null,
    seller,
    as_of: cfg.as_of,
  };
  let p: number;
  let rate: Estimate["rate"];
  if (listing.currency === "USD") {
    const r = finite(fxLatest?.rate);
    if (!r || r <= 0) {
      return { ...base, p_ars: null, rate: null, terms: [], extras: [], missing: [{ code: "fx", reason: "no_fx" }], total_ars: null, total_usd: null };
    }
    p = price * r;
    rate = { value: r, kind: fxLatest!.kind, date: fxLatest!.date };
  } else {
    p = price;
    const r = finite(listing.fx_rate);
    rate = r && r > 0 ? { value: r, kind: "listing", date: null } : null;
  }
  const results: Record<TermCode, Result> = {
    arancel: arancel(p, seller, b),
    sellos: sellos(p, jurisdiction, seller, b),
    formularios: formularios(b),
    patente: patente(p, listing, jurisdiction, b),
  };
  const terms: Term[] = [];
  const missing: Missing[] = [];
  for (const code of TERMS) {
    const res = results[code];
    if (res.ok) terms.push({ code, min: res.min, max: res.max, blocks: res.blocks });
    else missing.push({ code, reason: res.reason });
  }
  const extras: Extra[] = [];
  if (b.domain_report && b.mrpa_ars) {
    const n = b.domain_report.mrpa;
    extras.push({ code: "domain_report", min: n * b.mrpa_ars.min, max: n * b.mrpa_ars.max, blocks: ["domain_report", "mrpa_ars"] });
  }
  if (b.gestoria) extras.push({ code: "gestoria", min: null, max: null, blocks: ["gestoria"] });
  let lo = p, hi = p;
  for (const t of terms) {
    lo += t.min;
    hi += t.max;
  }
  let totalUsd: Range | null = null;
  if (rate) totalUsd = { min: lo / rate.value, max: hi / rate.value };
  else missing.push({ code: "fx", reason: "no_fx" });
  return { ...base, p_ars: p, rate, terms, extras, missing, total_ars: { min: lo, max: hi }, total_usd: totalUsd };
}

// ---------------------------------------------------------------------------
// The header
// ---------------------------------------------------------------------------

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? "");
}

/** " (sin patente)", " (sin sellos ni patente)", " (sin arancel, sellos ni patente)"; fx never goes here. */
export function missingSuffix(codes: readonly string[]): string {
  const names = TERMS.filter((c) => codes.includes(c)).map((c) => COST_ESTIMATE.names[c]);
  if (!names.length) return "";
  const items = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")}${COST_ESTIMATE.last}${names[names.length - 1]}`;
  return fill(COST_ESTIMATE.suffix, { items });
}

export type Rounded = { ars: Range | null; usd: Range | null };

/** The totals as shown: ARS to $1.000, USD to 10, outward. */
export function roundedTotals(est: Pick<Estimate, "total_ars" | "total_usd">): Rounded {
  const { total_ars: ars, total_usd: usd } = est;
  return {
    ars: ars ? { min: floorTo(ars.min, 1000), max: ceilTo(ars.max, 1000) } : null,
    usd: usd ? { min: floorTo(usd.min, 10), max: ceilTo(usd.max, 10) } : null,
  };
}

/** The header from already rounded totals. */
export function costHeadline(ars: Range | null, usd: Range | null, codes: readonly string[]): string {
  if (!ars) return COST_ESTIMATE.lineNoFx;
  const suffix = missingSuffix(codes);
  const arsText = formatRange(ars.min, ars.max, "ARS");
  if (!usd) return fill(COST_ESTIMATE.lineNoUsd, { suffix, ars: arsText });
  return fill(COST_ESTIMATE.line, { suffix, usd: formatRange(usd.min, usd.max, "USD"), ars: arsText });
}

export function costLine(est: Estimate): string {
  const r = roundedTotals(est);
  return costHeadline(r.ars, r.usd, est.missing.map((m) => m.code));
}

/** A detail line, rounded outward to $100. */
export function termAmount(t: { min: number; max: number }): string {
  return formatRange(floorTo(t.min, 100), ceilTo(t.max, 100), "ARS");
}

// ---------------------------------------------------------------------------
// /admin: when the parameters need a review
// ---------------------------------------------------------------------------

export type CostReview = "stale" | "due" | "missing" | null;

/**
 * "stale" past review.max_age_days; "due" in a review month while as_of is
 * before the current window of consecutive review months (across the year
 * end: with [12, 1], January's window starts on December 1st); "missing"
 * without a review block or a config. `today` is "YYYY-MM-DD".
 */
export function costEstimatorReview(cfg: CostConfig | null, today: string): CostReview {
  const review = cfg?.blocks.review;
  if (!cfg || !review) return "missing";
  if (daysBetween(cfg.as_of, today) > review.max_age_days) return "stale";
  const months = new Set(review.months);
  let year = Number(today.slice(0, 4)), month = Number(today.slice(5, 7));
  if (!months.has(month)) return null;
  for (let i = 0; i < 11; i++) {
    const prev = month === 1 ? 12 : month - 1;
    if (!months.has(prev)) break;
    if (month === 1) year -= 1;
    month = prev;
  }
  const start = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-01`;
  return cfg.as_of < start ? "due" : null;
}
