/**
 * PRO-01 paso 2 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md,
 * decisiones 13-19): the message for the seller, ready to copy. The twin of
 * worker/intelligence/contact_message.py; both are fixed by
 * worker/tests/fixtures/contact_message/golden.json.
 *
 * The template (profiles.contact_template, or the default) has two markers,
 * {auto} and {preguntas}, replaced literally in one pass (the inserted text is
 * not scanned again). A stored template is linted again here and falls back
 * to the default one: one written by API never reaches the page. {auto} is
 * the catalog's model and the year, never the listing's title.
 */
import { CONTACT_MESSAGE, lintContactTemplate } from "@/lib/copy";

const MARKER = /\{(auto|preguntas)\}/g;
const AUTO = /^[\p{L}\p{N} .-]{1,40}$/u;

/** «Fiesta 2017»; «auto» without a catalog model or off the pattern. */
export function autoText(catalogModel: string | null | undefined, year: number | null | undefined): string {
  const model = (catalogModel ?? "").trim();
  if (!model) return CONTACT_MESSAGE.auto;
  const value = Number.isInteger(year) && year! >= 1950 && year! <= 2100 ? `${model} ${year}` : model;
  return AUTO.test(value) && [...value].length <= 40 ? value : CONTACT_MESSAGE.auto;
}

function fill(template: string, auto: string, questions: string): string {
  const values: Record<string, string> = { auto, preguntas: questions };
  return template.replace(MARKER, (_, key: string) => values[key]);
}

/** The message: 3-4 lines with the default template. Never throws. */
export function renderContactMessage(
  template: string | null | undefined,
  catalogModel: string | null | undefined,
  year: number | null | undefined,
  questions: readonly string[] | null | undefined,
): string {
  const auto = autoText(catalogModel, year);
  const asked = [CONTACT_MESSAGE.available, questions?.[0] || CONTACT_MESSAGE.holder].join("\n");
  try {
    const { value, error } = lintContactTemplate(template);
    return fill(value && !error ? value : CONTACT_MESSAGE.default, auto, asked);
  } catch {
    return fill(CONTACT_MESSAGE.default, auto, asked);
  }
}

/** «Consulta por tu Fiesta 2017». */
export function contactSubject(catalogModel: string | null | undefined, year: number | null | undefined): string {
  return CONTACT_MESSAGE.subject.replace("{auto}", autoText(catalogModel, year));
}

/**
 * A mailto: without a recipient (Ese Auto has no seller address): each field
 * through encodeURIComponent (URLSearchParams would turn spaces into «+»,
 * which mail clients show as is) and CRLF line breaks (RFC 6068).
 */
export function mailtoHref(subject: string, body: string): string {
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body.replace(/\r?\n/g, "\r\n"))}`;
}
