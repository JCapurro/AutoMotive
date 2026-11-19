/**
 * Agencias, fase 3 (supabase/migrations/20261231120000_dealer_phase3.sql):
 * «Qué comprar» and the sellers who accept agencies' contact. Pure: pages,
 * actions and tests import it. Every count comes already rounded by SQL
 * (a model shows only with 3 or more people behind it); this only puts it in words.
 */

const nf = new Intl.NumberFormat("es-AR");

// ---------------------------------------------------------------- switch

export type DealerSellersConfig = { sellersEnabled: boolean; requestsPerDay: number };

/** app_config.dealer_program's sellers keys, read like public.dealer_sellers_config(). */
export function parseDealerSellers(raw: unknown): DealerSellersConfig {
  const v = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const perDay = v.seller_requests_per_day;
  return {
    sellersEnabled: v.enabled === true && v.sellers_enabled === true,
    requestsPerDay: typeof perDay === "number" && Number.isInteger(perDay) && perDay >= 1 && perDay <= 50 ? perDay : 5,
  };
}

// ---------------------------------------------------------------- «Qué comprar»

/** A demand level as SQL rounds it: a number, "few" (under 3 people) or 0. */
export type Level = number | "few" | null;

export type BuyOpportunity = {
  make: string | null;
  model: string;
  searches: number;
  activeSearches: Level;
  yearFrom: number | null;
  yearTo: number | null;
  budget: number | null;
  budgetCurrency: "ARS" | "USD" | null;
  supplyTotal: number;
  supplyNear: number;
};

const int = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? Math.round(v) : null);

function level(v: unknown): Level {
  if (v === "few") return "few";
  const n = int(v);
  // Never 1 or 2: SQL already rounds them to "few", this is the second lock.
  if (n === null) return null;
  return n > 0 && n < 3 ? "few" : n;
}

/** dealer_buy_opportunities() rows; a malformed row is dropped. */
export function parseBuyOpportunities(raw: unknown): BuyOpportunity[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((r) => {
    if (!r || typeof r !== "object") return [];
    const o = r as Record<string, unknown>;
    const searches = int(o.searches);
    if (typeof o.model !== "string" || !o.model || searches === null || searches < 3) return [];
    const cur = o.budget_currency === "ARS" || o.budget_currency === "USD" ? o.budget_currency : null;
    const budget = o.budget == null ? null : Number(o.budget);
    return [{
      make: typeof o.make === "string" && o.make ? o.make : null,
      model: o.model,
      searches,
      activeSearches: level(o.active_searches),
      yearFrom: int(o.year_from),
      yearTo: int(o.year_to),
      budget: cur && Number.isFinite(budget) && budget! > 0 ? budget : null,
      budgetCurrency: cur && Number.isFinite(budget) && budget! > 0 ? cur : null,
      supplyTotal: int(o.supply_total) ?? 0,
      supplyNear: int(o.supply_near) ?? 0,
    }];
  });
}

export function modelName(o: { make: string | null; model: string }): string {
  return [o.make, o.model].filter(Boolean).join(" ");
}

/** «4 búsquedas · 3 activas», «3 búsquedas · pocas activas». */
export function demandLine(o: BuyOpportunity): string {
  const total = `${nf.format(o.searches)} búsquedas`;
  if (o.activeSearches === "few") return `${total} · pocas activas`;
  if (o.activeSearches === 0) return `${total} · ninguna activa`;
  if (typeof o.activeSearches === "number") return `${total} · ${nf.format(o.activeSearches)} activas`;
  return total;
}

/** «2018 a 2020», «desde 2015», «hasta 2012», «cualquier año». */
export function yearsText(from: number | null, to: number | null): string {
  if (from && to) return from === to ? `${from}` : `${from} a ${to}`;
  if (from) return `desde ${from}`;
  if (to) return `hasta ${to}`;
  return "cualquier año";
}

/** «hasta $ 14.500.000», «hasta USD 9.500», or «sin presupuesto claro». */
export function budgetText(budget: number | null, currency: "ARS" | "USD" | null): string {
  if (!budget || !currency) return "sin presupuesto claro";
  return currency === "ARS" ? `hasta $ ${nf.format(budget)}` : `hasta USD ${nf.format(budget)}`;
}

/** «2 avisos publicados · 1 a menos de 50 km», «Ningún aviso publicado». */
export function supplyText(total: number, near: number): string {
  if (total === 0) return "Ningún aviso publicado";
  const head = total === 1 ? "1 aviso publicado" : `${nf.format(total)} avisos publicados`;
  return `${head} · ${near === 0 ? "ninguno" : nf.format(near)} a menos de 50 km`;
}

/** Few listings for the people who look for it: fewer listings than searches. */
export function isOpportunity(o: BuyOpportunity): boolean {
  return o.supplyTotal < o.searches;
}

/** /agencia/comprar/mercado for a row: model, make and the years asked for. */
export function buyMarketHref(o: Pick<BuyOpportunity, "make" | "model" | "yearFrom" | "yearTo">): string {
  const q = new URLSearchParams({ modelo: o.model });
  if (o.make) q.set("marca", o.make);
  if (o.yearFrom) q.set("desde", String(o.yearFrom));
  if (o.yearTo) q.set("hasta", String(o.yearTo));
  return `/agencia/comprar/mercado?${q.toString()}`;
}

export type BuyMarketQuery = { make: string | null; model: string; yearFrom: number | null; yearTo: number | null };

/** The market page's query, validated; null when there's no usable model. */
export function parseBuyMarketQuery(query: Record<string, string | string[] | undefined>): BuyMarketQuery | null {
  const one = (k: string) => (typeof query[k] === "string" ? (query[k] as string).trim() : "");
  const model = one("modelo");
  if (!model || model.length > 60) return null;
  const make = one("marca");
  const year = (k: string) => {
    const s = one(k);
    if (!/^\d{4}$/.test(s)) return null;
    const n = Number(s);
    return n >= 1950 && n <= 2100 ? n : null;
  };
  return { make: make && make.length <= 40 ? make : null, model, yearFrom: year("desde"), yearTo: year("hasta") };
}

// ---------------------------------------------------------------- sellers

export type DistanceBand = "lt10" | "10_25" | "25_50" | "50_100" | "unknown";
export type RequestStatus = "pending" | "accepted" | "declined" | "expired";

export type SellerRow = {
  ref: string;
  make: string | null;
  model: string | null;
  year: number | null;
  mileageKm: number | null;
  distance: DistanceBand;
  recent: boolean;
  requestId: number | null;
  requestStatus: RequestStatus | null;
  requestedOn: string | null;
  sharedName: string | null;
  sharedPhone: string | null;
  sharedEmail: string | null;
  canRequest: boolean;
};

const BANDS: DistanceBand[] = ["lt10", "10_25", "25_50", "50_100", "unknown"];
const STATUSES: RequestStatus[] = ["pending", "accepted", "declined", "expired"];
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

/** dealer_sellers() rows; a row without a valid ref is dropped. Contact only for an accepted request. */
export function parseSellers(raw: unknown): SellerRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((r) => {
    if (!r || typeof r !== "object") return [];
    const o = r as Record<string, unknown>;
    if (typeof o.ref !== "string" || !/^[0-9a-f]{32}$/.test(o.ref)) return [];
    const status = STATUSES.includes(o.request_status as RequestStatus) ? (o.request_status as RequestStatus) : null;
    const accepted = status === "accepted";
    return [{
      ref: o.ref,
      make: str(o.make),
      model: str(o.model),
      year: int(o.year),
      mileageKm: int(o.mileage_km_rounded),
      distance: BANDS.includes(o.distance_band as DistanceBand) ? (o.distance_band as DistanceBand) : "unknown",
      recent: o.recent === true,
      requestId: int(o.request_id),
      requestStatus: status,
      requestedOn: str(o.requested_on),
      sharedName: accepted ? str(o.shared_name) : null,
      sharedPhone: accepted ? str(o.shared_phone) : null,
      sharedEmail: accepted ? str(o.shared_email) : null,
      canRequest: o.can_request === true && status === null,
    }];
  });
}

/** «Fiat Palio 2012 · unos 85.000 km», or that we don't know. */
export function sellerCarText(s: Pick<SellerRow, "make" | "model" | "year" | "mileageKm">): string {
  const car = [s.make, s.model, s.year].filter(Boolean).join(" ");
  if (!car) return "Todavía no nos dijo qué auto vende";
  return s.mileageKm != null ? `${car} · unos ${nf.format(s.mileageKm)} km` : car;
}

export const DISTANCE_TEXT: Record<DistanceBand, string> = {
  lt10: "A menos de 10 km",
  "10_25": "A 10–25 km",
  "25_50": "A 25–50 km",
  "50_100": "A 50–100 km",
  unknown: "Sin zona",
};

/** What the dealer's request is waiting for, in words. */
export function requestStatusText(status: RequestStatus | null): string | null {
  if (status === "pending") return "Le avisamos que querés contactarlo. Decide el vendedor.";
  if (status === "accepted") return "Aceptó que lo contactes.";
  if (status === "declined") return "Prefirió que no lo contacten.";
  if (status === "expired") return "No respondió.";
  return null;
}

/** The sellers' RPC codes in words. Never echoes what was typed. */
export function sellerErrorText(code: string | null | undefined): string {
  switch (String(code ?? "").trim()) {
    case "sellers_off": return "Esto todavía no está disponible.";
    case "dealer_program_off": return "Esto todavía no está disponible.";
    case "not_approved": return "Falta que aprobemos tu agencia.";
    case "not_member": return "No tenés acceso a esta agencia.";
    case "not_signed_in": return "Entrá a tu cuenta para seguir.";
    case "seller_not_found": return "Este vendedor ya no está disponible.";
    case "rate_limited": return "Llegaste al tope de pedidos de hoy. Probá mañana.";
    case "seller_busy": return "Este vendedor ya recibió varios pedidos esta semana. Probá más adelante.";
    case "invalid_message": return "El mensaje puede tener hasta 300 letras.";
    default: return "No pudimos guardar. Probá de nuevo.";
  }
}
