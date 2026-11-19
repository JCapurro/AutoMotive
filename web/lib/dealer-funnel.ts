import { z } from "zod";

import { dealerErrorText } from "@/lib/dealer-program";

/**
 * The sales-channel funnel (migration 20261230120000_dealer_funnel.sql):
 * admin_dealer_funnel() for /admin/agencias/embudo and my_dealer_reach() for
 * the agency's home. Pure: parsing, the steps with their rates and the
 * agency's sentence. Counts only, never a buyer.
 */

const count = z.number().int().nonnegative();

export const funnelCountsSchema = z.object({
  stock: count,
  visible: count,
  loaded: count,
  matched_cars: count,
  matched_searches: count,
  alerts: count,
  alerted_cars: count,
  people: count,
  leads: count,
  contacted: count,
  reserved: count,
  sold: count,
  lost: count,
  still_new: count,
  sales_via_ese_auto: count,
  sales_elsewhere: count,
});
export type FunnelCounts = z.infer<typeof funnelCountsSchema>;

export const adminFunnelSchema = z.object({
  start: z.string(),
  end: z.string(),
  total: funnelCountsSchema,
  dealers: z.array(funnelCountsSchema.extend({ dealer_id: z.number().int(), name: z.string(), approved: z.boolean(), status: z.string() })),
});
export type AdminFunnel = z.infer<typeof adminFunnelSchema>;
export type DealerFunnelRow = AdminFunnel["dealers"][number];

export function parseAdminFunnel(raw: unknown): AdminFunnel | null {
  const parsed = adminFunnelSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

/** numerator / denominator in %, or null without a denominator. */
export function stepRate(numerator: number, denominator: number): number | null {
  return denominator > 0 ? (numerator / denominator) * 100 : null;
}

export function rateText(rate: number | null): string {
  if (rate === null) return "—";
  if (rate > 0 && rate < 1) return "<1 %";
  return `${Math.round(rate)} %`;
}

export type FunnelStep = {
  key: string;
  label: string;
  value: number;
  /** The rate against the step it hangs from (its label in `of`), or null for the first one. */
  rate: number | null;
  of: string | null;
  hint: string;
};

/**
 * The steps in order. Rates hang from the step before in the same unit: cars
 * (stock → visible → matched → in an alert), people (reached → leads) and
 * leads (contacted → reserved → bought, nested by furthest_status). Declared
 * sales: the share that came through Ese Auto.
 */
export function funnelSteps(c: FunnelCounts): FunnelStep[] {
  const declared = c.sales_via_ese_auto + c.sales_elsewhere;
  return [
    { key: "stock", label: "Autos en stock", value: c.stock, rate: null, of: null, hint: `Hoy, sin los archivados. ${c.loaded} cargados en el período.` },
    { key: "visible", label: "Visibles para compradores", value: c.visible, rate: stepRate(c.visible, c.stock), of: "del stock", hint: "Hoy: disponibles, confirmados y con la agencia aprobada." },
    { key: "matched", label: "Coincidieron con una búsqueda", value: c.matched_cars, rate: stepRate(c.matched_cars, c.visible), of: "de los visibles", hint: `Primera coincidencia en el período, con ${c.matched_searches} ${c.matched_searches === 1 ? "búsqueda" : "búsquedas"}.` },
    { key: "alerted", label: "Llegaron en una alerta", value: c.alerted_cars, rate: stepRate(c.alerted_cars, c.matched_cars), of: "de los que coincidieron", hint: `${c.alerts} ${c.alerts === 1 ? "alerta enviada" : "alertas enviadas"} (una por persona y auto).` },
    { key: "people", label: "Compradores alcanzados", value: c.people, rate: null, of: null, hint: "Personas distintas que recibieron un auto de agencia." },
    { key: "leads", label: "Consultas", value: c.leads, rate: stepRate(c.leads, c.people), of: "de los alcanzados", hint: `«Quiero que me contacten». ${c.still_new} sin responder, ${c.lost} no avanzaron.` },
    { key: "contacted", label: "Contactadas", value: c.contacted, rate: stepRate(c.contacted, c.leads), of: "de las consultas", hint: "La agencia las marcó contactadas o más." },
    { key: "reserved", label: "Reservaron", value: c.reserved, rate: stepRate(c.reserved, c.contacted), of: "de las contactadas", hint: "Reservaron o compraron." },
    { key: "sold", label: "Compraron", value: c.sold, rate: stepRate(c.sold, c.reserved), of: "de las que reservaron o compraron", hint: "La agencia marcó «Compró»." },
    { key: "sales", label: "Ventas por Ese Auto", value: c.sales_via_ese_auto, rate: stepRate(c.sales_via_ese_auto, declared), of: "de las ventas declaradas", hint: `Lo dijo la agencia al marcar la venta. ${c.sales_elsewhere} por otro lado.` },
  ];
}

// ---------------------------------------------------------------- the agency

const peopleSchema = z.union([z.literal("few"), count]);

export const reachSchema = z.object({
  since: z.string(),
  min_count: count,
  people: peopleSchema,
  leads: count,
  sales_via_ese_auto: count,
  pending_sales: z.array(z.object({
    item_id: z.number().int().nullable(),
    lead_id: z.number().int().nullable(),
    vehicle: z.string(),
    sold_at: z.string().nullable(),
  })),
});
export type DealerReach = z.infer<typeof reachSchema>;
export type PendingSale = DealerReach["pending_sales"][number];

export function parseReach(raw: unknown): DealerReach | null {
  const parsed = reachSchema.safeParse(raw);
  if (!parsed.success) return null;
  const r = parsed.data;
  // The SQL already rounds; never print 1 or 2 even if a number slips through.
  if (typeof r.people === "number" && r.people > 0 && r.people < Math.max(3, r.min_count)) return { ...r, people: "few" };
  return r;
}

const consultas = (n: number) => (n === 1 ? "1 consulta" : `${n} consultas`);

/** «Este mes tus autos llegaron a 12 personas y recibiste 3 consultas.» */
export function reachSentence(r: Pick<DealerReach, "people" | "leads">): string {
  if (r.people === 0) {
    return r.leads > 0 ? `Este mes recibiste ${consultas(r.leads)}.` : "Este mes tus autos todavía no llegaron a ningún comprador.";
  }
  const who = r.people === "few" ? "pocas personas" : `${r.people} personas`;
  return r.leads > 0
    ? `Este mes tus autos llegaron a ${who} y recibiste ${consultas(r.leads)}.`
    : `Este mes tus autos llegaron a ${who}. Todavía no recibiste consultas.`;
}

export function salesSentence(n: number): string | null {
  if (n <= 0) return null;
  return n === 1 ? "1 venta vino por Ese Auto." : `${n} ventas vinieron por Ese Auto.`;
}

export function saleErrorText(message: string | null | undefined): string {
  const code = String(message ?? "").trim();
  if (code === "not_sold") return "Primero marcalo como vendido.";
  if (code === "invalid_sale") return "No pudimos guardar tu respuesta. Probá de nuevo.";
  return dealerErrorText(message);
}
