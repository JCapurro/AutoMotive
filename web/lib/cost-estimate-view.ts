/**
 * PAR-01: the words of the listing page's «Ver detalle» under the total cost
 * estimate: one row per term, then the notes (what is outside the total,
 * what is missing and why, which jurisdiction and seller were used, the
 * dollar, the rounding and the sources with their dates). Pure: the
 * component (components/app/cost-estimate.tsx) only lays it out.
 */
import { COST_ESTIMATE } from "@/lib/copy";
import { type CostConfig, type Estimate, type Jurisdiction, type MissingReason, termAmount, TERMS, type Zone } from "@/lib/cost-estimator";
import { isoDayMonth, thousands } from "@/lib/format";

export type SellerKind = "private" | "dealer" | "inferred" | "none";
export type CostDetail = { rows: { label: string; amount: string }[]; notes: string[]; sources: string[] };

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

/** "CABA", "CABA y resto del país", "CABA, Buenos Aires y resto del país". */
function joinAnd(items: string[]): string {
  return items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

export function jurisdictionNames(jurisdiction: Jurisdiction[]): string {
  return joinAnd(jurisdiction.map((j) => COST_ESTIMATE.jurisdictionNames[j]));
}

function fold(text: string | null): string {
  return (text ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/** 0.7 -> "0,70" */
function decimal2(n: number): string {
  const cents = Math.trunc(n * 100 + 1e-9);
  return `${Math.trunc(cents / 100)},${String(cents % 100).padStart(2, "0")}`;
}

function source(cfg: CostConfig, block: string): { source: string; as_of: string } | null {
  const value = (cfg.blocks as Record<string, unknown>)[block];
  return value && typeof value === "object" ? (value as { source: string; as_of: string }) : null;
}

function sourceName(block: string): string {
  const names = COST_ESTIMATE.sourceNames;
  const [head, tail] = block.split(".");
  const where = (tail && tail in COST_ESTIMATE.jurisdictionNames) ? ` (${COST_ESTIMATE.jurisdictionNames[tail as Jurisdiction]})` : "";
  if (head === "dnrpa") return names.arancel;
  if (head === "stamp_tax_pct") return names.sellos + where;
  if (head === "fixed_ars") return `${names.formularios} (${tail.replace("form_", "")})`;
  if (head === "patente") return names.patente + where;
  if (head === "vf_from_price_k") return names.vf;
  if (head === "mrpa_ars") return names.mrpa;
  if (head === "domain_report") return names.domain_report;
  if (head === "gestoria") return names.gestoria;
  return head;
}

export function costDetail(
  estimate: Estimate,
  cfg: CostConfig,
  zones: Zone[],
  from: "search" | "profile",
  sellerKind: SellerKind,
): CostDetail {
  const rows: CostDetail["rows"] = [];
  const notes: string[] = [];
  const priceLabel = estimate.price_label === "cash" ? COST_ESTIMATE.priceCash : COST_ESTIMATE.pricePublished;
  const pArs = `ARS ${thousands(estimate.p_ars ?? 0)}`;
  rows.push({
    label: priceLabel,
    amount: estimate.p_orig.currency === "USD" ? fill(COST_ESTIMATE.usdPrice, { usd: `USD ${thousands(estimate.p_orig.amount)}`, ars: pArs }) : pArs,
  });
  const jurisdiction = estimate.jurisdiction ?? [];
  for (const t of estimate.terms) {
    const label =
      t.code === "sellos"
        ? fill(COST_ESTIMATE.terms.sellos, { jurisdiction: jurisdictionNames(jurisdiction) })
        : t.code === "patente"
          ? fill(COST_ESTIMATE.terms.patente, { year: cfg.blocks["patente.values_year"] ?? "" })
          : COST_ESTIMATE.terms[t.code];
    rows.push({ label, amount: termAmount(t) });
  }

  for (const e of estimate.extras) {
    if (e.code === "domain_report" && e.min != null && e.max != null) notes.push(fill(COST_ESTIMATE.domainReport, { amount: termAmount({ min: e.min, max: e.max }) }));
    if (e.code === "gestoria") notes.push(COST_ESTIMATE.gestoria);
  }

  // What is missing, grouped by reason: «Sellos y patente: tu búsqueda no tiene zona en Argentina.»
  const byReason = new Map<MissingReason, string[]>();
  for (const m of estimate.missing) {
    if (m.code === "fx") continue;
    byReason.set(m.reason, [...(byReason.get(m.reason) ?? []), m.code]);
  }
  for (const [reason, codes] of byReason) {
    const names = TERMS.filter((c) => codes.includes(c)).map((c, i) => (i === 0 ? COST_ESTIMATE.missingNames[c] : COST_ESTIMATE.names[c]));
    const why = fill(COST_ESTIMATE.reasons[reason as keyof typeof COST_ESTIMATE.reasons] ?? "", { year: cfg.blocks["patente.ba"]?.min_model_year ?? "" });
    notes.push(fill(COST_ESTIMATE.missingLine, { names: joinAnd(names), reason: why }));
  }

  if (jurisdiction.length) {
    const labels = zones.map((z) => z.label).filter((l): l is string => Boolean(l)).map((l) => `«${l}»`);
    const fromText = from === "search" ? COST_ESTIMATE.fromSearch : COST_ESTIMATE.fromProfile;
    notes.push(
      fill(jurisdiction.length > 1 ? COST_ESTIMATE.jurisdictionMany : COST_ESTIMATE.jurisdiction, {
        jurisdiction: jurisdictionNames(jurisdiction),
        from: fromText,
        where: labels.length ? fill(COST_ESTIMATE.where, { labels: joinAnd(labels) }) : "",
        all: jurisdiction.length === 2 ? COST_ESTIMATE.coversTwo : COST_ESTIMATE.coversAll,
      }),
    );
    if (zones.some((z) => fold(z.label) === "amba")) notes.push(COST_ESTIMATE.amba);
    if (jurisdiction.includes("rest")) notes.push(COST_ESTIMATE.rest);
  }
  notes.push(fill(COST_ESTIMATE.seller, { kind: COST_ESTIMATE.sellerKinds[sellerKind] }));

  const k = cfg.blocks.vf_from_price_k;
  if (k && estimate.terms.some((t) => t.code === "patente")) notes.push(fill(COST_ESTIMATE.vf, { k: `${decimal2(k.min)}–${decimal2(k.max)}` }));

  const rate = estimate.rate;
  if (!rate) notes.push(COST_ESTIMATE.noRate);
  else if (rate.kind === "listing" || !rate.date) notes.push(fill(COST_ESTIMATE.rateListing, { rate: thousands(Math.round(rate.value)) }));
  else notes.push(fill(COST_ESTIMATE.rateQuote, { kind: COST_ESTIMATE.rateKinds[rate.kind ?? ""] ?? rate.kind ?? "", date: isoDayMonth(rate.date), rate: thousands(Math.round(rate.value)) }));
  notes.push(COST_ESTIMATE.rounding);
  notes.push(fill(COST_ESTIMATE.asOf, { date: isoDayMonth(estimate.as_of) }));

  const blocks = [...new Set([...estimate.terms, ...estimate.extras].flatMap((t) => t.blocks))].filter((b) => b !== "transfer_base");
  const sources = blocks
    .map((b) => ({ b, s: source(cfg, b) }))
    .filter((x): x is { b: string; s: { source: string; as_of: string } } => x.s !== null)
    .map(({ b, s }) => fill(COST_ESTIMATE.sourceLine, { name: sourceName(b), source: s.source, date: isoDayMonth(s.as_of) }));
  return { rows, notes, sources };
}
