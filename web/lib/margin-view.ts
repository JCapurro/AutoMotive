/**
 * PRO-02: the words of matches.margin_ref (worker/intelligence/margin.py
 * computes and stores it): the line of the cards, the listing page and the
 * Pro emails, and the listing page's detail. Pure; the same rounding as the
 * worker's margin.email_payload (outward to USD 10, floor/ceil with EPS, the
 * median to the nearest 10), so the web and the alerts print the same line.
 */
import { COMPARABLE_LEVEL, MARGIN } from "@/lib/copy";
import { jurisdictionNames } from "@/lib/cost-estimate-view";
import type { Jurisdiction } from "@/lib/cost-estimator";
import { ceilTo, floorTo, isoDayMonth, ROUNDING_EPS, thousands } from "@/lib/format";

export type MarginRange = { min: number; max: number };
export type TransferStatus = "ok" | "no_zone" | "no_fx" | "params" | "base" | "no_price" | "disabled";
export type MarginRef = {
  v: number;
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
  gross_margin_usd: MarginRange;
  gross_margin_pct: MarginRange;
  as_of: { dealer_margin?: string | null; cost_estimator?: string | null };
};

/** What the worker's alerts keep (margin.email_payload), rounded. */
export type MarginPayload = {
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

/** A stored margin_ref, or null when it is not one (an unknown shape is never shown). */
export function asMarginRef(value: unknown): MarginRef | null {
  if (!value || typeof value !== "object") return null;
  const r = value as Partial<MarginRef>;
  const g = r.gross_margin_usd;
  if (!g || !isNum(g.min) || !isNum(g.max) || !isNum(r.dealer_median) || !isNum(r.dealer_n)) return null;
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
  const dates = [ref.as_of?.dealer_margin, ref.as_of?.cost_estimator].filter((d): d is string => typeof d === "string").sort();
  return {
    usd_min: single ? round10(g.min) : floorTo(g.min, 10),
    usd_max: single ? round10(g.min) : ceilTo(g.max, 10),
    pct_min: p && isNum(p.min) ? Math.floor(p.min + ROUNDING_EPS) : null,
    pct_max: p && isNum(p.max) ? Math.ceil(p.max - ROUNDING_EPS) : null,
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

export function marginLine(value: unknown): string | null {
  const ref = asMarginRef(value);
  return ref ? marginHeadline(marginPayload(ref)) : null;
}

function usdRange(r: MarginRange): string {
  const lo = floorTo(r.min, 10);
  const hi = ceilTo(r.max, 10);
  return Math.abs(r.max - r.min) < ROUNDING_EPS ? fill(MARGIN.single, { v: signed(round10(r.min)) }) : usdText(lo, hi);
}

/** The listing page's detail: what the margin subtracts, in numbers, and what it is not. */
export function marginDetail(ref: MarginRef): string[] {
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
    if (t.jurisdiction?.includes("rest")) out.push(MARGIN.rest);
  } else {
    out.push(fill(MARGIN.transferMissing, { why: why(t?.status ?? null) }));
  }
  if (p.pct_min != null && p.pct_max != null) {
    out.push(fill(MARGIN.pct, { pct: p.pct_min === p.pct_max ? `${p.pct_min} %` : `${p.pct_min} % a ${p.pct_max} %` }));
  }
  out.push(MARGIN.excludes, MARGIN.published);
  if (p.as_of) out.push(fill(MARGIN.asOf, { date: isoDayMonth(p.as_of) }));
  return out;
}
