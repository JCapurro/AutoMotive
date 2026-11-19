/**
 * app_config.dealer_program (docs/superpowers/specs/2026-11-18-agencias-design.md §1):
 * the agencies' panel and sales channel. Read the same way as public.dealer_program()
 * and worker/intelligence/config.py dealer_program(): anything missing or invalid
 * falls back to the default, and both switches are off unless explicitly true.
 */
export type DealerProgram = {
  enabled: boolean;
  channelEnabled: boolean;
  manualConfirmDays: number;
  /** Never below 3: a count of 1 or 2 searches is never shown. */
  demandMinCount: number;
  /** Fase 1: alerts to the agency by email, at most one summary every alertsEveryHours (6 to 168). */
  alertsEnabled: boolean;
  alertsEveryHours: number;
  /** Fase 1: stock from a photo or a PDF of the list (an LLM call, costs per use), photoImportDailyLimit per agency and day. */
  photoImportEnabled: boolean;
  photoImportDailyLimit: number;
};

export const DEFAULT_DEALER_PROGRAM: DealerProgram = {
  enabled: false, channelEnabled: false, manualConfirmDays: 7, demandMinCount: 3,
  alertsEnabled: false, alertsEveryHours: 24, photoImportEnabled: false, photoImportDailyLimit: 5,
};

function wholeIn(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max ? value : fallback;
}

export function parseDealerProgram(raw: unknown): DealerProgram {
  const v = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  return {
    enabled: v.enabled === true,
    channelEnabled: v.channel_enabled === true,
    manualConfirmDays: wholeIn(v.manual_confirm_days, 1, 60, 7),
    demandMinCount: wholeIn(v.demand_min_count, 3, 50, 3),
    alertsEnabled: v.alerts_enabled === true,
    alertsEveryHours: wholeIn(v.alerts_every_hours, 6, 168, 24),
    photoImportEnabled: v.photo_import_enabled === true,
    photoImportDailyLimit: wholeIn(v.photo_import_daily_limit, 1, 50, 5),
  };
}

/** The sales channel is on only with both switches on. */
export function channelOn(p: DealerProgram): boolean {
  return p.enabled && p.channelEnabled;
}

/** The field names of the RPC codes invalid_dealer:<campo> and invalid_item:<campo>, in words. */
const FIELD: Record<string, string> = {
  name: "el nombre",
  locality_label: "la localidad",
  lat: "la localidad",
  lon: "la localidad",
  phone: "el teléfono",
  whatsapp: "el WhatsApp",
  contact_email: "el email",
  address_text: "la dirección",
  profile_links: "los links",
  profile_url: "el link",
  seller_name_hint: "cómo figura tu nombre",
  make: "la marca",
  model: "el modelo",
  trim: "la versión",
  year: "el año",
  mileage_km: "los km",
  price: "el precio",
  currency: "la moneda",
  transmission: "la caja",
  fuel: "el combustible",
  color: "el color",
  body_type: "la carrocería",
  title: "el título",
  description: "la descripción",
  images: "las fotos",
  in_stock_since: "la fecha de ingreso",
  purchase_price: "lo que pagaste",
  purchase_currency: "la moneda de lo que pagaste",
  notes: "las notas",
  alerts_email: "los avisos",
};

/** The code an RPC raised (P0001 with the code as message), from a PostgREST error message. */
export function rpcCode(message: string | null | undefined): string {
  return String(message ?? "").trim();
}

/** §6.6: an RPC error of the agencies' panel, in words. Never echoes what the person typed. */
export function dealerErrorText(message: string | null | undefined): string {
  const code = rpcCode(message);
  if (code === "dealer_program_off") return "Esto todavía no está disponible.";
  if (code === "not_member") return "No tenés acceso a esta agencia.";
  if (code === "not_signed_in") return "Entrá a tu cuenta para seguir.";
  if (code === "already_member") return "Ya tenés una agencia.";
  if (code === "too_many_rows") return "La planilla tiene más de 500 autos.";
  if (code === "item_not_found") return "No encontramos ese auto en tu stock.";
  if (code === "lead_not_found") return "No encontramos esa consulta.";
  if (code === "invalid_status") return "Ese estado no se puede elegir.";
  if (code === "invalid_source") return "Elegí una fuente de la lista.";
  if (code === "photo_import_off") return "La carga por foto todavía no está disponible.";
  if (code === "photo_import_limit") return "Llegaste al máximo de fotos o PDF por hoy. Probá mañana o subí la planilla.";
  if (code === "file_too_big") return "El archivo es muy grande: hasta 4 MB.";
  if (code === "invalid_file:type") return "Subí una foto (JPG, PNG o WebP) o un PDF.";
  if (code.startsWith("invalid_file")) return "No pudimos leer el archivo. Probá con otro.";
  if (code === "llm_rate_limited") return "Pediste muchas lecturas en la última hora. Probá en un rato.";
  const field = /^invalid_(?:dealer|item):(?:(\d+):)?([a-z_]+)$/.exec(code);
  if (field) {
    const what = FIELD[field[2]] ?? "los datos";
    return field[1] ? `Revisá ${what} en la fila ${field[1]}.` : `Revisá ${what}.`;
  }
  return "No pudimos guardar. Probá de nuevo.";
}
