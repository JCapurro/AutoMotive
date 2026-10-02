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
  interested: "Me interesa",
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
export const FUEL: Record<string, string> = {
  nafta: "Nafta",
  diesel: "Diésel",
  gnc: "GNC",
  hibrido: "Híbrido",
  electrico: "Eléctrico",
};

export const CHANNEL: Record<string, string> = { telegram: "Telegram", email: "Email", web: "Web" };

// "¿Por qué apareció?" (§23): what an ok reason says, by match_reasons key.
export const REASON_OK: Record<string, string> = {
  model: "Modelo buscado",
  year: "Año dentro del rango",
  price: "Dentro del presupuesto",
  km: "Kilometraje compatible",
  transmission: "Caja buscada",
  fuel: "Combustible buscado",
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
