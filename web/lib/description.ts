import { FUEL, TRANSMISSION } from "./copy";
import { km, money } from "./format";
import type { PriceRef } from "./types";

type RecordValue = Record<string, unknown>;
export type DescriptionListing = {
  title?: string | null;
  description?: string | null;
  description_facts?: unknown;
  year?: number | null;
  mileage_km?: number | null;
  trim?: string | null;
  transmission?: string | null;
  fuel?: string | null;
  price_partial?: boolean | null;
};
export type SellerStatement = { field: string; label: string; value: string; quotes: string[]; conflict: boolean };

function record(value: unknown): RecordValue {
  return value != null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
}
function folded(value: string): string { return value.normalize("NFC").toLocaleLowerCase("es").replace(/\s+/g, " ").trim(); }

const LABEL: Record<string, string> = {
  trim: "Versión", engine: "Motor", equipment: "Equipamiento", single_owner: "Dueños",
  service_history: "Mantenimiento", timing_belt_changed: "Distribución", tires_condition: "Cubiertas",
  commercial_use: "Uso comercial", repairs: "Reparaciones", damage_mentioned: "Daños o choques",
  damage_details: "Detalle de daños", vtv_current: "VTV", documentation: "Documentación",
  accepts_trade_in: "Permuta", negotiable: "Negociación", urgent_sale: "Venta urgente", sale_reason: "Motivo de venta",
  transmission: "Caja", fuel: "Combustible", year: "Año", mileage_km: "Kilometraje",
  cash_price: "Precio de contado", list_price: "Precio de lista", down_payment: "Anticipo", installment_amount: "Cuota",
};
const BOOL: Record<string, [string, string]> = {
  single_owner: ["Declara ser único dueño", "Indica que tuvo más de un dueño"],
  service_history: ["Declara historial de mantenimiento", "Indica que no tiene historial de mantenimiento"],
  timing_belt_changed: ["Declara que la distribución está hecha", "Indica que la distribución no está hecha"],
  commercial_use: ["Declara uso comercial", "Declara que no tuvo uso comercial"],
  damage_mentioned: ["Menciona daños o antecedentes de choques", "Niega daños o choques en el texto citado"],
  vtv_current: ["Declara VTV vigente", "Indica que no tiene VTV vigente"],
  accepts_trade_in: ["Acepta permuta", "No acepta permuta"],
  negotiable: ["Precio conversable", "Precio fijo"], urgent_sale: ["Declara urgencia de venta", "Declara que no tiene apuro"],
};

export function sellerStatements(listing: DescriptionListing): SellerStatement[] {
  const facts = record(listing.description_facts);
  if (facts.source !== "llm" || facts.v !== 2) return [];
  const claims = record(facts.claims);
  const text = folded(`${listing.title ?? ""}\n${listing.description ?? ""}`);
  const evidence = Array.isArray(facts.evidence) ? facts.evidence.map(record) : [];
  const fields = Object.keys(LABEL);
  return fields.flatMap((field) => {
    const quotes = [...new Set(evidence.filter((e) => e.field === field && typeof e.quote === "string"
      && e.quote.trim() && text.includes(folded(e.quote))).map((e) => e.quote as string))];
    if (!quotes.length) return [];
    let raw = claims[field] ?? facts[field];
    if (["cash_price", "list_price", "down_payment", "installment_amount"].includes(field)) {
      const kind = { cash_price: "cash", list_price: "list", down_payment: "down_payment", installment_amount: "installment" }[field];
      const amounts = Array.isArray(facts.amounts) ? facts.amounts.map(record) : [];
      const amount = amounts.find((a) => a.kind === kind && typeof a.amount === "number");
      raw = amount ? money(amount.amount as number, typeof amount.currency === "string" ? amount.currency : null) : null;
    }
    let value: string | null = null;
    if (typeof raw === "boolean" && BOOL[field]) value = BOOL[field][raw ? 0 : 1];
    else if (field === "equipment" && Array.isArray(raw)) {
      value = raw.filter((s): s is string => typeof s === "string" && quotes.some((q) => folded(q).includes(folded(s)))).join(", ") || null;
    } else if (field === "mileage_km" && typeof raw === "number") value = km(raw);
    else if (field === "year" && typeof raw === "number") value = String(raw);
    else if (field === "transmission" && (raw === "manual" || raw === "automatic")) value = TRANSMISSION[raw];
    else if (field === "fuel" && typeof raw === "string") value = FUEL[raw] ?? raw;
    else if (typeof raw === "string" && raw.trim()) value = raw;
    if (value == null) return [];
    const current = listing[field as keyof DescriptionListing];
    const different = typeof current === "string" && typeof raw === "string"
      ? folded(current) !== folded(raw) : current !== raw;
    const conflict = ["year", "mileage_km", "trim", "transmission", "fuel"].includes(field)
      && current != null && different;
    return [{ field, label: LABEL[field], value, quotes, conflict }];
  });
}

export function priceContext(listing: DescriptionListing, refs: PriceRef | null, minN: number): { intro: string; factors: string[] } {
  const statements = sellerStatements(listing);
  const byField = Object.fromEntries(statements.map((s) => [s.field, s]));
  const claims = record(record(listing.description_facts).claims);
  const factors: string[] = [];
  if (byField.damage_mentioned && claims.damage_mentioned === true) factors.push("Los daños o antecedentes de choques mencionados podrían influir en el precio. Falta conocer su alcance y el costo de lo pendiente.");
  if (byField.commercial_use && claims.commercial_use === true) factors.push("El uso comercial declarado puede influir en el desgaste y la valoración. Conviene conocer cuánto tiempo tuvo ese uso.");
  if (byField.urgent_sale && claims.urgent_sale === true) factors.push("El vendedor declara urgencia de venta; podría influir en lo que pide o acepta, pero no confirma el motivo de la diferencia.");
  if (byField.negotiable && claims.negotiable === true) factors.push("El precio es conversable según el aviso. La comparación usa el precio publicado o de contado, no un descuento supuesto.");
  if (byField.service_history && claims.service_history === true) factors.push("El mantenimiento declarado puede ser un punto a favor si se acredita con comprobantes.");
  if (byField.timing_belt_changed && claims.timing_belt_changed === true) factors.push("La distribución declarada como hecha puede evitar un gasto próximo; conviene confirmar fecha, kilometraje y comprobante.");
  if (byField.timing_belt_changed && claims.timing_belt_changed === false) factors.push("La distribución pendiente puede implicar un gasto. Falta confirmar qué trabajo necesita y cuánto cuesta.");
  if (byField.repairs && claims.damage_mentioned !== true) factors.push("El vendedor menciona reparaciones. Conviene distinguir los trabajos terminados de los pendientes y pedir comprobantes.");
  if (byField.tires_condition) factors.push("El estado o cambio de cubiertas declarado puede influir en los gastos próximos. Conviene confirmar cuándo se cambiaron y su estado actual.");
  if (byField.service_history && claims.service_history === false) factors.push("La falta de historial de mantenimiento declarado limita lo que sabemos del auto; conviene pedir información antes de valorar su estado.");
  if (byField.vtv_current && claims.vtv_current === false) factors.push("La VTV pendiente puede requerir trámites o trabajos; el aviso no alcanza para estimar su costo.");
  if (byField.single_owner && claims.single_owner === true) factors.push("El vendedor declara dueño único. Puede ayudar a reconstruir el historial, sin probar por sí solo el estado del auto.");
  if (byField.equipment) factors.push("El equipamiento declarado puede influir en la comparación. Conviene comparar versiones equivalentes.");
  const enough = refs != null && refs.n >= minN && refs.median != null && refs.diff_pct != null;
  const intro = listing.price_partial
    ? "El precio parece parcial. Primero hay que confirmar el total antes de compararlo con otros autos."
    : !enough ? "Faltan publicaciones comparables suficientes para evaluar la diferencia de precio. Estos datos aportan contexto."
    : "La diferencia de precio se calcula con publicaciones comparables. Estas afirmaciones del vendedor aportan contexto; no prueban por qué pide ese valor.";
  return { intro, factors };
}
