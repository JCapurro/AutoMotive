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
