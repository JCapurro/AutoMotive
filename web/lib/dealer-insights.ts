import { km, money, vehicle } from "@/lib/format";

/**
 * The agency panel's numbers in words (spec §6.3). Pure: the page passes what
 * public.dealer_stock_insights() returned. Demand counts come already rounded
 * by SQL ("few" under demand_min_count); this module never prints a 1 or a 2
 * even if one came through.
 */

export type MarketRef = {
  n: number;
  median: number | null;
  p25: number | null;
  p75: number | null;
  vs_market_pct: number | null;
  enough: boolean;
  year_tol?: number;
  days?: number;
  blue?: number | null;
};

export type DemandLevel = number | "few" | null;
export type Demand =
  | { approved: false }
  | { approved: true; window_days: number; min_count: number; levels: { model: DemandLevel; fits: DemandLevel; zone: DemandLevel; active_zone: DemandLevel } };

export type ModelDaysToSell = { median: number | null; n: number };

export type HiddenReason = "no_dealer" | "channel_off" | "not_approved" | "not_available" | "unconfirmed" | "pending_sync";

const nf = new Intl.NumberFormat("es-AR");

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** dealer_market_ref()'s JSON, read tolerantly; null when it isn't one. */
export function parseMarket(raw: unknown): MarketRef | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const n = num(r.n);
  if (n == null) return null;
  return {
    n,
    median: num(r.median),
    p25: num(r.p25),
    p75: num(r.p75),
    vs_market_pct: num(r.vs_market_pct),
    enough: r.enough === true,
    year_tol: num(r.year_tol) ?? undefined,
    days: num(r.days) ?? undefined,
    blue: num(r.blue),
  };
}

function level(v: unknown): DemandLevel {
  if (v === "few") return "few";
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return null;
}

export function parseDemand(raw: unknown): Demand {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { approved: false };
  const r = raw as Record<string, unknown>;
  if (r.approved !== true) return { approved: false };
  const lv = (r.levels && typeof r.levels === "object" ? r.levels : {}) as Record<string, unknown>;
  return {
    approved: true,
    window_days: num(r.window_days) ?? 90,
    min_count: Math.max(3, num(r.min_count) ?? 3),
    levels: { model: level(lv.model), fits: level(lv.fits), zone: level(lv.zone), active_zone: level(lv.active_zone) },
  };
}

export function parseModelDays(raw: unknown): ModelDaysToSell {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { median: null, n: 0 };
  const r = raw as Record<string, unknown>;
  return { median: num(r.median), n: num(r.n) ?? 0 };
}

const comparables = (n: number) => `${nf.format(n)} ${n === 1 ? "comparable" : "comparables"}`;

/** «12 % arriba de autos parecidos · 23 comparables»; «En precio» within ±10 %. */
export function priceVsMarketText(market: MarketRef | null): string {
  if (!market || market.n === 0) return "Sin comparables";
  if (!market.enough) return `Pocos comparables (${nf.format(market.n)})`;
  const pct = market.vs_market_pct;
  if (pct == null) return `Sin precio en dólares · ${comparables(market.n)}`;
  if (Math.abs(pct) <= 10) return `En precio · ${comparables(market.n)}`;
  const shown = nf.format(Math.round(Math.abs(pct)));
  return `${shown} % ${pct > 0 ? "arriba" : "abajo"} de autos parecidos · ${comparables(market.n)}`;
}

/** «Revisá este precio» when it is far below (a cost?) or far above the market. */
export function priceCheck(market: MarketRef | null): "far_below" | "far_above" | null {
  if (!market?.enough || market.vs_market_pct == null) return null;
  if (market.vs_market_pct <= -20) return "far_below";
  if (market.vs_market_pct >= 50) return "far_above";
  return null;
}

export const PRICE_CHECK_TEXT = "Revisá este precio";

/** A demand count, safely: a number below the minimum (it shouldn't come) prints as «pocas». */
export function demandCount(v: DemandLevel, min = 3): string {
  if (v === null) return "sin dato";
  if (v === "few") return "pocas";
  if (v === 0) return "ninguna";
  if (v < Math.max(3, min)) return "pocas";
  return nf.format(v);
}

function phrase(v: DemandLevel, min: number, unit: [string, string], rest: string): string {
  const count = demandCount(v, min);
  return `${count} ${count === "ninguna" ? unit[0] : unit[1]}${rest}`;
}

/**
 * «42 búsquedas del modelo · 17 entran en año y precio · 8 en tu zona · 2 activas
 * en tu zona» (the active count in words: «pocas» below the minimum).
 */
export function demandTexts(demand: Demand): string[] {
  if (!demand.approved) return ["La demanda se ve cuando aprobemos tu agencia"];
  const { levels, min_count: min } = demand;
  return [
    phrase(levels.model, min, ["búsqueda", "búsquedas"], " del modelo"),
    `${demandCount(levels.fits, min)} ${levels.fits === 0 ? "entra" : "entran"} en año y precio`,
    `${demandCount(levels.zone, min)} en tu zona`,
    `${demandCount(levels.active_zone, min)} ${levels.active_zone === 0 ? "activa" : "activas"} en tu zona`,
  ];
}

export function demandText(demand: Demand): string {
  return demandTexts(demand).join(" · ");
}

/** §2's reason, in words, for the «Envío» column. */
export function hiddenReasonText(reason: string | null, days: number): string {
  switch (reason) {
    case null:
      return "Se envía a quien lo busca";
    case "channel_off":
      return "Todavía no se envía a compradores";
    case "not_approved":
      return "Falta que aprobemos tu agencia";
    case "not_available":
      return "Reservado o vendido: no se envía";
    case "unconfirmed":
      return `Sin confirmar hace más de ${days} ${days === 1 ? "día" : "días"}: confirmalo para que vuelva a enviarse`;
    case "pending_sync":
    case "no_dealer":
      return "Lo estamos cargando";
    default:
      return "No se envía";
  }
}

export const SYNC_ERROR_TEXT = "No lo pudimos cargar: revisá marca, modelo y año";
export const REVIEW_TEXT = "En revisión: ¿es tu aviso?";

/**
 * Whether one of my cars reaches buyers, in words, for the stock table and the
 * car's page: the stock status and the worker's state first (out of stock,
 * sold, in review, not loaded), then the gate's reason. `hiddenReason`
 * undefined means there is no insight row (an archived item): «Lo estamos
 * cargando» only for a car still on sale.
 */
export function itemSending(
  item: { status: string; sync_state: string; hidden_reason?: string | null },
  days: number,
): { text: string; sends: boolean } {
  if (item.status === "archived") return { text: "Sacado del stock", sends: false };
  if (item.status === "sold") return { text: "Vendido: no se envía", sends: false };
  if (item.sync_state === "review") return { text: REVIEW_TEXT, sends: false };
  if (item.sync_state === "error") return { text: SYNC_ERROR_TEXT, sends: false };
  const reason = item.hidden_reason === undefined ? "pending_sync" : item.hidden_reason;
  return { text: hiddenReasonText(reason, days), sends: reason === null };
}

/** «En stock hace 34 días · el modelo se vende en unos 41» (median of the model, only with enough cars). */
export function daysInStockText(days: number | null, modelDays: ModelDaysToSell | null): string {
  const own = days == null ? "Sin fecha de ingreso" : days <= 0 ? "Entró hoy" : `En stock hace ${nf.format(days)} ${days === 1 ? "día" : "días"}`;
  if (!modelDays || modelDays.median == null || modelDays.n < 5) return own;
  return `${own} · el modelo se vende en unos ${nf.format(modelDays.median)}`;
}

/** What the panel needs of a dealer_stock_insights() row. */
export type InsightRow = {
  item_id: number;
  origin: string;
  status: string;
  sync_state: string;
  make: string | null;
  model: string | null;
  trim: string | null;
  year: number | null;
  mileage_km: number | null;
  price: number | null;
  currency: string | null;
  price_usd: number | null;
  hidden_reason: string | null;
  market: unknown;
  days_in_stock: number | null;
  model_days_to_sell: unknown;
  demand: unknown;
};

/** A row of /agencia/stock in words (StockTable's StockRow). */
export function stockRowView(row: InsightRow, manualConfirmDays: number, photo: string | null = null) {
  const market = parseMarket(row.market);
  const sending = itemSending(row, manualConfirmDays);
  const name = vehicle({ make: row.make, model: row.model, year: row.year }) || "Auto";
  return {
    itemId: row.item_id,
    photo,
    name,
    detail: [row.trim, km(row.mileage_km), row.origin === "sync" ? "Sincronizado" : row.origin === "sheet" ? "Planilla" : "Cargado a mano"].filter(Boolean).join(" · "),
    price: money(row.price, row.currency),
    priceUsd: row.currency === "ARS" && row.price_usd ? money(row.price_usd, "USD") : null,
    market: priceVsMarketText(market),
    priceCheck: priceCheck(market) !== null,
    demand: demandText(parseDemand(row.demand)),
    days: daysInStockText(row.days_in_stock, parseModelDays(row.model_days_to_sell)),
    status: row.status,
    origin: row.origin,
    sending: sending.text,
    sends: sending.sends,
    review: row.sync_state === "review",
    facts: stockFacts(row),
  };
}

/** The same row as numbers and short labels, for layouts that draw them (the stock screen's options). */
export type StockFacts = {
  pct: number | null;
  n: number;
  enough: boolean;
  medianUsd: number | null;
  p25Usd: number | null;
  p75Usd: number | null;
  priceUsd: number | null;
  /** below / fair / above the market; check = far enough to look like a typo or a cost; none = no reference. */
  tone: "below" | "fair" | "above" | "check" | "none";
  priceLabel: string;
  demandApproved: boolean;
  demand: { model: string; fits: string; zone: string; active: string };
  /** For sorting and grouping only: 0 none, 1 few, else the count. Never shown. */
  demandRank: number;
  daysInStock: number | null;
  modelDays: number | null;
  slow: boolean;
};

export function stockFacts(row: InsightRow): StockFacts {
  const market = parseMarket(row.market);
  const demand = parseDemand(row.demand);
  const modelDays = parseModelDays(row.model_days_to_sell);
  const pct = market?.enough ? market.vs_market_pct : null;
  const check = priceCheck(market) !== null;
  const tone = pct == null ? "none" : check ? "check" : Math.abs(pct) <= 10 ? "fair" : pct > 0 ? "above" : "below";
  const shown = pct == null ? "" : nf.format(Math.round(Math.abs(pct)));
  const priceLabel =
    !market || market.n === 0 ? "Sin comparables"
    : !market.enough ? "Pocos comparables"
    : pct == null ? "Sin precio en dólares"
    : Math.abs(pct) <= 10 ? "En precio"
    : `${shown} % ${pct > 0 ? "arriba" : "abajo"}`;
  const lv = demand.approved ? demand.levels : null;
  const min = demand.approved ? demand.min_count : 3;
  const rank = (v: DemandLevel) => (v === "few" ? 1 : typeof v === "number" ? (v > 0 && v < 3 ? 1 : v) : 0);
  const median = modelDays.n >= 5 ? modelDays.median : null;
  return {
    pct,
    n: market?.n ?? 0,
    enough: market?.enough ?? false,
    medianUsd: market?.median ?? null,
    p25Usd: market?.p25 ?? null,
    p75Usd: market?.p75 ?? null,
    priceUsd: row.price_usd,
    tone,
    priceLabel,
    demandApproved: demand.approved,
    demand: {
      model: lv ? demandCount(lv.model, min) : "—",
      fits: lv ? demandCount(lv.fits, min) : "—",
      zone: lv ? demandCount(lv.zone, min) : "—",
      active: lv ? demandCount(lv.active_zone, min) : "—",
    },
    demandRank: lv ? rank(lv.zone) : 0,
    daysInStock: row.days_in_stock,
    modelDays: median,
    slow: row.days_in_stock != null && median != null && row.days_in_stock > median * 1.5,
  };
}

/** Stock statuses the agency can pick. */
export const ITEM_STATUS: Record<string, string> = {
  available: "Disponible",
  reserved: "Reservado",
  sold: "Vendido",
  archived: "Sacar del stock",
};

export const LEAD_STATUS: Record<string, string> = {
  new: "Nueva",
  contacted: "Contactada",
  reserved: "Reservó",
  sold: "Compró",
  lost: "No avanzó",
};

export const LEAD_ORIGIN: Record<string, string> = {
  ficha: "Ficha",
  email: "Email",
  telegram: "Telegram",
  web: "Web",
};
