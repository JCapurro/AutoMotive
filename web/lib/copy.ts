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
/**
 * PRO-01, option C (Juan, 02/11): the strict seller filter let a listing whose
 * seller is unknown through (lib/seller.ts strictSellerUnknown). The card, the
 * listing page and the opportunity email (worker copy.SELLER_UNKNOWN).
 */
export const SELLER_UNKNOWN = "vendedor sin dato";
/** F-02: under the search form's «Vendedor» when it prefers a dealer. */
export const SELLER_FORM_HINT = "Incluye posibles agencias.";
/**
 * PRO-01: the strict seller filter (filters.seller_types, Pro). The options
 * Pro sees, the check, its hint, the summary row and what a plan without it
 * reads (the stored type works as the preference there).
 */
export const SELLER_STRICT = {
  option: { private: "Particulares", dealer: "Agencias (incluye posibles agencias)" },
  check: "Solo este tipo de vendedor",
  hint: "Descartamos los otros. Si la publicación no dice quién vende, el aviso pasa con menos puntaje.",
  summary: { private: "Solo particulares", dealer: "Solo agencias (incluye posibles agencias)" },
  proOnly: "Filtro estricto: solo Pro. En tu plan se usa como preferencia.",
  remove: "Quitar filtro estricto",
  downgraded: { private: "Particulares (preferido; filtro estricto solo Pro)", dealer: "Agencias (preferido; filtro estricto solo Pro)" },
  assisted: {
    private: "Solo particulares (filtro estricto). Podés cambiarlo editando la búsqueda.",
    dealer: "Solo agencias, incluye posibles agencias (filtro estricto). Podés cambiarlo editando la búsqueda.",
  },
  relax: "Cualquier vendedor",
  required: "Elegí el tipo de vendedor.",
} as const;
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
  seller: "Tipo de vendedor buscado",
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
  seller: "Vendedor",
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

/**
 * PRO-01: the message for the seller, ready to copy (lib/contact-message.ts).
 * The same texts as worker/intelligence/copy.py CONTACT_MESSAGE and QUESTION
 * («available», «holder»). {auto} and {preguntas} are markers, replaced
 * literally. Ese Auto never sends it.
 */
export const CONTACT_MESSAGE = {
  default: "Hola, vi tu {auto} publicado.\n{preguntas}\n¿Cuándo se puede ver?",
  auto: "auto",
  available: "¿Lo seguís teniendo?",
  holder: "¿Sos titular?",
  subject: "Consulta por tu {auto}",
  title: "Mensaje listo para mandar",
  copy: "Copiar",
  mail: "Abrir en tu correo",
  copied: "Copiado. Pegalo en el chat de la publicación.",
  copyFailed: "No pudimos copiar. Seleccioná el texto y copialo a mano.",
  note: "Ese Auto no contacta al vendedor: vos decidís si mandarlo.",
  send: "Mandalo desde la publicación",
  settingsTitle: "Mensaje para vendedores",
  field: "Tu plantilla",
  settingsHint: "Lo armamos para cada auto y lo copiás o lo abrís en tu correo. Ese Auto no lo manda.",
  markers: "{auto} es el modelo y el año; {preguntas}, si lo sigue teniendo y una pregunta de ese auto.",
  preview: "Vista previa",
  save: "Guardar",
  reset: "Volver al mensaje sugerido",
  saved: "Mensaje guardado.",
  resetDone: "Volvimos al mensaje sugerido.",
} as const;

/** The idioms the copy lint lets through (the §50 landing's «vale la pena» is not about price). */
export const ALLOWED_PHRASES = ["vale la pena"];

/** Lowercase without accents (NFD without marks), as the lint reads text. */
export function foldText(text: string): string {
  return text.normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase();
}

/** The FORBIDDEN_TERMS in `text`, as whole words, accents folded, ALLOWED_PHRASES aside. */
export function forbiddenTermsIn(text: string): string[] {
  let folded = foldText(text);
  for (const phrase of ALLOWED_PHRASES) folded = folded.split(foldText(phrase)).join(" ");
  const terms = [...new Set(FORBIDDEN_TERMS.map(foldText))];
  return terms.filter((t) => new RegExp(`(^|[^\\p{L}\\p{N}_])${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^\\p{L}\\p{N}_]|$)`, "u").test(folded));
}

export const CONTACT_TEMPLATE_MAX_CHARS = 500;
export const CONTACT_TEMPLATE_MAX_LINES = 6;
export type ContactTemplateError = "too_long" | "too_many_lines" | "placeholder" | "forbidden" | "url" | "phone";
/** What Ajustes says for each rule of lintContactTemplate. */
export const CONTACT_TEMPLATE_ERROR: Record<ContactTemplateError, string> = {
  too_long: "Usá hasta 500 caracteres.",
  too_many_lines: "Usá hasta 6 líneas.",
  placeholder: "Entre llaves solo van {auto} y {preguntas}.",
  forbidden: "Evitá frases sobre cuánto debería costar el auto: no las podemos verificar.",
  url: "Sacá links, emails y usuarios: el mensaje se manda desde la publicación.",
  phone: "Sacá los teléfonos: el mensaje se manda desde la publicación.",
};

const MARKER = /\{(auto|preguntas)\}/g;
const URL_LIKE = /https?:\/\/|(?<![\p{L}\p{N}_-])www\.|(?<![\p{L}\p{N}_-])wa\.me(?![\p{L}\p{N}_])|@|(?<![\p{L}\p{N}_-])[\p{L}\p{N}_-]+\.(?:com|net|org|ar|io|me|app|co|ly|info|link|site|online|store|shop)(?![\p{L}\p{N}_])/u;
// \p{Nd}, not \d: any decimal digit (fullwidth, Arabic-Indic...), as Python's \d reads it.
const PHONE_LIKE = /\+?\p{Nd}(?:[\s.\-()/]*\p{Nd}){6,}/u;

/**
 * PRO-01 decisión 17: the rule for profiles.contact_template, the worker's
 * lint_contact_template twin (both fixed by worker/tests/fixtures/contact_message/lint.json).
 * `value` is what to store (null: the default template); `error` a code, never thrown.
 */
export function lintContactTemplate(raw: string | null | undefined): { value: string | null; error: ContactTemplateError | null } {
  if (raw == null) return { value: null, error: null };
  const text = raw.replace(/\r\n?/g, "\n").trim();
  if (!text) return { value: null, error: null };
  if ([...text].length > CONTACT_TEMPLATE_MAX_CHARS) return { value: null, error: "too_long" };
  if (text.split("\n").length > CONTACT_TEMPLATE_MAX_LINES) return { value: null, error: "too_many_lines" };
  const rest = text.replace(MARKER, "");
  if (rest.includes("{") || rest.includes("}") || /%\(?[a-z]/.test(foldText(text))) return { value: null, error: "placeholder" };
  const folded = foldText(text);
  if (forbiddenTermsIn(text).length) return { value: null, error: "forbidden" };
  if (URL_LIKE.test(folded)) return { value: null, error: "url" };
  if (PHONE_LIKE.test(folded)) return { value: null, error: "phone" };
  return { value: text, error: null };
}

// PAR-01: the total cost estimate (lib/cost-estimator.ts returns codes). The
// header lines are the worker's (worker/intelligence/copy.py TOTAL_COST).
export const COST_ESTIMATE = {
  line: "Costo total estimado{suffix}: {usd} ({ars})",
  lineNoUsd: "Costo total estimado{suffix}: {ars} (sin dólar del día)",
  lineNoFx: "Costo total estimado: sin dólar del día, no se puede estimar",
  lineNoZone: "Costo total: no sabemos tu localidad. Cargala en la búsqueda para estimarlo",
  /** The part of lineNoZone the listing page links to the search's edit form. */
  noZoneLink: "Cargala en la búsqueda",
  suffix: " (sin {items})",
  last: " ni ",
  names: { arancel: "arancel", sellos: "sellos", formularios: "formularios", patente: "patente" },
  toggle: "Ver detalle",
  // Juan 02/11: the breakdown is a compact summary (cost-estimate-view.ts).
  transfer: "Transferencia",
  patente: "Patente anual (valores {year})",
  total: "Total estimado",
  footnote: "Valores oficiales al {date} para {jurisdiction}.{outside}",
  // «rest» has no official scale of its own: its range is built from other provinces, so it is never called official.
  footnoteRest: "Valores al {date} de Córdoba, Santa Fe y Mendoza como referencia: no son los oficiales de tu provincia.{outside}",
  footnoteMixed: "Valores oficiales al {date} para {jurisdiction}; para el resto del país, referencia con Córdoba, Santa Fe y Mendoza.{outside}",
  outside: " No incluye {items}.",
  outsideGestoria: "gestoría",
  outsideDomainReport: "informe de dominio ({amount})",
  or: " o ",
  jurisdictionNames: { caba: "CABA", ba: "Provincia de Buenos Aires", rest: "resto del país" },
  sourcesToggle: "Ver fuentes",
  sourceLine: "{name}: {source} ({date})",
  rateListing: "Dólar del aviso: ${rate}",
  rateQuote: "Dólar {kind} del {date}: ${rate}",
  rateKinds: { blue: "blue", oficial: "oficial" } as Record<string, string>,
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
  reasons: {
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

// The listing page's decision panel: the published price against the observed
// market in one line (lib/price-gap.ts); «¿Está bien de precio?» has the long one.
export const PRICE_GAP = {
  below: "{gap} debajo",
  above: "{gap} arriba",
  rest: " de lo que suelen pedir por autos parecidos ({pct}).",
  inLine: "En línea con lo que suelen pedir por autos parecidos.",
} as const;

// PRO-02: the estimated gross margin against the dealers' median (lib/margin-view.ts
// formats matches.margin_ref). The line is the worker's (worker/intelligence/copy.py
// MARGIN); the rest is the listing page's detail. An estimate to orient a dealer,
// never a promise: lib/copy.test.ts forbids the words of a guaranteed result here.
export const MARGIN = {
  line: "Margen bruto estimado: {usd} (contra la mediana de {median} a la que publican las agencias este modelo, n = {n}; {costs}; sin impuestos)",
  single: "USD {v}",
  range: "USD {lo} a {hi}",
  costsBoth: "descuenta acondicionamiento del {pct} % y transferencia",
  costsNoTransfer: "descuenta acondicionamiento del {pct} %; no descuenta la transferencia porque {why}",
  costsNoReconditioning: "descuenta transferencia; no descuenta acondicionamiento porque faltan sus parámetros",
  costsNone: "sin descontar costos: faltan los parámetros de acondicionamiento y no descuenta la transferencia porque {why}",
  // Juan, 02/11: without enough dealers, say so instead of showing nothing.
  fewDealers: "Margen estimado: no hay suficientes agencias publicando este modelo para estimarlo (n = {n}, mínimo {min_n})",
  // Juan, 02/11: the result cards (search, dashboard, Guardados) carry the short
  // line; the listing page and the Pro emails keep the full one above.
  cardLine: "Margen bruto estimado: {usd} (n\u00a0=\u00a0{n}\u00a0agencias)",
  cardFewDealers: "Margen estimado: pocas agencias para estimarlo (n\u00a0=\u00a0{n})",
  why: {
    no_zone: "tu búsqueda no tiene localidad",
    no_official: "no tenemos los valores oficiales de tu provincia",
    no_official_some: "no tenemos los valores oficiales de todas las provincias de tu búsqueda",
    no_fx: "falta el dólar del día",
    params: "faltan parámetros cargados",
    base: "faltan parámetros cargados",
    no_price: "no pudimos leer la moneda del precio",
    disabled: "no está activada",
  } as Record<string, string>,
  // The listing page's «Ver detalle».
  toggle: "Ver detalle del margen",
  median: "Mediana de agencias: {median} (n = {n} de {total} comparables, {level}).",
  asking: "Precio de compra: {asking}.",
  askingCash: "Precio de compra (de contado): {asking}.",
  reconditioning: "Acondicionamiento: {usd} ({pct} % del precio, mínimo {min}).",
  reconditioningMissing: "Acondicionamiento: no se descuenta, faltan sus parámetros.",
  transfer: "Transferencia: {usd} (arancel, sellos y formularios de {jurisdiction}, según tu búsqueda).",
  transferMissing: "Transferencia: no se descuenta porque {why}.",
  acquisition: "Lo que cuesta comprar el auto: {usd} (precio de compra más los costos descontados).",
  pct: "Margen sobre lo que cuesta comprar el auto: {pct}.",
  excludes: "No incluye impuestos de la venta, patente ni comisiones.",
  published: "Comparamos con precios publicados por agencias, no con precios de venta. Es una estimación orientativa.",
  asOf: "Parámetros al {date}.",
  // Results order and the search form (Pro).
  sort: "Mayor margen estimado",
  thresholdTitle: "Avisos al instante por margen estimado",
  thresholdOn: "Te avisamos al instante cuando el margen bruto estimado contra la mediana de agencias es de {usd} o más. El resto va al resumen diario.",
  thresholdOff: "Apagado: el margen estimado no cambia cuándo te avisamos.",
  thresholdLabel: "Margen mínimo (USD)",
  thresholdMin: "Desde USD {min}.",
  thresholdNoMargin: "Lo que no tiene suficientes agencias comparables para estimar el margen va al resumen diario.",
} as const;

// Juan, 02/11: the other plans see where Pro has a margin, never the margin. The
// figure and the note are fixed placeholders (X for every digit), shown blurred:
// nothing of the listing's margin reaches the page.
export const MARGIN_TEASER = {
  label: "Margen bruto estimado",
  figure: "USD X.XXX a X.XXX",
  note: "(contra la mediana de USD XX.XXX a la que publican las agencias este modelo, n = X; descuenta acondicionamiento y transferencia; sin impuestos)",
  cardFigure: "USD X.XXX",
  hidden: "disponible con Pro",
  line: "Con Pro ves el margen bruto estimado de este auto frente a lo que publican las agencias.",
  cta: "Ver planes",
} as const;

// Juan, 02/11: Pro's settings in view on the other plans, locked (lib/pro.ts
// proLocked): the tag, what each one does and the way to the plans.
export const PRO_LOCKED = {
  badge: "Pro",
  cta: "Ver planes",
  opportunity: "Con Pro te avisamos al instante cuando un auto está por debajo del precio de mercado en el porcentaje que elijas.",
  margin: "Con Pro te avisamos al instante cuando el margen bruto estimado contra la mediana de agencias llega al monto que elijas.",
  seller: "Con Pro descartamos los otros tipos de vendedor.",
  sort: "{sort} (Pro)",
} as const;
