/**
 * PAR-02 tramo 1: the «Antes de señar» checklist of the listing page
 * (docs/superpowers/specs/2026-10-29-par02-checklist-design.md). Data only, no
 * UI and no server-only code: the client component, webConfig() and
 * validateConfigChange() all import it.
 *
 * Every item reads as something the user should check; Ese Auto never claims
 * it checked anything. The official links live in app_config.risk.links and
 * only Juan loads them: until then the block shows no link at all.
 */
import { z } from "zod";

import { EMPHASIS_FLAGS } from "@/lib/red-flags";

export const RISK_TITLE = "Antes de señar";
export const RISK_HINT = "Controles para hacer vos antes de dejar una seña.";
export const RISK_HEADER = "Son controles que conviene hacer vos. Ese Auto no verificó nada de esta publicación.";
/** Approved by Juan (2026-10-30). Shown when the listing has much_cheaper or partial_price_suspect. */
export const RISK_EMPHASIS = "Por el precio de esta publicación, conviene hacer todos estos controles antes de señar.";
export const RISK_COPY_LABEL = "Copiar checklist";
export const RISK_OFFICIAL_LABEL = "Ver sitio oficial";
export const RISK_COPIED = "Copiado. Tenelo a mano antes de señar.";
export const RISK_COPY_FAILED = "No pudimos copiar. Seleccioná el texto y copialo a mano.";

export type RiskItemId = "dominio" | "deudas" | "prenda" | "vtv" | "titular" | "transferencia" | "en_persona";

export const CHECKLIST_ITEMS: readonly { id: RiskItemId; text: string }[] = [
  { id: "dominio", text: "Conviene verificar el informe de dominio y el informe histórico del vehículo en el registro automotor (DNRPA)." },
  { id: "deudas", text: "Conviene verificar si hay deuda de patentes e infracciones en la jurisdicción que corresponda." },
  { id: "prenda", text: "Conviene verificar si tiene prenda u otra restricción registrada." },
  { id: "vtv", text: "Conviene verificar la VTV." },
  { id: "titular", text: "Conviene verificar la cédula y el DNI del titular y que coincidan con quien vende." },
  { id: "transferencia", text: "Conviene verificar cómo se hace la transferencia: formulario 08 ante escribano o registro." },
  { id: "en_persona", text: "Conviene ver el auto y los papeles en persona antes de señar por transferencia." },
];

export const RISK_URL_MAX = 300;
const TITLE_MAX = 120;

export type RiskLink = { label: string; url: string };
export type RiskLinks = {
  dnrpa: RiskLink | null;
  patentes: RiskLink[];
  infracciones: RiskLink[];
  vtv: RiskLink | null;
  form_08: RiskLink | null;
};
export type RiskConfig = { checklistEnabled: boolean; links: RiskLinks };
export type RiskItem = {
  id: RiskItemId;
  text: string;
  official?: RiskLink;
  groups?: { title: string; links: RiskLink[] }[];
};

/** Only https://, with a host, no credentials, at most 300 characters and no surrounding spaces. */
export function safeRiskUrl(url: unknown): url is string {
  if (typeof url !== "string" || url.length > RISK_URL_MAX || url !== url.trim() || !/^https:\/\/[^/\\\s]/i.test(url)) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname !== "" && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

const URL_MESSAGE = `Cada link tiene que empezar con https://, sin usuario ni contraseña y con hasta ${RISK_URL_MAX} caracteres.`;
const LinkInput = z
  .object({
    label: z.string().trim().min(1, "Cada link necesita una etiqueta."),
    url: z.string().refine(safeRiskUrl, URL_MESSAGE),
  })
  .passthrough();

// PAR-02 resto: the duplicate signals and the photo hash, same bounds as
// worker/intelligence/config.py risk(). Each key is optional (the worker falls
// back to its default); a present one must be valid.
const Signal = z.enum(["on", "shadow", "off"], "Cada señal de signals tiene que ser on, shadow u off.");
const range = (name: string, min: number, max: number, int = true) =>
  z.number(`${name} tiene que ser un número entre ${min} y ${max}.`).refine(
    (n) => Number.isFinite(n) && n >= min && n <= max && (!int || Number.isInteger(n)),
    `${name} tiene que ser un${int ? " entero" : " número"} entre ${min} y ${max}.`,
  );
export const RiskDuplicatesInput = z.object({
  photo_hash_count: range("photo_hash_count", 1, 5).optional(),
  phash_max_distance: range("phash_max_distance", 0, 16).optional(),
  photo_hash: z
    .object({
      enabled: z.boolean("photo_hash.enabled tiene que ser true o false.").optional(),
      daily_image_cap: range("photo_hash.daily_image_cap", 0, 5000).optional(),
      max_attempts: range("photo_hash.max_attempts", 1, 10).optional(),
      max_bytes: range("photo_hash.max_bytes", 10_000, 20_000_000).optional(),
      timeout_seconds: range("photo_hash.timeout_seconds", 1, 60, false).optional(),
      per_host_interval_seconds: range("photo_hash.per_host_interval_seconds", 0, 60, false).optional(),
      common_min_sellers: range("photo_hash.common_min_sellers", 2, 100).optional(),
      skip_sources: z.array(z.string().min(1), "photo_hash.skip_sources tiene que ser una lista de fuentes.").optional(),
    })
    .passthrough()
    .optional(),
  cross_source: z
    .object({
      km_tol_pct: range("cross_source.km_tol_pct", 0, 20, false).optional(),
      price_tol_pct: range("cross_source.price_tol_pct", 0, 20, false).optional(),
      data_min_km: range("cross_source.data_min_km", 0, 1_000_000).optional(),
      data_max_dist_km: range("cross_source.data_max_dist_km", 1, 500, false).optional(),
      photo_conflict_km_pct: range("cross_source.photo_conflict_km_pct", 0, 50, false).optional(),
      photo_conflict_price_pct: range("cross_source.photo_conflict_price_pct", 0, 50, false).optional(),
    })
    .passthrough()
    .optional(),
  signals: z
    .object({
      private_many_listings: Signal.optional(),
      cross_source_photos: Signal.optional(),
      cross_source_data: Signal.optional(),
      duplicate_photos: Signal.optional(),
    })
    .passthrough()
    .optional(),
});

/** /admin/config validation of app_config.risk; unknown keys are kept. */
export const RiskConfigInput = z
  .object({
    ...RiskDuplicatesInput.shape,
    checklist_enabled: z.boolean("checklist_enabled tiene que ser true o false.").optional(),
    links: z
      .object({
        dnrpa: LinkInput.nullable().optional(),
        patentes: z.array(LinkInput).optional(),
        infracciones: z.array(LinkInput).optional(),
        vtv: LinkInput.nullable().optional(),
        form_08: LinkInput.nullable().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function riskLink(value: unknown): RiskLink | null {
  const v = record(value);
  const label = typeof v.label === "string" ? v.label.trim() : "";
  return label && safeRiskUrl(v.url) ? { label, url: v.url } : null;
}

function riskLinks(value: unknown): RiskLink[] {
  return Array.isArray(value) ? value.map(riskLink).filter((l): l is RiskLink => l !== null) : [];
}

/** app_config.risk as the page uses it: missing or malformed = visible checklist without links; bad links are dropped one by one. */
export function riskConfig(raw: unknown): RiskConfig {
  const value = record(raw);
  const links = record(value.links);
  return {
    checklistEnabled: value.checklist_enabled !== false,
    links: {
      dnrpa: riskLink(links.dnrpa),
      patentes: riskLinks(links.patentes),
      infracciones: riskLinks(links.infracciones),
      vtv: riskLink(links.vtv),
      form_08: riskLink(links.form_08),
    },
  };
}

/** The items with whatever official link is loaded for them. */
export function checklistItems(config: RiskConfig): RiskItem[] {
  const { links } = config;
  const official: Partial<Record<RiskItemId, RiskLink | null>> = {
    dominio: links.dnrpa,
    vtv: links.vtv,
    transferencia: links.form_08,
  };
  return CHECKLIST_ITEMS.map((item) => {
    const out: RiskItem = { ...item };
    const link = official[item.id];
    if (link) out.official = link;
    if (item.id === "deudas") {
      const groups = [
        { title: "Patentes", links: links.patentes },
        { title: "Infracciones", links: links.infracciones },
      ].filter((group) => group.links.length > 0);
      if (groups.length) out.groups = groups;
    }
    return out;
  });
}

/** What «Copiar checklist» copies: the listing's name and the items, never links or personal data. */
export function checklistText(title: string): string {
  const name = String(title ?? "").replace(/\s+/g, " ").trim();
  const short = name.length > TITLE_MAX ? `${name.slice(0, TITLE_MAX - 1).trimEnd()}…` : name;
  return [short ? `${RISK_TITLE}: ${short}` : RISK_TITLE, RISK_HEADER, ...CHECKLIST_ITEMS.map((item) => `- ${item.text}`)].join("\n");
}

/**
 * The block opens with the emphasis line when the price itself is a reason to
 * be careful, or (PAR-02 resto) the photos also appear in another listing.
 */
export function emphasize(flags: readonly { id: string }[]): boolean {
  return flags.some((flag) => EMPHASIS_FLAGS.has(flag.id));
}
