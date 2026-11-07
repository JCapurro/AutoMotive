import { Info } from "lucide-react";

import { CopyGuideQuestions } from "@/components/guides/copy-guide-questions";
import {
  generationAnchor,
  GUIDE_COPY,
  GUIDE_SECTIONS,
  guideDate,
  guideName,
  type PublicGuide,
  questionsText,
  sectionQuestion,
  yearsText,
} from "@/lib/guides";

/**
 * Who a section's question is about: the model, or with several generations
 * the model and the generation («Toyota Corolla E170»), unless the label
 * already is the model («Gol Trend» of the Gol Trend).
 */
function subject(name: string, label: string | null, many: boolean): string {
  if (!many || !label || name.toLowerCase().includes(label.toLowerCase())) return name;
  return `${name} ${label}`;
}

/** The «Guía orientativa» notice, first thing on the page. */
export function GuideNotice() {
  return (
    <p role="note" data-testid="guide-notice" className="flex gap-2.5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-[15px] leading-snug text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-50">
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{GUIDE_COPY.notice}</span>
    </p>
  );
}

/**
 * A model's published guides (one per generation): the five sections, the
 * questions for the seller, the checked sources and the date. Nothing about
 * who reviewed it, whether an LLM drafted it, prices or the platform. The
 * admin's preview uses it too (`slugMake` absent: copying logs nothing).
 */
export function GuideContent({ guides, slugMake, slugModel }: { guides: PublicGuide[]; slugMake?: string; slugModel?: string }) {
  const many = guides.length > 1;
  const updated = guides.map((g) => g.updatedAt).sort().at(-1);
  const sources = guides.flatMap((g) => g.sources);
  const questions = questionsText(guides);
  // One guide: its sections are the page's h2; several: each generation is.
  const Heading = many ? "h3" : "h2";
  const name = guideName(guides[0]?.make ?? "", guides[0]?.model ?? "");
  return (
    <div className="space-y-10">
      {many ? (
        <nav aria-label="Generaciones" className="flex flex-wrap gap-2 text-sm">
          {guides.map((g) => (
            <a key={g.id} href={`#${generationAnchor(g)}`} className="rounded-md bg-muted px-2.5 py-1.5 underline-offset-4 hover:underline">
              {g.generationLabel ?? "Todo el modelo"} {yearsText(g.yearFrom, g.yearTo)}
            </a>
          ))}
        </nav>
      ) : null}

      {guides.map((g) => (
        <article key={g.id} id={generationAnchor(g)} className="scroll-mt-24 space-y-8">
          {many ? <h2 className="type-display text-2xl">{g.generationLabel ?? "Todo el modelo"} <span className="text-muted-foreground">{yearsText(g.yearFrom, g.yearTo)}</span></h2> : null}
          {GUIDE_SECTIONS.map((key) => g.body[key].length ? (
            <section key={key} aria-labelledby={`${generationAnchor(g)}-${key}`} className="space-y-3">
              <Heading id={`${generationAnchor(g)}-${key}`} className="text-xl font-semibold tracking-tight">{sectionQuestion(key, subject(name, g.generationLabel, many))}</Heading>
              <ul className="list-disc space-y-2 pl-5 text-[16px] leading-relaxed">
                {g.body[key].map((line, n) => (
                  <li key={n}>
                    {"label" in line && line.label ? <strong className="font-semibold">{line.label}{"year_from" in line && (line.year_from || line.year_to) ? ` (${yearsText(line.year_from, line.year_to)})` : ""}: </strong> : null}
                    {line.text}
                    {"applies_to" in line && line.applies_to ? <span className="block text-sm text-muted-foreground">{GUIDE_COPY.appliesTo.replace("{text}", line.applies_to)}</span> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null)}
        </article>
      ))}

      {questions ? (
        <section aria-labelledby="guide-questions" className="space-y-3 rounded-xl bg-muted/60 p-4 sm:p-6">
          <h2 id="guide-questions" className="text-xl font-semibold tracking-tight">{sectionQuestion("seller", name)}</h2>
          <ol className="list-decimal space-y-2 pl-5 text-[16px] leading-relaxed" data-testid="guide-questions">
            {questions.split("\n").map((q) => <li key={q}>{q}</li>)}
          </ol>
          <CopyGuideQuestions text={questions} slugMake={slugMake} slugModel={slugModel} />
        </section>
      ) : null}

      {sources.length ? (
        <section aria-labelledby="guide-sources" className="space-y-2">
          <h2 id="guide-sources" className="text-base font-semibold">{GUIDE_COPY.sourcesTitle}</h2>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {sources.map((s) => (
              <li key={s.url} className="[overflow-wrap:anywhere]">
                <a href={s.url} rel="nofollow noopener noreferrer" target="_blank" className="underline underline-offset-4">{s.title}</a> ({s.kind})
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {updated ? <p className="text-sm text-muted-foreground">{GUIDE_COPY.updated.replace("{date}", guideDate(updated))}</p> : null}
    </div>
  );
}
