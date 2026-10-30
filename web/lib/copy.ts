/**
 * Every user-facing label of the web that comes from the data model.
 * Prudent price language (§19): "precio publicado", "mercado observado",
 * "publicaciones comparables" — never the terms in FORBIDDEN_TERMS
 * (lib/copy.test.ts lints the app for them, like the worker does).
 */
import type { Database } from "@/types/database";

type Enums = Database["public"]["Enums"];
export type Level = Enums["match_level"];
export type InteractionStatus = Enums["interaction_status"];
export type RejectionReason = Enums["rejection_reason"];
export type Influence = Enums["purchase_influence"];
export type Frequency = Enums["notify_frequency"];

export const FORBIDDEN_TERMS = ["vale", "valor real", "precio real", "tasacion", "tasación", "tasado"];

// §20
export const LEVEL: Record<Level, { emoji: string; label: string; short: string }> = {
  high: { emoji: "🔥", label: "Alta oportunidad", short: "Alta" },
  good: { emoji: "🟢", label: "Buena coincidencia", short: "Buena" },
  match: { emoji: "🟡", label: "Coincidencia", short: "Coincidencia" },
  low: { emoji: "⚪", label: "Baja prioridad", short: "Baja" },
};
export const LEVELS: Level[] = ["high", "good", "match", "low"];

// §26
export const STATUS: Record<InteractionStatus, string> = {
  new: "Nuevo",
  seen: "Visto",
  interested: "Guardada",
  discarded: "Descartado",
  contacted: "Contactado",
  visit_scheduled: "Visita agendada",
  purchased: "Comprado",
};
export const STATUSES: InteractionStatus[] = [
  "new",
  "seen",
  "interested",
  "contacted",
  "visit_scheduled",
  "discarded",
  "purchased",
];

// X-01: the "Seguimiento" block, its purchase dialog and the filters by status.
export const TRACKING = {
  title: "Seguimiento",
  status: "Estado",
  note: "Tu nota",
  notePlaceholder: "Qué hablaste, cuándo es la visita, qué falta revisar",
  saveNote: "Guardar nota",
  editNote: "Editar nota",
  notePrivacy: "La nota es privada: no se la mostramos al vendedor ni a otros usuarios.",
  purchasedLocked: "Marcaste que la compraste. Por ahora la compra no se puede deshacer desde acá.",
  purchaseTitle: "¿La compraste?",
  purchaseDescription: "Es definitivo: después no vas a poder cambiar el estado desde acá. Precio, moneda y fecha son opcionales.",
  purchasePrice: "Precio que pagaste",
  purchasePriceInvalid: "Escribí el precio sin centavos, solo números: por ejemplo 9800 o 9.800.",
  purchaseCurrency: "Moneda",
  purchaseDate: "Fecha de compra",
  purchaseConfirm: "Marcar como comprada",
  cancel: "Cancelar",
} as const;

/** Saved listings' and results' filters by follow-up status, with what an empty one says. */
export const FOLLOW_FILTERS = ["contacted", "visit_scheduled", "purchased"] as const;
export type FollowFilter = (typeof FOLLOW_FILTERS)[number];
export const FOLLOW_LABEL: Record<FollowFilter, string> = {
  contacted: "Contactados",
  visit_scheduled: "Visita agendada",
  purchased: "Comprados",
};
export const FOLLOW_EMPTY: Record<FollowFilter, string> = {
  contacted: "No marcaste publicaciones como contactadas.",
  visit_scheduled: "No marcaste publicaciones con visita agendada.",
  purchased: "No marcaste publicaciones como compradas.",
};

// §27
export const REJECTION: Record<RejectionReason, string> = {
  too_expensive: "Demasiado caro",
  too_many_km: "Demasiados kilómetros",
  wrong_trim: "Mala versión",
  location: "Ubicación",
  automatic: "Automático",
  seller: "Vendedor",
  apparent_condition: "Estado aparente",
  documentation: "Documentación",
  other: "Otro",
};

// §38
export const INFLUENCE: Record<Influence, string> = {
  a_lot: "Mucho",
  some: "Algo",
  little: "Poco",
  none: "No",
};

// §32
export const FREQUENCY: Record<Frequency, { label: string; hint: string }> = {
  immediate: { label: "Inmediata", hint: "Te avisamos cuando aparece." },
  daily: { label: "Diaria", hint: "Un resumen por día." },
};

export const MIN_LEVEL_OPTIONS: { value: Level; label: string }[] = [
  { value: "high", label: "Solo altas oportunidades" },
  { value: "good", label: "Buenas coincidencias o mejores" },
  { value: "match", label: "Cualquier coincidencia" },
  { value: "low", label: "Todo lo que coincida" },
];

export const TRANSMISSION: Record<string, string> = { manual: "Manual", automatic: "Automática" };
export const SELLER: Record<string, string> = { private: "Particular", dealer: "Concesionaria" };
/** F-02: listings.dealer_inferred, a seller with many cars in the same source (lib/seller.ts). */
export const SELLER_INFERRED = "Posible agencia";
/** F-02: under the search form's «Vendedor» when it prefers a dealer. */
export const SELLER_FORM_HINT = "Incluye posibles agencias.";
export const FUEL: Record<string, string> = {
  nafta: "Nafta",
  diesel: "Diésel",
  gnc: "GNC",
  hibrido: "Híbrido",
  electrico: "Eléctrico",
};

// docs/CARROCERIA.md: the same codes and order as the database, the worker
// (normalization/body_type.py) and the LLM.
export const BODY_TYPE_CODES = [
  "sedan", "hatchback", "suv", "pickup", "rural", "monovolumen", "coupe", "convertible", "utilitario",
] as const;
export type BodyType = (typeof BODY_TYPE_CODES)[number];
export const BODY_TYPE: Record<BodyType, string> = {
  sedan: "Sedán",
  hatchback: "Hatchback",
  suv: "SUV",
  pickup: "Pick-up",
  rural: "Rural",
  monovolumen: "Monovolumen",
  coupe: "Coupé",
  convertible: "Convertible",
  utilitario: "Utilitario",
};

export function isBodyType(value: unknown): value is BodyType {
  return typeof value === "string" && (BODY_TYPE_CODES as readonly string[]).includes(value);
}

/** The known codes of a list, once each, in the canonical order. */
export function bodyTypeCodes(codes: readonly unknown[] | null | undefined): BodyType[] {
  return BODY_TYPE_CODES.filter((code) => codes?.includes(code));
}

/** ["suv", "pickup"] → "SUV o Pick-up"; three or more: "Sedán, SUV o Pick-up". */
export function bodyTypesText(codes: readonly unknown[] | null | undefined): string {
  const labels = bodyTypeCodes(codes).map((code) => BODY_TYPE[code]);
  return labels.length > 1 ? `${labels.slice(0, -1).join(", ")} o ${labels[labels.length - 1]}` : (labels[0] ?? "");
}

export const CHANNEL: Record<string, string> = { telegram: "Telegram", email: "Email", web: "Web" };

// "¿Por qué apareció?" (§23): what an ok reason says, by match_reasons key.
export const REASON_OK: Record<string, string> = {
  model: "Modelo buscado",
  year: "Año dentro del rango",
  price: "Dentro del presupuesto",
  km: "Kilometraje compatible",
  transmission: "Caja buscada",
  fuel: "Combustible buscado",
  body_type: "Carrocería buscada",
  location: "Zona compatible",
  source: "Fuente elegida",
  trim: "Versión buscada",
  km_target: "Km por debajo del objetivo",
  price_target: "Precio por debajo del objetivo",
  seller_type: "Tipo de vendedor preferido",
  colors: "Color preferido",
  max_distance_km: "Distancia preferida",
};
export const REASON_NAME: Record<string, string> = {
  model: "Modelo",
  year: "Año",
  price: "Precio",
  km: "Kilometraje",
  transmission: "Caja",
  fuel: "Combustible",
  body_type: "Carrocería",
  location: "Ubicación",
  source: "Fuente",
  trim: "Versión",
  km_target: "Km objetivo",
  price_target: "Precio objetivo",
  seller_type: "Vendedor",
  colors: "Color",
  max_distance_km: "Distancia",
};
export const REASON_ORDER = Object.keys(REASON_OK);

// Opportunity Score components (sección 6.3).
export const COMPONENT: Record<string, string> = {
  price: "Precio",
  match: "Coincidencia con la búsqueda",
  km: "Kilometraje",
  trim: "Versión",
  recency: "Antigüedad de la publicación",
  completeness: "Datos informados",
};
export const COMPONENTS = Object.keys(COMPONENT);

// Price Intelligence cascade (sección 6.2).
export const COMPARABLE_LEVEL: Record<string, string> = {
  trim_transmission: "misma versión y caja",
  transmission: "misma caja",
  model: "mismo modelo",
};

// Watchlist events (§30).
export const SNAPSHOT_CHANGE: Record<string, string> = {
  new: "Detectada",
  price: "Cambió el precio",
  mileage: "Cambió el kilometraje",
  description: "Cambió la descripción",
  images: "Cambiaron las fotos",
  attrs: "Cambiaron los datos",
};

// Notification kinds (§22), as the worker titles them.
export const NOTIFICATION_TITLE: Record<string, string> = {
  new_match: "🚗 Nuevo vehículo encontrado",
  opportunity: "🔥 Nueva oportunidad",
  price_drop: "📉 Bajó de precio",
  listing_gone: "🚫 Ya no está disponible",
  digest: "🗓 Tu resumen del día",
};

// §25: the part every message starts with, shown while a match has no
// stored questions yet (rows scored before F4 get them on the next re-score).
export const BASE_SELLER_QUESTIONS = "Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular?";

// PAR-01: the total cost estimate (lib/cost-estimator.ts returns codes). The
// header lines are the worker's (worker/intelligence/copy.py TOTAL_COST).
export const COST_ESTIMATE = {
  line: "Costo total estimado{suffix}: {usd} ({ars})",
  lineNoUsd: "Costo total estimado{suffix}: {ars} (sin dólar del día)",
  lineNoFx: "Costo total estimado: sin dólar del día, no se puede estimar",
  suffix: " (sin {items})",
  last: " ni ",
  names: { arancel: "arancel", sellos: "sellos", formularios: "formularios", patente: "patente" },
  toggle: "Ver detalle",
  priceCash: "Precio de contado",
  pricePublished: "Precio publicado",
  usdPrice: "{usd} = {ars}",
  terms: {
    arancel: "Arancel de transferencia DNRPA",
    sellos: "Sellos de {jurisdiction}",
    formularios: "Formularios 08 y 12",
    patente: "Patente anual (valores {year})",
  },
  domainReport: "Fuera del total: informe de dominio {amount}, recomendado antes de señar.",
  gestoria: "Gestor opcional: sin tarifa oficial, se pacta con el gestor.",
  jurisdiction: "Patente y sellos de {jurisdiction}, según {from}{where}.",
  jurisdictionMany: "Patente y sellos de {jurisdiction}, según {from}{where}: el rango cubre {all}.",
  where: " en {labels}",
  coversTwo: "las dos",
  coversAll: "todas",
  fromSearch: "tu búsqueda",
  fromProfile: "tu zona",
  jurisdictionNames: { caba: "CABA", ba: "Buenos Aires", rest: "resto del país" },
  amba: "Tu búsqueda es AMBA: el rango cubre CABA y provincia de Buenos Aires.",
  rest: "Resto del país: rango armado con Córdoba, Santa Fe y Mendoza.",
  seller: "Vendedor: {kind}.",
  sellerKinds: {
    private: "particular",
    dealer: "concesionaria",
    inferred: "posible agencia",
    none: "sin informar: el rango cubre particular y agencia",
  },
  vf: "La valuación fiscal se estima como precio × {k} (supuesto propio, no oficial). Si la tabla oficial de tu modelo supera el precio, el arancel y los sellos son mayores.",
  rateListing: "Dólar del aviso: ${rate}.",
  rateQuote: "Dólar {kind} del {date}: ${rate}.",
  rateKinds: { blue: "blue", oficial: "oficial" } as Record<string, string>,
  noRate: "Sin dólar del día: el total va solo en pesos.",
  rounding: "Montos redondeados hacia afuera.",
  asOf: "Parámetros al {date}.",
  sources: "Fuentes:",
  sourceLine: "{name}: {source} ({date})",
  sourceNames: {
    arancel: "Arancel",
    sellos: "Sellos",
    formularios: "Formularios",
    patente: "Patente",
    domain_report: "Informe de dominio",
    vf: "Valuación fiscal",
    mrpa: "MRPA",
    gestoria: "Gestoría",
  },
  missingLine: "{names}: {reason}.",
  missingNames: { arancel: "Arancel", sellos: "Sellos", formularios: "Formularios", patente: "Patente" },
  reasons: {
    no_zone: "tu búsqueda no tiene zona en Argentina",
    no_year: "falta el año del modelo",
    params: "faltan parámetros cargados",
    pre_min_year: "modelo anterior a {year} en Buenos Aires: sin dato",
    base: "la base de cálculo cargada no es el precio",
  },
} as const;

// PAR-03: a listing's price drops since we first saw it (its first snapshot,
// not its publication). Same wording as worker/intelligence/copy.py.
export const PRICE_TRACK = {
  line: "Bajó {n} {times} desde que la vimos: -{amount} (-{pct}){about}.",
  times: ["vez", "veces"],
  aboutUsd: ", unos {usd}",
  summary: "{n} {drops} · -{amount} (-{pct}) desde el {date}",
  drops: ["baja", "bajas"],
  detected: "No sabemos cuándo se publicó; contamos desde que la detectamos.",
  trackedSince: "Seguimos este aviso desde el {date}; no vemos los cambios anteriores.",
  historyToggle: "Ver el histórico de precios",
} as const;
