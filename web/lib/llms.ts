/**
 * PAR-04 · llms.txt (https://llmstxt.org): what the site is and its public
 * guides, in Markdown, for answer engines. Pure: the route handlers in
 * app/llms.txt and app/llms-full.txt read the published guides and call these.
 */
import {
  GUIDE_COPY,
  GUIDE_SECTION_NAME,
  GUIDE_SECTIONS,
  guideDescription,
  guidePath,
  guideTitle,
  makePath,
  METHOD_PATH,
  modelYears,
  type PublicGuide,
  questionsText,
  SITE_NAME,
  yearsText,
} from "@/lib/guides";

export const LLMS_COPY = {
  summary: "Servicio argentino para quien busca un auto usado: nos contás qué auto querés y te avisamos cuando aparece publicado uno que coincide.",
  about:
    "En eseauto.com.ar describís el auto que buscás con tus palabras (marca, modelo, años, presupuesto, zona) y Ese Auto revisa las publicaciones de usados por vos. Cuando aparece uno que coincide, te avisa con el link a la publicación y preguntas para hacerle al vendedor. Las guías orientativas por modelo resumen fallas conocidas, qué revisar en la visita, versiones, mantenimiento y qué preguntar. Son información general: no verifican ningún auto en particular ni reemplazan la revisión de un mecánico de confianza.",
  guidesTitle: "Guías orientativas por modelo",
  noGuides: "Todavía no hay guías publicadas.",
  optionalTitle: "Optional",
  fullText: "Texto completo de todas las guías publicadas",
  pages: "Páginas",
  home: "Inicio: cómo funciona y crear una búsqueda",
  plans: "Planes",
  method: "Cómo hacemos las guías: fuentes, revisión y actualización",
  makes: "Guías por marca",
} as const;

/** Markdown text of a line: no newlines (a line never breaks the list). */
function inline(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function modelSummary(guides: PublicGuide[]): string {
  const { make, model } = guides[0];
  const years = modelYears(guides);
  return guideDescription(make, model, yearsText(years.from, years.to));
}

function header(): string[] {
  return [`# ${SITE_NAME} (eseauto.com.ar)`, "", `> ${LLMS_COPY.summary}`, "", LLMS_COPY.about, ""];
}

/** /llms.txt: the site in a paragraph, /guias and each published model with a line. */
export function llmsTxt(models: PublicGuide[][], site: string): string {
  const out = header();
  out.push(`## ${LLMS_COPY.guidesTitle}`, "", `- [${GUIDE_COPY.indexTitle}](${site}/guias): ${GUIDE_COPY.indexIntro}`);
  const published = models.filter((m) => m.length);
  for (const guides of published) {
    const { make, model, slugMake, slugModel } = guides[0];
    out.push(`- [${guideTitle(make, model)}](${site}${guidePath(slugMake, slugModel)}): ${modelSummary(guides)}`);
  }
  if (!published.length) out.push("", LLMS_COPY.noGuides);
  const makes = new Map(published.map((guides) => [guides[0].slugMake, guides[0].make]));
  if (makes.size) {
    out.push("", `## ${LLMS_COPY.makes}`, "");
    for (const [slugMake, make] of makes) out.push(`- [${GUIDE_COPY.makeTitle.replace("{make}", make)}](${site}${makePath(slugMake)})`);
  }
  out.push(
    "",
    `## ${LLMS_COPY.pages}`,
    "",
    `- [${LLMS_COPY.home}](${site}/)`,
    `- [${LLMS_COPY.plans}](${site}/planes)`,
    `- [${LLMS_COPY.method}](${site}${METHOD_PATH})`,
  );
  if (published.length) out.push("", `## ${LLMS_COPY.optionalTitle}`, "", `- [${LLMS_COPY.fullText}](${site}/llms-full.txt)`);
  return `${out.join("\n")}\n`;
}

/** One model's guides in Markdown: the sections, the questions and the checked sources. */
export function guideMarkdown(guides: PublicGuide[], site: string): string {
  const { make, model, slugMake, slugModel } = guides[0];
  const many = guides.length > 1;
  const updated = guides.map((g) => g.updatedAt).sort().at(-1);
  const out = [`## ${guideTitle(make, model)}`, "", `URL: ${site}${guidePath(slugMake, slugModel)}`];
  if (updated) out.push(`Última actualización: ${updated.slice(0, 10)}`);
  out.push("", GUIDE_COPY.notice, "");
  for (const g of guides) {
    const level = many ? "####" : "###";
    if (many) out.push(`### ${inline(g.generationLabel ?? "Todo el modelo")}${g.yearFrom || g.yearTo ? ` (${yearsText(g.yearFrom, g.yearTo)})` : ""}`, "");
    for (const key of GUIDE_SECTIONS) {
      if (!g.body[key].length) continue;
      out.push(`${level} ${GUIDE_SECTION_NAME[key]}`, "");
      for (const line of g.body[key]) {
        const label = "label" in line && line.label ? `${inline(line.label)}${line.year_from || line.year_to ? ` (${yearsText(line.year_from, line.year_to)})` : ""}: ` : "";
        const applies = "applies_to" in line && line.applies_to ? ` (${GUIDE_COPY.appliesTo.replace("{text}", inline(line.applies_to))})` : "";
        out.push(`- ${label}${inline(line.text)}${applies}`);
      }
      out.push("");
    }
  }
  const questions = questionsText(guides).split("\n").filter(Boolean);
  if (questions.length) {
    out.push(`### ${GUIDE_COPY.questionsTitle}`, "", ...questions.map((q, n) => `${n + 1}. ${inline(q)}`), "");
  }
  const sources = guides.flatMap((g) => g.sources);
  if (sources.length) {
    out.push(`### ${GUIDE_COPY.sourcesTitle}`, "", ...sources.map((s) => `- [${inline(s.title)}](${s.url}) (${s.kind})`), "");
  }
  return out.join("\n");
}

/** /llms-full.txt: the header and the full text of every published guide. */
export function llmsFullTxt(models: PublicGuide[][], site: string): string {
  const published = models.filter((m) => m.length);
  const out = header();
  out.push(`# ${LLMS_COPY.guidesTitle}`, "");
  if (!published.length) out.push(LLMS_COPY.noGuides, "");
  for (const guides of published) out.push(guideMarkdown(guides, site));
  return `${out.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}

