/**
 * PRO-02: the words of matches.margin_ref (worker/intelligence/margin.py
 * computes and stores it): the line of the listing page and the Pro emails,
 * the cards' short line, and the listing page's detail. Pure; the same rounding as the
 * worker's margin.email_payload (outward to USD 10, floor/ceil with EPS, the
 * median to the nearest 10), so the web and the alerts print the same line.
 *
 * An implausible price has no margin (worker margin.plausible): asking_usd
 * above 3x or below 0,4x the dealers' median (an ARS price loaded as USD, a
 * down payment not detected). compute() no longer stores one, and the refs
 * stored before that guard are not shown here (no line, no card line, no
 * detail) until the worker's rescore recomputes them to null.
 */
import { COMPARABLE_LEVEL, MARGIN } from "@/lib/copy";
import { jurisdictionNames } from "@/lib/cost-estimate-view";
import type { Jurisdiction } from "@/lib/cost-estimator";
import { ceilTo, floorTo, isoDayMonth, ROUNDING_EPS, thousands } from "@/lib/format";

export type MarginRange = { min: number; max: number };
export type TransferStatus = "ok" | "no_zone" | "no_official" | "no_official_some" | "no_fx" | "params" | "base" | "no_price" | "disabled";
export type MarginRef = {
  v: number;
  status?: "ok";
  dealer_median: number;
  dealer_n: number;
  n: number;
  level_used: string;
  asking_usd: number;
  price_label: "published" | "cash";
  currency: string | null;
  fx: { rate: number; kind: string | null; date: string | null } | null;
  reconditioning: { pct: number; min_usd: number; usd: number } | null;
  transfer: { status: TransferStatus; usd: MarginRange | null; terms?: string[]; jurisdiction: Jurisdiction[] | null; seller: string | null };
  est_costs_usd: MarginRange;
  /** What buying the car costs: asking_usd + est_costs_usd (the base of gross_margin_pct). */
  acquisition_usd?: MarginRange;
  gross_margin_usd: MarginRange;
  gross_margin_pct: MarginRange;
  /** The asking_usd / dealer_median bounds it passed (absent in refs from before the guard). */
  plausible_ratio?: MarginRange;
  as_of: { dealer_margin?: string | null; cost_estimator?: string | null };
};

/** Juan, 02/11: fewer dealers than comparables.min_n, no margin but the line that says so. */
export type MarginFewDealers = {
  v: number;
  status: "few_dealers";
  dealer_n: number;
  min_n: number;
  n?: number;
  level_used?: string;
};

/** What matches.margin_ref holds: a margin, or not enough dealers. */
export type StoredMargin = MarginRef | MarginFewDealers;

/** What the worker's alerts keep (margin.email_payload), rounded. */
export type MarginPayload = {
  status?: "ok";
  usd_min: number;
  usd_max: number;
  pct_min: number | null;
  pct_max: number | null;
  dealer_median: number;
  dealer_n: number;
  reconditioning_pct: number | null;
  transfer_status: TransferStatus | null;
  jurisdiction: Jurisdiction[] | null;
  as_of: string | null;
};

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/** A stored margin_ref that says there are not enough dealers, or null. */
export function asFewDealers(value: unknown): MarginFewDealers | null {
  if (!value || typeof value !== "object") return null;
  const r = value as Partial<MarginFewDealers>;
  return r.status === "few_dealers" && Number.isInteger(r.dealer_n) && Number.isInteger(r.min_n) ? (r as MarginFewDealers) : null;
}

/** A stored margin_ref (a margin or not enough dealers), or null when it is not one. */
export function asStoredMargin(value: unknown): StoredMargin | null {
  return asFewDealers(value) ?? asMarginRef(value);
}

/** The worker's margin.PLAUSIBLE_RATIO (app_config.dealer_margin.plausible_ratio's default) and PLAUSIBLE_EPS. */
export const PLAUSIBLE_RATIO: MarginRange = { min: 0.4, max: 3 };
const PLAUSIBLE_EPS = 0.01;

/** The worker's margin.parse_ratio: {min, max} with 0 < min < 1 < max, else PLAUSIBLE_RATIO. */
function parseRatio(value: unknown): MarginRange {
  const r = value && typeof value === "object" ? (value as Partial<MarginRange>) : null;
  return r && isNum(r.min) && isNum(r.max) && r.min > 0 && r.min < 1 && r.max > 1 ? { min: r.min, max: r.max } : PLAUSIBLE_RATIO;
}

/**
 * The worker's margin.plausible: min x median <= asking_usd <= max x median
 * (inclusive), with the ref's own bounds or, before the guard, PLAUSIBLE_RATIO.
 */
export function plausiblePrice(ref: Pick<MarginRef, "asking_usd" | "dealer_median"> & { plausible_ratio?: unknown }): boolean {
  const { asking_usd: asking, dealer_median: median } = ref;
  if (!isNum(asking) || !isNum(median) || median <= 0) return false;
  const r = parseRatio(ref.plausible_ratio);
  return r.min * median - PLAUSIBLE_EPS <= asking && asking <= r.max * median + PLAUSIBLE_EPS;
}

/**
 * A stored margin_ref with a margin, or null when it is not one (an unknown
 * shape is never shown) or its price is implausible (plausiblePrice).
 */
export function asMarginRef(value: unknown): MarginRef | null {
  if (!value || typeof value !== "object") return null;
  const r = value as Partial<MarginRef> & { status?: unknown };
  if (r.status !== undefined && r.status !== "ok") return null;
  const g = r.gross_margin_usd;
  if (!g || !isNum(g.min) || !isNum(g.max) || !isNum(r.dealer_median) || !isNum(r.dealer_n)) return null;
  if (!plausiblePrice(r as MarginRef)) return null;
  return r as MarginRef;
}

/** -300 -> "-300", 1400 -> "1.400". */
export function signed(n: number): string {
  return (n < 0 ? "-" : "") + thousands(Math.abs(Math.trunc(n)));
}

/** The median shown, to the nearest 10: floor(x / 10 + 0.5), the worker's round10. */
export function round10(x: number): number {
  return 10 * Math.floor(x / 10 + 0.5);
}

/** 5 -> "5", 5.5 -> "5,5". */
export function pctText(pct: number): string {
  return Number.isInteger(pct) ? String(pct) : pct.toFixed(2).replace(/0+$/, "").replace(".", ",");
}

export function marginPayload(ref: MarginRef): MarginPayload {
  const g = ref.gross_margin_usd;
  const p = ref.gross_margin_pct;
  const single = Math.abs(g.max - g.min) < ROUNDING_EPS;
  const pct = p && isNum(p.min) && isNum(p.max)
    ? Math.abs(p.max - p.min) < ROUNDING_EPS
      ? [Math.floor(p.min + 0.5), Math.floor(p.min + 0.5)]
      : [Math.floor(p.min + ROUNDING_EPS), Math.ceil(p.max - ROUNDING_EPS)]
    : [null, null];
  const dates = [ref.as_of?.dealer_margin, ref.as_of?.cost_estimator].filter((d): d is string => typeof d === "string").sort();
  return {
    status: "ok",
    usd_min: single ? round10(g.min) : floorTo(g.min, 10),
    usd_max: single ? round10(g.min) : ceilTo(g.max, 10),
    pct_min: pct[0],
    pct_max: pct[1],
    dealer_median: round10(ref.dealer_median),
    dealer_n: ref.dealer_n,
    reconditioning_pct: ref.reconditioning ? ref.reconditioning.pct : null,
    transfer_status: ref.transfer?.status ?? null,
    jurisdiction: ref.transfer?.jurisdiction ?? null,
    as_of: dates[0] ?? null,
  };
}

function why(status: TransferStatus | null): string {
  return MARGIN.why[status ?? ""] ?? MARGIN.why.params;
}

export function costsText(reconditioningPct: number | null, status: TransferStatus | null): string {
  if (reconditioningPct != null) {
    return status === "ok"
      ? fill(MARGIN.costsBoth, { pct: pctText(reconditioningPct) })
      : fill(MARGIN.costsNoTransfer, { pct: pctText(reconditioningPct), why: why(status) });
  }
  return status === "ok" ? MARGIN.costsNoReconditioning : fill(MARGIN.costsNone, { why: why(status) });
}

export function usdText(lo: number, hi: number): string {
  return lo === hi ? fill(MARGIN.single, { v: signed(lo) }) : fill(MARGIN.range, { lo: signed(lo), hi: signed(hi) });
}

export function marginHeadline(p: MarginPayload): string {
  return fill(MARGIN.line, {
    usd: usdText(p.usd_min, p.usd_max),
    median: fill(MARGIN.single, { v: signed(p.dealer_median) }),
    n: p.dealer_n,
    costs: costsText(p.reconditioning_pct, p.transfer_status),
  });
}

/** «Margen estimado: no hay suficientes agencias … (n = 2, mínimo 5)». */
export function fewDealersLine(r: MarginFewDealers): string {
  return fill(MARGIN.fewDealers, { n: r.dealer_n, min_n: r.min_n });
}

/** The line of the listing page and the Pro emails: the margin, or why there is none. */
export function marginLine(value: unknown): string | null {
  const few = asFewDealers(value);
  if (few) return fewDealersLine(few);
  const ref = asMarginRef(value);
  return ref ? marginHeadline(marginPayload(ref)) : null;
}

/**
 * The result cards' short line (Juan, 02/11: the full one took ~5 lines in a
 * card): the same USD figure or range as marginLine and the dealers' n; the
 * median, the costs and «sin impuestos» stay on the listing page.
 */
export function marginCardLine(value: unknown): string | null {
  const few = asFewDealers(value);
  if (few) return fill(MARGIN.cardFewDealers, { n: few.dealer_n });
  const ref = asMarginRef(value);
  if (!ref) return null;
  const p = marginPayload(ref);
  return fill(MARGIN.cardLine, { usd: usdText(p.usd_min, p.usd_max), n: p.dealer_n });
}

function usdRange(r: MarginRange): string {
  const lo = floorTo(r.min, 10);
  const hi = ceilTo(r.max, 10);
  return Math.abs(r.max - r.min) < ROUNDING_EPS ? fill(MARGIN.single, { v: signed(round10(r.min)) }) : usdText(lo, hi);
}

/** The listing page's detail: what the margin subtracts, in numbers, and what it is not (nothing for an implausible price). */
export function marginDetail(ref: MarginRef): string[] {
  if (!asMarginRef(ref)) return [];
  const p = marginPayload(ref);
  const out: string[] = [];
  out.push(fill(MARGIN.median, {
    median: fill(MARGIN.single, { v: signed(p.dealer_median) }),
    n: ref.dealer_n,
    total: ref.n,
    level: COMPARABLE_LEVEL[ref.level_used] ?? ref.level_used,
  }));
  out.push(fill(ref.price_label === "cash" ? MARGIN.askingCash : MARGIN.asking, { asking: fill(MARGIN.single, { v: signed(round10(ref.asking_usd)) }) }));
  const rec = ref.reconditioning;
  out.push(rec
    ? fill(MARGIN.reconditioning, {
      usd: fill(MARGIN.single, { v: signed(round10(rec.usd)) }),
      pct: pctText(rec.pct),
      min: fill(MARGIN.single, { v: signed(rec.min_usd) }),
    })
    : MARGIN.reconditioningMissing);
  const t = ref.transfer;
  if (t?.status === "ok" && t.usd) {
    out.push(fill(MARGIN.transfer, { usd: usdRange(t.usd), jurisdiction: jurisdictionNames(t.jurisdiction ?? []) }));
  } else {
    out.push(fill(MARGIN.transferMissing, { why: why(t?.status ?? null) }));
  }
  const acq = ref.acquisition_usd;
  if (acq && isNum(acq.min) && isNum(acq.max)) out.push(fill(MARGIN.acquisition, { usd: usdRange(acq) }));
  if (p.pct_min != null && p.pct_max != null) {
    out.push(fill(MARGIN.pct, { pct: p.pct_min === p.pct_max ? `${p.pct_min} %` : `${p.pct_min} % a ${p.pct_max} %` }));
  }
  out.push(MARGIN.excludes, MARGIN.published);
  if (p.as_of) out.push(fill(MARGIN.asOf, { date: isoDayMonth(p.as_of) }));
  return out;
}
