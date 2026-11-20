import type { MarketRef } from "@/lib/dealer-insights";
import { km as kmText, money } from "@/lib/format";

/**
 * Agencias: why a car's price is off the market, in words. The market reference
 * compares with every listing of the model, year ±1, whatever the mileage, the
 * trim or the seller; public.dealer_price_context() gives the medians of
 * narrower cuts of that same pool, and this module says which of them goes the
 * way of the gap. Pure. They are possible explanations from published prices,
 * never a statement about the car: with none, it says so.
 */

export type Cut = { n: number; median: number | null };
export type PriceContext = {
  km: number | null;
  kmN: number;
  kmMedian: number | null;
  sameYear: Cut;
  similarKm: Cut;
  closest: Cut;
  sameTrim: Cut;
  dealers: Cut;
};

/** A price within this of the market is «En precio» in the panel (dealer-insights.ts) and needs no explanation. */
export const GAP_PCT = 10;
/** A cut explains only with this many listings... */
export const MIN_CUT_N = 5;
/** ...and when its median is at least this far from the whole pool's, the way of the gap. */
export const CUT_SHIFT_PCT = 4;
/** More (or fewer) km than the pool's median by this share counts as a difference in use. */
export const KM_SHARE = 0.2;
/** So far below that it is more often a typo than a price. */
export const TYPO_PCT = -35;

const nf = new Intl.NumberFormat("es-AR");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function cut(raw: unknown): Cut {
  const r = (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {}) as Record<string, unknown>;
  return { n: num(r.n) ?? 0, median: num(r.median) };
}

/** dealer_price_context()'s JSON, read tolerantly; null when it isn't one. */
export function parsePriceContext(raw: unknown): PriceContext | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  return {
    km: num(r.km),
    kmN: num(r.km_n) ?? 0,
    kmMedian: num(r.km_median),
    sameYear: cut(r.same_year),
    similarKm: cut(r.similar_km),
    closest: cut(r.closest),
    sameTrim: cut(r.same_trim),
    dealers: cut(r.dealers),
  };
}

export type PriceWhy = {
  side: "below" | "above";
  /** One short line for the stock table. */
  short: string;
  /** Full sentences, the strongest first. Empty when the data explains nothing. */
  reasons: string[];
  /** The car against its closest look-alikes, or what to check when nothing explains the gap. */
  verdict: string;
  /** What the agency can load to get a better answer. */
  missing: string | null;
  /** With a reference by km: where the car would sit against the whole model, and that the km is the difference. */
  wide: string | null;
};

const usd = (v: number) => money(Math.round(v), "USD");
const pctOf = (a: number, b: number) => (a / b - 1) * 100;

/**
 * The explanations for a price more than GAP_PCT % off the market; null for a
 * price in line, or without a market reference to explain.
 */
export function priceReasons(
  car: { priceUsd: number | null; year: number | null; trim: string | null },
  market: MarketRef | null,
  ctx: PriceContext | null,
): PriceWhy | null {
  const pct = market?.enough ? market.vs_market_pct : null;
  const median = market?.median ?? null;
  if (pct == null || median == null || median <= 0 || Math.abs(pct) <= GAP_PCT || !ctx) return null;
  if (car.priceUsd == null || car.priceUsd <= 0) return null;
  const below = pct < 0;
  const side = below ? "below" : "above";
  // The reference already takes the km (and maybe the trim): those are no longer explanations of the gap.
  const byKm = market?.basis === "km" || market?.basis === "version_km";
  const byTrim = market?.basis === "version_km";
  /** The whole model's median: what the cuts of dealer_price_context() are measured against. */
  const whole = market?.wide?.median != null && market.wide.median > 0 ? market.wide.median : median;
  const cheaper = below ? "más barato" : "más caro";
  const cheaperF = below ? "más barata" : "más cara";
  const cheaperPl = below ? "más baratos" : "más caros";
  /** The cut's median, when it has enough listings and moved the way of the gap. */
  const shifted = (c: Cut): number | null => {
    if (c.n < MIN_CUT_N || c.median == null || c.median <= 0) return null;
    const shift = pctOf(c.median, whole);
    return (below ? shift <= -CUT_SHIFT_PCT : shift >= CUT_SHIFT_PCT) ? c.median : null;
  };

  const reasons: string[] = [];
  const shorts: string[] = [];

  // Use: more km than the look-alikes pulls a price down, fewer pulls it up.
  if (!byKm && ctx.km != null && ctx.kmMedian != null && ctx.kmMedian > 0 && ctx.kmN >= MIN_CUT_N) {
    const more = ctx.km >= ctx.kmMedian * (1 + KM_SHARE);
    const fewer = ctx.km <= ctx.kmMedian * (1 - KM_SHARE);
    if ((below && more) || (!below && fewer)) {
      const near = ctx.similarKm.n >= MIN_CUT_N && ctx.similarKm.median != null ? ctx.similarKm.median : null;
      reasons.push(
        `Tiene ${below ? "más" : "menos"} kilómetros que los parecidos: ${kmText(ctx.km)} contra ${kmText(ctx.kmMedian)} de mediana.`
        + (near != null ? ` Los de kilometraje parecido se publican a ${usd(near)} de mediana (${nf.format(ctx.similarKm.n)} avisos).` : ""),
      );
      shorts.push(`${below ? "Más" : "Menos"} km que los parecidos`);
    }
  }

  const trimMedian = car.trim && !byTrim ? shifted(ctx.sameTrim) : null;
  if (trimMedian != null) {
    reasons.push(`Su versión (${car.trim}) se publica ${cheaperF} que el resto del modelo: ${usd(trimMedian)} de mediana en ${nf.format(ctx.sameTrim.n)} avisos, contra ${usd(whole)} de todo el modelo.`);
    shorts.push(`Su versión se publica ${cheaperF}`);
  }

  const yearMedian = shifted(ctx.sameYear);
  if (yearMedian != null) {
    reasons.push(`Los de su mismo año${car.year ? ` (${car.year})` : ""} se publican ${cheaperPl} que el grupo de año ±1: ${usd(yearMedian)} de mediana en ${nf.format(ctx.sameYear.n)} avisos.`);
    shorts.push(`Su año se publica ${cheaper}`);
  }

  const dealersMedian = shifted(ctx.dealers);
  if (dealersMedian != null) {
    reasons.push(`Las agencias publican este modelo ${cheaper} que el conjunto: ${usd(dealersMedian)} de mediana entre ${nf.format(ctx.dealers.n)} avisos de agencias.`);
    shorts.push(`Las agencias lo publican ${cheaper}`);
  }

  // Against the closest look-alikes: same year and similar km; only similar km when those are few. With a
  // reference by km the second is the reference itself, and by trim neither is closer than it.
  const close = byTrim ? null
    : ctx.closest.n >= MIN_CUT_N && ctx.closest.median ? { c: ctx.closest, what: "mismo año y kilómetros parecidos" }
    : !byKm && ctx.similarKm.n >= MIN_CUT_N && ctx.similarKm.median ? { c: ctx.similarKm, what: "kilómetros parecidos" }
    : null;
  const shown = (p: number) => nf.format(Math.round(Math.abs(p)));
  let verdict: string;
  let closes = false;
  if (close) {
    const p = pctOf(car.priceUsd, close.c.median!);
    const ref = `${close.what}, ${nf.format(close.c.n)} avisos, mediana ${usd(close.c.median!)}`;
    closes = Math.abs(p) <= GAP_PCT;
    verdict = closes
      ? `Contra los más parecidos (${ref}) está en precio.`
      : `Contra los más parecidos (${ref}) ${(p < 0) === below ? "sigue" : "queda"} ${shown(p)} % ${p < 0 ? "abajo" : "arriba"}.`;
  } else if (reasons.length > 0 && !byKm) {
    verdict = "No hay suficientes avisos con el mismo año y kilómetros parecidos para medir cuánto de la diferencia explican.";
  } else {
    verdict = "";
  }
  // Nothing in the data goes the way of the gap: say so, and what it usually is.
  if (reasons.length === 0 && !closes) {
    const unexplained = pct <= TYPO_PCT
      ? "No encontramos una explicación en los datos. Con tanta diferencia suele ser un error de carga: revisá la moneda y los ceros del precio."
      : below
        ? "No encontramos una explicación en los datos (kilómetros, año, versión). Puede ser el estado del auto, o hay lugar para subir el precio."
        : "No encontramos una explicación en los datos (kilómetros, año, versión). Puede ser el estado o el equipamiento del auto, o un precio con margen para negociar.";
    verdict = verdict ? `${verdict} ${unexplained}` : unexplained;
  }

  const short = shorts[0] ?? (closes ? "En precio contra los más parecidos" : "Sin explicación en los datos");
  const missing = ctx.km == null ? "Cargá los kilómetros: es lo que más mueve el precio, y sin ellos comparamos con autos de cualquier uso."
    : !car.trim ? "Cargá la versión para comparar con la misma versión."
    : null;
  const widePct = market?.wide?.vs_market_pct ?? null;
  const wide = byKm && widePct != null && Math.abs(widePct - pct) >= 5 && ctx.km != null && ctx.kmMedian != null
    ? `Contra todo el modelo, sin mirar kilómetros, ${Math.abs(widePct) <= GAP_PCT ? "estaría en precio" : `estaría ${shown(widePct)} % ${widePct < 0 ? "abajo" : "arriba"}`}: `
      + `el auto tiene ${kmText(ctx.km)} y la mediana del modelo es ${kmText(ctx.kmMedian)}.`
    : null;
  return { side, short, reasons, verdict, missing, wide };
}

export const PRICE_WHY_TITLE = { below: "Por qué puede estar abajo del mercado", above: "Por qué puede estar arriba del mercado" } as const;
export const PRICE_WHY_NOTE = "Son explicaciones posibles según precios publicados de autos parecidos. No conocemos el estado del auto.";
