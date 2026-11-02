/**
 * PAR-01: the words of the listing page's «Ver detalle» under the total cost
 * estimate. Since Juan's 02/11 request it is a compact summary: one row for
 * the transfer (DNRPA fee, stamp tax and forms as one range), one for the
 * annual patente, the total, and one footnote with the date of the official
 * values, the jurisdiction (named once) and what stays outside the total.
 * The sources, with the dollar used, go behind a single «Ver fuentes».
 * Pure: the component (components/app/cost-estimate.tsx) only lays it out.
 */
import { COST_ESTIMATE } from "@/lib/copy";
import {
  type CostConfig,
  type Estimate,
  type Jurisdiction,
  type MissingReason,
  missingSuffix,
  roundedTotals,
  termAmount,
  type TermCode,
} from "@/lib/cost-estimator";
import { formatRange, isoDayMonth, thousands } from "@/lib/format";

export type SellerKind = "private" | "dealer" | "inferred" | "none";
export type CostDetail = { rows: { label: string; amount: string }[]; footnote: string; sources: string[] };

const TRANSFER: TermCode[] = ["arancel", "sellos", "formularios"];

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

/** "CABA", "CABA o Provincia de Buenos Aires", "CABA, Provincia de Buenos Aires o resto del país". */
function joinOr(items: string[]): string {
  return items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")}${COST_ESTIMATE.or}${items[items.length - 1]}`;
}

export function jurisdictionNames(jurisdiction: Jurisdiction[]): string {
  return joinOr(jurisdiction.map((j) => COST_ESTIMATE.jurisdictionNames[j]));
}

function reasonText(reason: MissingReason | undefined, cfg: CostConfig): string {
  const template = COST_ESTIMATE.reasons[reason as keyof typeof COST_ESTIMATE.reasons] ?? COST_ESTIMATE.reasons.params;
  return fill(template, { year: cfg.blocks["patente.ba"]?.min_model_year ?? "" });
}

function source(cfg: CostConfig, block: string): { source: string; as_of: string } | null {
  const value = (cfg.blocks as Record<string, unknown>)[block];
  return value && typeof value === "object" ? (value as { source: string; as_of: string }) : null;
}

function sourceName(block: string): string {
  const names = COST_ESTIMATE.sourceNames;
  const [head, tail] = block.split(".");
  const where = tail && tail in COST_ESTIMATE.jurisdictionNames ? ` (${COST_ESTIMATE.jurisdictionNames[tail as Jurisdiction]})` : "";
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

/** The breakdown of an estimate with a price in pesos (p_ars), hence a jurisdiction. */
export function costDetail(estimate: Estimate, cfg: CostConfig): CostDetail {
  const rows: CostDetail["rows"] = [];
  const missing = new Map(estimate.missing.map((m) => [m.code, m.reason]));

  const transfer = estimate.terms.filter((t) => TRANSFER.includes(t.code));
  const transferMissing = TRANSFER.filter((c) => missing.has(c));
  if (transfer.length) {
    const sum = transfer.reduce((acc, t) => ({ min: acc.min + t.min, max: acc.max + t.max }), { min: 0, max: 0 });
    rows.push({ label: COST_ESTIMATE.transfer + missingSuffix(transferMissing), amount: termAmount(sum) });
  } else {
    rows.push({ label: COST_ESTIMATE.transfer, amount: reasonText(missing.get(transferMissing[0]), cfg) });
  }

  const patente = estimate.terms.find((t) => t.code === "patente");
  rows.push({
    label: fill(COST_ESTIMATE.patente, { year: cfg.blocks["patente.values_year"] ?? "" }),
    amount: patente ? termAmount(patente) : reasonText(missing.get("patente"), cfg),
  });

  const total = roundedTotals(estimate).ars;
  if (total) rows.push({ label: COST_ESTIMATE.total, amount: formatRange(total.min, total.max, "ARS") });

  // Gestoría first: it has no amount, the domain report's goes last, in its parentheses.
  const outside: string[] = [];
  const domain = estimate.extras.find((e) => e.code === "domain_report");
  if (estimate.extras.some((e) => e.code === "gestoria")) outside.push(COST_ESTIMATE.outsideGestoria);
  if (domain?.min != null && domain.max != null) {
    outside.push(fill(COST_ESTIMATE.outsideDomainReport, { amount: termAmount({ min: domain.min, max: domain.max }) }));
  }
  const footnote = fill(COST_ESTIMATE.footnote, {
    date: isoDayMonth(estimate.as_of),
    jurisdiction: jurisdictionNames(estimate.jurisdiction ?? []),
    outside: outside.length ? fill(COST_ESTIMATE.outside, { items: outside.join(COST_ESTIMATE.last) }) : "",
  });

  const blocks = [...new Set([...estimate.terms, ...estimate.extras].flatMap((t) => t.blocks))].filter((b) => b !== "transfer_base");
  const sources = blocks
    .map((b) => ({ b, s: source(cfg, b) }))
    .filter((x): x is { b: string; s: { source: string; as_of: string } } => x.s !== null)
    .map(({ b, s }) => fill(COST_ESTIMATE.sourceLine, { name: sourceName(b), source: s.source, date: isoDayMonth(s.as_of) }));
  const rate = estimate.rate;
  if (rate) {
    sources.push(
      rate.kind === "listing" || !rate.date
        ? fill(COST_ESTIMATE.rateListing, { rate: thousands(Math.round(rate.value)) })
        : fill(COST_ESTIMATE.rateQuote, {
            kind: COST_ESTIMATE.rateKinds[rate.kind ?? ""] ?? rate.kind ?? "",
            date: isoDayMonth(rate.date),
            rate: thousands(Math.round(rate.value)),
          }),
    );
  }
  return { rows, footnote, sources };
}
