/**
 * What a listing's description says about its price (worker/normalization/description_facts.py):
 * whether the price shown is the cash one, what the source published, and
 * the financing terms. Read from listings.description_facts.
 */
import { money, number } from "@/lib/format";

type Money = { amount: number; currency: string } | null | undefined;

type Facts = {
  financing?: {
    offered?: boolean;
    down_payment?: Money;
    installment?: Money;
    min_down_payment_pct?: number | null;
    max_financed_pct?: number | null;
    max_installments?: number | null;
  };
  price_check?: { published_kind?: string | null; effective_kind?: string | null; source?: string | null };
};

/** What the published price is, as the description calls it. */
const PUBLISHED_KIND: Record<string, string> = {
  list: "lista/permuta",
  cash: "contado",
  down_payment: "anticipo",
  installment: "cuota",
};

function facts(raw: unknown): Facts {
  return raw && typeof raw === "object" ? (raw as Facts) : {};
}

export function isCashPrice(raw: unknown): boolean {
  return facts(raw).price_check?.effective_kind === "cash";
}

export function publishedKind(raw: unknown): string | null {
  const kind = facts(raw).price_check?.published_kind;
  return kind ? (PUBLISHED_KIND[kind] ?? null) : null;
}

type PricedListing = {
  description_facts: unknown;
  price_partial?: boolean | null;
  price_source?: string | null;
  price?: number | null;
  currency?: string | null;
  price_usd?: number | null;
  price_published?: number | null;
  price_published_currency?: string | null;
};

/**
 * The price shown is a total from the description above the published number.
 * The worker only goes up from the published price when it took that number
 * for a down payment or an installment (a cash price from the text lies
 * below): as worker/pipeline/ingest.total_above_published. Across currencies,
 * at the rate the stored ARS price implies, else `usdRate` (ARS per USD, as
 * a snapshot's ARS price implies it); without one, unknown (false).
 */
export function totalAbovePublished(listing: PricedListing, usdRate?: number | null): boolean {
  const { price, currency, price_usd: usd, price_published: pub } = listing;
  if (listing.price_source !== "description" || !price || !pub) return false;
  const pubCurrency = listing.price_published_currency ?? currency;
  if (pubCurrency === currency) return Number(price) > Number(pub);
  if (!usd) return false;
  const rate = currency === "ARS" ? Number(price) / Number(usd) : usdRate || null;
  const pubUsd = pubCurrency === "USD" ? Number(pub) : pubCurrency === "ARS" && rate ? Number(pub) / rate : null;
  return pubUsd != null && Number(usd) > pubUsd;
}

/**
 * PAR-03: the published price is a down payment or an installment, not a
 * price (the description calls it so, it stands as partial, or the price
 * shown is a total above it): its drops are no price drops. As
 * worker/pipeline/ingest.published_partial.
 */
export function publishedIsPartial(listing: PricedListing, usdRate?: number | null): boolean {
  const kind = facts(listing.description_facts).price_check?.published_kind;
  return (
    kind === "down_payment" || kind === "installment" || Boolean(listing.price_partial) || totalAbovePublished(listing, usdRate)
  );
}

/** ARS per USD as the latest snapshot in pesos with a dollar value implies it (snapshots store the published price). */
export function snapshotUsdRate(snapshots: { currency: string | null; price: number | null; price_usd: number | null }[]): number | null {
  const s = [...snapshots].reverse().find((x) => x.currency === "ARS" && x.price && x.price_usd);
  return s ? Number(s.price) / Number(s.price_usd) : null;
}

export function financingOffered(raw: unknown): boolean {
  return Boolean(facts(raw).financing?.offered);
}

/** "anticipo desde USD 4.800 · hasta 36 cuotas de ARS 603.000 · entrega mínima 50%" */
export function financingTerms(raw: unknown): string | null {
  const f = facts(raw).financing;
  if (!f?.offered) return null;
  const parts: string[] = [];
  if (f.down_payment) parts.push(`anticipo desde ${money(f.down_payment.amount, f.down_payment.currency)}`);
  if (f.min_down_payment_pct) parts.push(`entrega mínima ${f.min_down_payment_pct}%`);
  if (f.max_financed_pct) parts.push(`financia hasta el ${f.max_financed_pct}%`);
  const installments = f.max_installments ? `hasta ${number(f.max_installments)} cuotas` : null;
  const installment = f.installment ? money(f.installment.amount, f.installment.currency) : null;
  if (installments && installment) parts.push(`${installments} de ${installment}`);
  else if (installments) parts.push(installments);
  else if (installment) parts.push(`cuotas de ${installment}`);
  return parts.length ? parts.join(" · ") : null;
}
