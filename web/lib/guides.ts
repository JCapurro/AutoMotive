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
} as const;

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
  updated_at: string;
};
export const PUBLIC_GUIDE_COLUMNS =
  "id, make, model, generation_label, year_from, year_to, slug_make, slug_model, body, questions, sources, published_at, updated_at";

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
  updatedAt: string;
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
    updatedAt: row.updated_at,
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

/**
 * schema.org FAQPage built from the sections, deterministically: known
 * issues, what to check and what to ask, with the guide's own lines.
 */
export function faqJsonLd(guides: PublicGuide[], url: string): Record<string, unknown> | null {
  if (!guides.length) return null;
  const name = guideName(guides[0].make, guides[0].model);
  const lines = (key: "known_issues" | "visit_checklist") => guides.flatMap((g) => g.body[key].map((l) => l.text));
  const questions = guides.flatMap((g) => g.questions.map((q) => q.text));
  const entries: [string, string[]][] = [
    [`¿Qué fallas conocidas tiene el ${name}?`, lines("known_issues")],
    [`¿Qué revisar al ver un ${name} usado?`, lines("visit_checklist")],
    [`¿Qué preguntarle al vendedor de un ${name}?`, [...new Set(questions)]],
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

/** «12 de noviembre de 2026», Argentina's calendar. */
export function guideDate(iso: string): string {
  return new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "long", year: "numeric", timeZone: "America/Argentina/Buenos_Aires" })
    .format(new Date(iso));
}
