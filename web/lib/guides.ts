/**
 * PAR-04 · Guías por modelo (docs/superpowers/specs/2026-11-03-par04-guias-design.md).
 *
 * Pure: slugs, the shape of a guide (zod, the worker's schemas.ModelGuideDraft
 * twin), what blocks publishing (public.model_guide_problem), the copy lint
 * (lib/copy.ts FORBIDDEN_TERMS plus the risk stems of worker copy.RISK_FORBIDDEN,
 * and no amount of money, like worker/intelligence/guides.py), the FAQ JSON-LD
 * and every fixed text of the public pages.
 *
 * A guide's text is a statement of the guide, never a check of a car: the
 * page says «Guía orientativa» and that it does not replace a mechanic.
 */
import { z } from "zod";

import { foldText, forbiddenTermsIn } from "@/lib/copy";

export const GUIDE_SECTIONS = ["known_issues", "visit_checklist", "versions_equipment", "maintenance_costs", "generations"] as const;
export type GuideSection = (typeof GUIDE_SECTIONS)[number];
export const GUIDE_SECTION_NAME: Record<GuideSection, string> = {
  known_issues: "Fallas conocidas",
  visit_checklist: "Qué revisar en la visita",
  versions_equipment: "Versiones y equipamiento",
  maintenance_costs: "Mantenimiento y costos típicos",
  generations: "Generaciones",
};
/**
 * GEO: each section's heading on the public page, as the question someone
 * types into a search or answer engine; the FAQPage JSON-LD repeats them word
 * for word, so the structured data matches what the page shows.
 */
export const GUIDE_SECTION_QUESTION: Record<GuideSection, string> = {
  known_issues: "¿Qué fallas conocidas tiene el {name}?",
  visit_checklist: "¿Qué revisar al ver un {name} usado?",
  versions_equipment: "¿Qué versiones y equipamiento tiene el {name}?",
  maintenance_costs: "¿Qué mantenimiento necesita el {name}?",
  generations: "¿Qué generaciones tuvo el {name}?",
};
export const SELLER_QUESTION = "¿Qué preguntarle al vendedor de un {name}?";

/** A section's question for a model («Volkswagen Gol Trend») or one of its generations («Toyota Corolla E170»). */
export function sectionQuestion(key: GuideSection | "seller", name: string): string {
  return (key === "seller" ? SELLER_QUESTION : GUIDE_SECTION_QUESTION[key]).replace("{name}", name);
}

export const SOURCE_KINDS = ["ficha técnica", "manual", "prensa", "foro", "otra"] as const;
export const MIN_QUESTIONS = 3;
export const MAX_QUESTIONS = 8;
export const QUESTION_MIN_CHARS = 10;
export const QUESTION_MAX_CHARS = 200;
/** Backlog: a listing gets «hasta 3» questions of its guide (worker MAX_QUESTIONS_IN_LISTING). */
export const MAX_QUESTIONS_IN_LISTING = 3;
/** The public pages' ISR window, in seconds; publishing invalidates at once (revalidatePath). */
export const GUIDE_REVALIDATE_SECONDS = 3600;

/** Every fixed text of the public pages (lib/guides.test.ts lints it). */
export const GUIDE_COPY = {
  badge: "Guía orientativa",
  notice:
    "Guía orientativa. Resume información general del modelo; no verifica ningún auto en particular ni reemplaza la revisión de un mecánico de confianza.",
  questionsTitle: "Preguntas para hacerle al vendedor",
  copy: "Copiar preguntas",
  copied: "Copiadas. Pegalas en el chat de la publicación.",
  copyFailed: "No pudimos copiar. Seleccioná el texto y copialo a mano.",
  sourcesTitle: "Fuentes",
  updated: "Última actualización: {date}",
  appliesTo: "Aplica a: {text}",
  ctaTitle: "¿Estás buscando un {name}?",
  ctaText: "Contanos qué querés y te avisamos cuando aparezca uno publicado, con preguntas para hacerle al vendedor.",
  indexTitle: "Guías orientativas por modelo",
  indexIntro: "Qué mirar y qué preguntar antes de ver un usado. Información general de cada modelo: no verifica ningún auto en particular ni reemplaza la revisión de un mecánico.",
  indexEmpty: "Todavía no hay guías publicadas.",
  indexBack: "Volver al inicio",
  allGuides: "Todas las guías",
  summaryTitle: "En resumen",
  summaryIssue: "Una falla conocida del {name}{years}: {text}.",
  summaryCheck: "En la visita, revisá primero esto: {text}.",
  summaryClose: "Es información general del modelo: no reemplaza la revisión de un mecánico de confianza.",
  ctaTop: "Crear mi búsqueda",
  ctaTopShort: "Avisame",
  ctaTopText: "¿Ya sabés que querés un {name}? Te avisamos cuando aparezca uno publicado.",
  home: "Inicio",
  listingLink: "Ver la guía del {name}",
  updatedTop: "Actualizada el {date}",
  makeTitle: "Guías de {make} usados",
  makeIntro: "Qué mirar y qué preguntar antes de ver un {make} usado, modelo por modelo. Información general: no verifica ningún auto en particular ni reemplaza la revisión de un mecánico.",
  makeIssue: "Falla conocida: {text}",
  allFromMake: "Todas las guías de {make}",
  related: "Otras guías",
  method: "Cómo hacemos las guías",
  indexEyebrow: "Guías orientativas",
  indexHeading: "Qué mirar antes de ver un usado",
  letters: "Marcas por letra",
  models: "{n} modelos",
  model: "1 modelo",
  toc: "En esta guía",
  sources: "{n} fuentes consultadas",
  source: "1 fuente consultada",
  sourcesFold: "Fuentes ({n})",
  visitHint: "Tocá el círculo a medida que lo revisás.",
  visitTick: "Marcar como revisado",
  whatsapp: "Mandarlas por WhatsApp",
  whatsappIntro: "Hola, te consulto por el {name}:",
} as const;

/** Who publishes the guides (schema.org Organization). */
export const SITE_NAME = "Ese Auto";

export function guideName(make: string, model: string): string {
  return `${make} ${model}`;
}

export function guideTitle(make: string, model: string): string {
  return `${guideName(make, model)} usado: guía orientativa para revisarlo`;
}

export function guideDescription(make: string, model: string, years: string): string {
  const name = guideName(make, model);
  return `Fallas conocidas, qué revisar en la visita y qué preguntarle al vendedor de un ${name}${years ? ` ${years}` : ""} usado. Guía orientativa: no reemplaza la revisión de un mecánico.`;
}

/** "2014 a 2019", "desde 2014", "hasta 2019" or "". */
export function yearsText(from: number | null | undefined, to: number | null | undefined): string {
  if (from && to) return from === to ? String(from) : `${from} a ${to}`;
  if (from) return `desde ${from}`;
  if (to) return `hasta ${to}`;
  return "";
}

/** The CTA's prefilled text: «Busco un Toyota Corolla 2014 a 2019». */
export function ctaPrompt(make: string, model: string, from?: number | null, to?: number | null): string {
  const years = from && to ? (from === to ? ` ${from}` : ` ${from} a ${to}`) : from ? ` desde ${from}` : to ? ` hasta ${to}` : "";
  return `Busco un ${guideName(make, model)}${years}`;
}

/** Lowercase, no accents, anything else to "-": «Volkswagen Gol Trend» → "volkswagen-gol-trend". */
export function slugify(text: string): string {
  return foldText(text).replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export function isSlug(value: unknown): value is string {
  return typeof value === "string" && value.length <= 80 && SLUG_PATTERN.test(value);
}

export function guidePath(slugMake: string, slugModel: string): string {
  return `/guias/${slugMake}/${slugModel}`;
}

/** /guias/<marca>: the make's published models. */
export function makePath(slugMake: string): string {
  return `/guias/${slugMake}`;
}

/** How the guides are made (sources, updates, what they are not). A static segment: it wins over /guias/[marca]. */
export const METHOD_PATH = "/guias/como-las-hacemos";

/**
 * The published model whose guide a listing links to (the ficha's «Ver la
 * guía del …»), or null. The worker's match (worker/intelligence/guides.py
 * pick): same make and the catalog's model (the listing's own model without
 * one), case-insensitive. The years don't matter: the model's page covers
 * every generation.
 */
export function guideForListing<T extends { make: string; model: string }>(
  index: readonly T[],
  make: string | null | undefined,
  model: string | null | undefined,
): T | null {
  const key = (v: string) => v.trim().toLowerCase();
  if (!make?.trim() || !model?.trim()) return null;
  return index.find((e) => key(e.make) === key(make) && key(e.model) === key(model)) ?? null;
}

// ---------------------------------------------------------------------------
// Shape
// ---------------------------------------------------------------------------

const text = (max: number) => z.string().trim().min(1, "Escribí el texto del renglón.").max(max, `Usá hasta ${max} caracteres.`);
const optionalText = (max: number) =>
  z.string().trim().max(max, `Usá hasta ${max} caracteres.`).nullish().transform((v) => (v ? v : null));
const year = z.number().int().min(1950).max(2100).nullish().transform((v) => v ?? null);

export const GuideLineInput = z.object({ text: text(400), applies_to: optionalText(120) });
export const GenerationLineInput = z.object({ label: optionalText(80), year_from: year, year_to: year, text: text(400) });
export const GuideBodyInput = z.object({
  known_issues: z.array(GuideLineInput).max(30),
  visit_checklist: z.array(GuideLineInput).max(30),
  versions_equipment: z.array(GuideLineInput).max(30),
  maintenance_costs: z.array(GuideLineInput).max(30),
  generations: z.array(GenerationLineInput).max(15),
});
export const GuideQuestionInput = z.object({
  text: z.string().trim()
    .min(QUESTION_MIN_CHARS, `Cada pregunta tiene de ${QUESTION_MIN_CHARS} a ${QUESTION_MAX_CHARS} caracteres.`)
    .max(QUESTION_MAX_CHARS, `Cada pregunta tiene de ${QUESTION_MIN_CHARS} a ${QUESTION_MAX_CHARS} caracteres.`)
    .refine((v) => v.endsWith("?"), "Cada pregunta termina en «?»."),
  why: z.string().trim().max(300).default(""),
});
export const GuideSourceInput = z.object({
  title: text(200),
  url: z.string().trim().max(500).refine((v) => /^https:\/\/[^\s]+$/.test(v), "La URL de cada fuente empieza con https://."),
  kind: z.enum(SOURCE_KINDS).default("otra"),
  verified: z.boolean().default(false),
});
/** The content (what publishing checks): the sections, the questions and the sources. */
export const GuideContentInput = z.object({
  body: GuideBodyInput,
  questions: z.array(GuideQuestionInput).max(MAX_QUESTIONS, `Van de ${MIN_QUESTIONS} a ${MAX_QUESTIONS} preguntas.`),
  sources: z.array(GuideSourceInput).max(20),
});
export const GuideValuesInput = GuideContentInput.extend({
  make: z.string().trim().min(1).max(80),
  model: z.string().trim().min(1).max(80),
  generation_label: optionalText(80),
  year_from: year,
  year_to: year,
}).superRefine((v, ctx) => {
  if (v.year_from && v.year_to && v.year_to < v.year_from) ctx.addIssue({ code: "custom", path: ["year_to"], message: "El año hasta no puede ser anterior al año desde." });
});
export type GuideValues = z.infer<typeof GuideValuesInput>;
export type GuideBody = GuideValues["body"];
export type GuideLine = z.infer<typeof GuideLineInput>;
export type GenerationLine = z.infer<typeof GenerationLineInput>;
export type GuideQuestion = z.infer<typeof GuideQuestionInput>;
export type GuideSource = z.infer<typeof GuideSourceInput>;

export function emptyBody(): GuideBody {
  return { known_issues: [], visit_checklist: [], versions_equipment: [], maintenance_costs: [], generations: [] };
}

/** A stored jsonb body read leniently (a draft may be empty or partial). */
export function readBody(value: unknown): GuideBody {
  const body = emptyBody();
  if (!value || typeof value !== "object" || Array.isArray(value)) return body;
  for (const key of GUIDE_SECTIONS) {
    const lines = (value as Record<string, unknown>)[key];
    if (!Array.isArray(lines)) continue;
    for (const line of lines) {
      const parsed = (key === "generations" ? GenerationLineInput : GuideLineInput).safeParse(line);
      if (parsed.success) (body[key] as unknown[]).push(parsed.data);
    }
  }
  return body;
}

export function readQuestions(value: unknown): GuideQuestion[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((q) => {
    if (!q || typeof q !== "object") return [];
    const t = (q as { text?: unknown }).text;
    const why = (q as { why?: unknown }).why;
    return typeof t === "string" && t.trim() ? [{ text: t.trim(), why: typeof why === "string" ? why.trim() : "" }] : [];
  });
}

export function readSources(value: unknown): GuideSource[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((s) => {
    const parsed = GuideSourceInput.safeParse(s);
    return parsed.success ? [parsed.data] : [];
  });
}

/** Why a guide cannot be published as it stands (public.model_guide_problem), or null. */
export function publishProblem(v: Pick<GuideValues, "body" | "questions" | "sources">): string | null {
  const missing = GUIDE_SECTIONS.filter((key) => !v.body[key].length);
  if (missing.length) return `Falta completar: ${missing.map((k) => GUIDE_SECTION_NAME[k]).join(", ")}.`;
  if (v.questions.length < MIN_QUESTIONS || v.questions.length > MAX_QUESTIONS) return `Van de ${MIN_QUESTIONS} a ${MAX_QUESTIONS} preguntas.`;
  if (!v.sources.length) return "Agregá al menos una fuente y marcá «La revisé».";
  if (v.sources.some((s) => !s.verified)) return "Marcá «La revisé» en cada fuente, o borrá la que no exista.";
  return null;
}

// ---------------------------------------------------------------------------
// Copy lint
// ---------------------------------------------------------------------------

/** worker/intelligence/copy.py RISK_FORBIDDEN: no promise, no accusation, no «agencia» (stems). */
export const GUIDE_RISK_FORBIDDEN = ["robad", "estafa", "fraude", "verificado por ese auto", "certificad", "garantiz", "agencia", "revendedor"];

const MONEY_WORDS = String.raw`(?:\$|(?<![a-z])(?:u\$s|u\$d|usd|us\$|ars|pesos?|dolares?|lucas|palos))`;
const NUMBER = String.raw`\d[\d.,]*(?:\s*(?:mil|millones?|k))?`;
// «$ 300.000», «USD 1.500», «300 mil pesos», «1500 dólares», «$300k». On folded text (worker _MONEY).
const MONEY = new RegExp(`${MONEY_WORDS}\\s*${NUMBER}|${NUMBER}\\s*${MONEY_WORDS}(?![a-z])`);

export function hasMoney(value: string): boolean {
  return MONEY.test(foldText(value));
}

/** The forbidden word or promise in `value`, or null. */
export function copyProblem(value: string): string | null {
  const term = forbiddenTermsIn(value)[0];
  if (term) return term;
  const folded = foldText(value);
  for (const stem of GUIDE_RISK_FORBIDDEN) {
    if (new RegExp(`(^|[^\\p{L}\\p{N}_])${foldText(stem)}`, "u").test(folded)) return stem;
  }
  return null;
}

export type LintIssue = { where: string; message: string };

/** Every line that breaks the copy rules, saying which one (the editor's errors). */
export function lintGuide(v: Pick<GuideValues, "body" | "questions" | "sources">): LintIssue[] {
  const issues: LintIssue[] = [];
  const check = (where: string, value: string | null | undefined) => {
    if (!value) return;
    const term = copyProblem(value);
    if (term) issues.push({ where, message: `usa «${term}», que el copy no permite` });
    if (hasMoney(value)) issues.push({ where, message: "tiene una cifra de dinero" });
  };
  for (const key of GUIDE_SECTIONS) {
    v.body[key].forEach((line, n) => {
      const where = `${GUIDE_SECTION_NAME[key]}, renglón ${n + 1}`;
      check(where, line.text);
      check(where, "applies_to" in line ? line.applies_to : null);
      check(where, "label" in line ? line.label : null);
    });
  }
  v.questions.forEach((q, n) => {
    check(`Pregunta ${n + 1}`, q.text);
    check(`Pregunta ${n + 1}`, q.why);
  });
  v.sources.forEach((s, n) => check(`Fuente ${n + 1}`, s.title));
  return issues;
}

// ---------------------------------------------------------------------------
// The public read
// ---------------------------------------------------------------------------

/** The public columns of a published guide (anon's column grant). */
export type PublicGuideRow = {
  id: number;
  make: string;
  model: string;
  generation_label: string | null;
  year_from: number | null;
  year_to: number | null;
  slug_make: string;
  slug_model: string;
  body: unknown;
  questions: unknown;
  sources: unknown;
  published_at: string | null;
  /** The content's last change (publishing or unpublishing doesn't move it). */
  content_updated_at: string;
};
export const PUBLIC_GUIDE_COLUMNS =
  "id, make, model, generation_label, year_from, year_to, slug_make, slug_model, body, questions, sources, published_at, content_updated_at";

export type PublicGuide = {
  id: number;
  make: string;
  model: string;
  generationLabel: string | null;
  yearFrom: number | null;
  yearTo: number | null;
  slugMake: string;
  slugModel: string;
  body: GuideBody;
  questions: GuideQuestion[];
  /** Only the sources Juan checked (publishing requires all of them checked). */
  sources: GuideSource[];
  /** model_guides.content_updated_at: «Última actualización» and the sitemap's lastModified. */
  updatedAt: string;
  /** model_guides.published_at: the Article's datePublished. */
  publishedAt: string | null;
};

export function toPublicGuide(row: PublicGuideRow): PublicGuide {
  return {
    id: row.id,
    make: row.make,
    model: row.model,
    generationLabel: row.generation_label,
    yearFrom: row.year_from,
    yearTo: row.year_to,
    slugMake: row.slug_make,
    slugModel: row.slug_model,
    body: readBody(row.body),
    questions: readQuestions(row.questions),
    sources: readSources(row.sources).filter((s) => s.verified),
    updatedAt: row.content_updated_at,
    publishedAt: row.published_at,
  };
}

/** The rows of one model, by year (null first: the guide of the whole model). */
export function sortGenerations(guides: PublicGuide[]): PublicGuide[] {
  return [...guides].sort((a, b) => (a.yearFrom ?? 0) - (b.yearFrom ?? 0) || a.id - b.id);
}

/** The years a model's page covers: the smallest start and the largest end. */
export function modelYears(guides: PublicGuide[]): { from: number | null; to: number | null } {
  const froms = guides.map((g) => g.yearFrom).filter((v): v is number => v != null);
  const tos = guides.map((g) => g.yearTo).filter((v): v is number => v != null);
  return { from: froms.length ? Math.min(...froms) : null, to: tos.length ? Math.max(...tos) : null };
}

/** The anchor of a generation in the page. */
export function generationAnchor(guide: PublicGuide): string {
  return guide.generationLabel ? `generacion-${slugify(guide.generationLabel)}` : "guia";
}

/** Every question of the page, once each, ready to copy. */
export function questionsText(guides: PublicGuide[]): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const g of guides) for (const q of g.questions) {
    const key = foldText(q.text).replace(/[^\p{L}\p{N}]+/gu, " ").trim();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(q.text);
    }
  }
  return out.join("\n");
}

/** A line as the FAQ's answer says it: the generation's label and years first, «Aplica a» last. */
function lineAnswer(line: GuideLine | GenerationLine): string {
  const label = "label" in line && line.label ? `${line.label}${line.year_from || line.year_to ? ` (${yearsText(line.year_from, line.year_to)})` : ""}: ` : "";
  const applies = "applies_to" in line && line.applies_to ? ` (${GUIDE_COPY.appliesTo.replace("{text}", line.applies_to)})` : "";
  return `${label}${line.text}${applies}`;
}

/**
 * schema.org FAQPage built from the sections, deterministically: every
 * section and the questions for the seller, each asked as the page's own
 * heading asks it, with the guide's own lines as the answer.
 */
export function faqJsonLd(guides: PublicGuide[], url: string): Record<string, unknown> | null {
  if (!guides.length) return null;
  const name = guideName(guides[0].make, guides[0].model);
  const lines = (key: GuideSection) => guides.flatMap((g) => (g.body[key] as (GuideLine | GenerationLine)[]).map(lineAnswer));
  // The page's own list: each question once across the generations.
  const questions = questionsText(guides).split("\n").filter(Boolean);
  // The first three keep their place (what most people ask); then the rest of the page.
  const entries: [string, string[]][] = [
    [sectionQuestion("known_issues", name), lines("known_issues")],
    [sectionQuestion("visit_checklist", name), lines("visit_checklist")],
    [sectionQuestion("seller", name), questions],
    [sectionQuestion("versions_equipment", name), lines("versions_equipment")],
    [sectionQuestion("maintenance_costs", name), lines("maintenance_costs")],
    [sectionQuestion("generations", name), lines("generations")],
  ];
  const mainEntity = entries
    .filter(([, answer]) => answer.length)
    .map(([q, answer]) => ({
      "@type": "Question",
      name: q,
      acceptedAnswer: { "@type": "Answer", text: `${GUIDE_COPY.badge}. ${answer.join(" ")}` },
    }));
  if (!mainEntity.length) return null;
  return { "@context": "https://schema.org", "@type": "FAQPage", url, inLanguage: "es-AR", mainEntity };
}

/** JSON for a <script type="application/ld+json">, with «<» escaped (Next's JSON-LD guide). */
export function jsonLdScript(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

/** A guide line as the end of a sentence: no trailing period or spaces. */
function clause(text: string): string {
  return text.trim().replace(/[.\s]+$/, "");
}

/**
 * «En resumen»: the answer-first paragraph at the top of the page, built from
 * the guide's own lines (the first known issue and the first thing to check),
 * so a search or answer engine can quote it as it stands. null without either.
 */
export function guideSummary(guides: PublicGuide[]): string | null {
  const parts = guideSummaryParts(guides);
  return parts ? parts.map((p) => p.text).join("") : null;
}

/** A piece of «En resumen»; `mark`: what to check first, the one highlighted thing on the page. */
export type SummaryPart = { text: string; mark?: true };

/** guideSummary in pieces, so the page can highlight what to check first. */
export function guideSummaryParts(guides: PublicGuide[]): SummaryPart[] | null {
  if (!guides.length) return null;
  const name = guideName(guides[0].make, guides[0].model);
  // Each line with the guide it comes from: its label and years are that guide's, not the page's.
  const first = (key: "known_issues" | "visit_checklist") => {
    for (const g of guides) if (g.body[key].length) return { guide: g, line: g.body[key][0] };
    return null;
  };
  const withApplies = (line: GuideLine) =>
    line.applies_to ? `${clause(line.text)} (${GUIDE_COPY.appliesTo.replace("{text}", clause(line.applies_to))})` : clause(line.text);
  const issue = first("known_issues");
  const check = first("visit_checklist");
  if (!issue && !check) return null;
  const parts: SummaryPart[] = [];
  if (issue) {
    const scope = [issue.guide.generationLabel, yearsText(issue.guide.yearFrom, issue.guide.yearTo)].filter(Boolean).join(", ");
    parts.push({ text: `${GUIDE_COPY.summaryIssue.replace("{name}", name).replace("{years}", scope ? ` (${scope})` : "").replace("{text}", withApplies(issue.line))} ` });
  }
  if (check) {
    const [before, after] = GUIDE_COPY.summaryCheck.split("{text}");
    // Only the first clause is highlighted («Si es I-Motion, probala en tránsito y en subida»): a swipe, not a paragraph.
    const text = withApplies(check.line);
    const head = /^(.{12,}?)(?=[:;.]\s|\s\()/.exec(text)?.[1] ?? text;
    parts.push({ text: before }, { text: head, mark: true });
    if (head.length < text.length) parts.push({ text: text.slice(head.length) });
    parts.push({ text: `${after} ` });
  }
  parts.push({ text: GUIDE_COPY.summaryClose });
  return parts;
}

/**
 * The page's datePublished (its first guide's published_at) and dateModified:
 * the latest content_updated_at, but never before datePublished (publishing
 * sets published_at to now and leaves content_updated_at as it was).
 */
export function guideDates(guides: PublicGuide[]): { published: string | null; modified: string | null } {
  const time = (v: string) => Date.parse(v);
  const published = guides.map((g) => g.publishedAt).filter((v): v is string => Boolean(v)).sort((a, b) => time(a) - time(b))[0] ?? null;
  const updated = guides.map((g) => g.updatedAt).filter(Boolean).sort((a, b) => time(a) - time(b)).at(-1) ?? null;
  const modified = updated && published ? (time(published) > time(updated) ? published : updated) : (updated ?? published);
  return { published, modified };
}

/** schema.org Organization: the site, author and publisher of the guides. */
export function organizationJsonLd(site: string): Record<string, unknown> {
  return { "@type": "Organization", name: SITE_NAME, url: `${site}/` };
}

/**
 * schema.org Article for a model's page: the headline and description of its
 * metadata, published when its first guide was, modified when its content
 * last changed (never before it was published), about the model (Car: brand,
 * model, its years in the name; vehicleModelDate only for a single year).
 */
export function articleJsonLd(guides: PublicGuide[], site: string): Record<string, unknown> | null {
  if (!guides.length) return null;
  const { make, model, slugMake, slugModel } = guides[0];
  const years = modelYears(guides);
  const url = `${site}${guidePath(slugMake, slugModel)}`;
  const { published, modified } = guideDates(guides);
  const span = yearsText(years.from, years.to);
  const org = organizationJsonLd(site);
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: guideTitle(make, model),
    description: guideDescription(make, model, yearsText(years.from, years.to)),
    url,
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    inLanguage: "es-AR",
    ...(published ? { datePublished: published } : {}),
    ...(modified ? { dateModified: modified } : {}),
    author: org,
    publisher: org,
    about: {
      "@type": "Car",
      // The years in words, as the page says them: schema.org's vehicleModelDate is a single date.
      name: span ? `${guideName(make, model)} ${span}` : guideName(make, model),
      brand: { "@type": "Brand", name: make },
      model,
      ...(years.from && years.from === years.to ? { vehicleModelDate: String(years.from) } : {}),
    },
  };
}

/** schema.org BreadcrumbList: Inicio › Guías › the model. */
export function breadcrumbJsonLd(items: { name: string; url: string }[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, n) => ({ "@type": "ListItem", position: n + 1, name: item.name, item: item.url })),
  };
}

/** The breadcrumb of a model's page. */
export function guideBreadcrumb(make: string, model: string, slugMake: string, slugModel: string, site: string) {
  return breadcrumbJsonLd([
    { name: GUIDE_COPY.home, url: `${site}/` },
    { name: GUIDE_COPY.indexTitle, url: `${site}/guias` },
    { name: make, url: `${site}${makePath(slugMake)}` },
    { name: guideName(make, model), url: `${site}${guidePath(slugMake, slugModel)}` },
  ]);
}

/** schema.org CollectionPage of /guias/<marca>, with an ItemList of the make's published models. */
export function makeIndexJsonLd(
  make: string,
  slugMake: string,
  entries: { make: string; model: string; slugMake: string; slugModel: string }[],
  site: string,
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: GUIDE_COPY.makeTitle.replace("{make}", make),
    description: GUIDE_COPY.makeIntro.replace("{make}", make),
    url: `${site}${makePath(slugMake)}`,
    inLanguage: "es-AR",
    publisher: organizationJsonLd(site),
    about: { "@type": "Brand", name: make },
    mainEntity: {
      "@type": "ItemList",
      numberOfItems: entries.length,
      itemListElement: entries.map((e, n) => ({
        "@type": "ListItem",
        position: n + 1,
        name: guideName(e.make, e.model),
        url: `${site}${guidePath(e.slugMake, e.slugModel)}`,
      })),
    },
  };
}

/** The breadcrumb of a make's page: Inicio › Guías › the make. */
export function makeBreadcrumb(make: string, slugMake: string, site: string) {
  return breadcrumbJsonLd([
    { name: GUIDE_COPY.home, url: `${site}/` },
    { name: GUIDE_COPY.indexTitle, url: `${site}/guias` },
    { name: make, url: `${site}${makePath(slugMake)}` },
  ]);
}

/**
 * «Otras guías» under a model's page: the make's other models first, then
 * others spread across the index in a stable per-page order (every guide gets
 * links from somewhere, and a page's list doesn't move between visits).
 */
export function relatedGuides<T extends { slugMake: string; slugModel: string }>(
  index: readonly T[],
  slugMake: string,
  slugModel: string,
  count = 6,
): T[] {
  const others = index.filter((e) => !(e.slugMake === slugMake && e.slugModel === slugModel));
  const sameMake = others.filter((e) => e.slugMake === slugMake);
  const seed = hash(`${slugMake}/${slugModel}`);
  const rest = others
    .filter((e) => e.slugMake !== slugMake)
    .map((e) => ({ e, k: hash(`${seed}:${e.slugMake}/${e.slugModel}`) }))
    .sort((x, y) => x.k - y.k)
    .map(({ e }) => e);
  return [...sameMake, ...rest].slice(0, count);
}

/** FNV-1a, 32 bits: a stable order, not security. */
function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193) >>> 0;
  return h;
}

/** schema.org CollectionPage of /guias, with an ItemList of every published model. */
export function guideIndexJsonLd(entries: { make: string; model: string; slugMake: string; slugModel: string }[], site: string): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: GUIDE_COPY.indexTitle,
    description: GUIDE_COPY.indexIntro,
    url: `${site}/guias`,
    inLanguage: "es-AR",
    publisher: organizationJsonLd(site),
    mainEntity: {
      "@type": "ItemList",
      numberOfItems: entries.length,
      itemListElement: entries.map((e, n) => ({
        "@type": "ListItem",
        position: n + 1,
        name: guideName(e.make, e.model),
        url: `${site}${guidePath(e.slugMake, e.slugModel)}`,
      })),
    },
  };
}

/** «12 de noviembre de 2026», Argentina's calendar. */
export function guideDate(iso: string): string {
  return new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "long", year: "numeric", timeZone: "America/Argentina/Buenos_Aires" })
    .format(new Date(iso));
}
