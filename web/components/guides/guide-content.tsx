import { ChevronDown, Info, MessageCircle } from "lucide-react";
import type { ReactNode } from "react";

import { CopyGuideQuestions } from "@/components/guides/copy-guide-questions";
import { GuideChapterOpener } from "@/components/guides/guide-chapter-opener";
import { GuideVisit } from "@/components/guides/guide-visit";
import {
  type GenerationLine,
  generationAnchor,
  GUIDE_COPY,
  guideDate,
  type GuideLine,
  guideName,
  type GuideSection,
  type PublicGuide,
  questionsText,
  sectionQuestion,
  yearsText,
} from "@/lib/guides";

/** The «Guía orientativa» notice, first thing on the page. */
export function GuideNotice() {
  return (
    <p role="note" data-testid="guide-notice" className="flex gap-2.5 rounded-md border border-amber-300 bg-amber-50 px-3.5 py-3 text-[15px] leading-snug text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-50">
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{GUIDE_COPY.notice}</span>
    </p>
  );
}

type ChapterKey = GuideSection | "seller";

/** Each chapter's anchor: short and in Spanish, so a shared link reads well (/guias/…#visita). */
export const CHAPTER_ID: Record<ChapterKey, string> = {
  known_issues: "fallas",
  visit_checklist: "visita",
  seller: "vendedor",
  versions_equipment: "versiones",
  maintenance_costs: "mantenimiento",
  generations: "generaciones",
};

/** Each chapter in the index at the top. */
const TOC_NAME: Record<ChapterKey, string> = {
  known_issues: "Fallas conocidas",
  visit_checklist: "Qué revisar en la visita",
  seller: "Qué preguntarle al vendedor",
  versions_equipment: "Versiones y equipamiento",
  maintenance_costs: "Mantenimiento",
  generations: "Generaciones",
};

/** The order of the page: what to know before going, the visit, the seller; then the reference chapters, folded. */
const ORDER: ChapterKey[] = ["known_issues", "visit_checklist", "seller", "versions_equipment", "maintenance_costs", "generations"];
const FOLDED = new Set<ChapterKey>(["versions_equipment", "maintenance_costs", "generations"]);

type Chapter = { key: ChapterKey; count: number; body: ReactNode };

/** A generation's name in its chapter: «E170 · 2014 a 2019», «Todo el modelo» without a label. */
function groupLabel(g: PublicGuide): string {
  return [g.generationLabel ?? "Todo el modelo", yearsText(g.yearFrom, g.yearTo)].filter(Boolean).join(" · ");
}

function Lines({ lines }: { lines: GuideLine[] }) {
  return (
    <ul>
      {lines.map((line, n) => (
        <li key={n} className="border-b py-3.5 text-[16px] leading-relaxed last:border-b-0">
          {line.text}
          {line.applies_to ? (
            <span className="mt-2 block w-fit rounded bg-muted px-2 py-0.5 text-[13px] text-muted-foreground">{GUIDE_COPY.appliesTo.replace("{text}", line.applies_to)}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function Timeline({ lines }: { lines: GenerationLine[] }) {
  return (
    <ol className="ml-1.5 border-l-2 pl-5">
      {lines.map((line, n) => (
        <li key={n} className="relative pb-4 text-[16px] leading-relaxed last:pb-0">
          <span aria-hidden="true" className="absolute top-1.5 -left-[29px] size-3 rounded-full border-2 border-foreground bg-background" />
          {line.year_from || line.year_to ? <span className="type-figure block text-[15px]">{yearsText(line.year_from, line.year_to)}</span> : null}
          {line.label ? <strong className="font-semibold">{line.label}. </strong> : null}
          {line.text}
        </li>
      ))}
    </ol>
  );
}

/** A chapter's numbered head, like the landing's «Cómo funciona»: a big number and the question. */
function ChapterHead({ n, id, title, folded }: { n: number; id: string; title: string; folded?: boolean }) {
  return (
    <div className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-start gap-x-2.5 border-t-2 border-foreground pt-3.5">
      <span aria-hidden="true" className="type-display text-[40px] leading-[0.9]">{n}</span>
      <h2 id={`${id}-titulo`} className="type-heading text-[21px] leading-tight text-balance">{title}</h2>
      {folded ? <ChevronDown aria-hidden="true" className="mt-0.5 size-6 transition-transform group-open:rotate-180" /> : null}
    </div>
  );
}

/**
 * A model's published guides (one per generation) as a printed guide read with
 * a highlighter: an index, then numbered chapters, each the question people
 * ask. Fallas, the visit (to tick standing next to the car) and the questions
 * for the seller are open; versions, maintenance and generations are folded
 * (still in the HTML: engines read them). With several generations each
 * chapter has one block per generation. Nothing about who reviewed it,
 * whether an LLM drafted it, prices or the platform. The admin's preview uses
 * it too (`slugMake` absent: copying logs nothing and ticks aren't kept).
 */
export function GuideContent({ guides, slugMake, slugModel }: { guides: PublicGuide[]; slugMake?: string; slugModel?: string }) {
  const many = guides.length > 1;
  const updated = guides.map((g) => g.updatedAt).sort().at(-1);
  const sources = guides.flatMap((g) => g.sources);
  const questions = questionsText(guides);
  const name = guideName(guides[0]?.make ?? "", guides[0]?.model ?? "");
  const withLines = (key: GuideSection) => guides.filter((g) => g.body[key].length);

  /** One block per generation that has lines (with its name when there are several). */
  function groups(key: GuideSection, render: (g: PublicGuide) => ReactNode, anchors = false) {
    return (
      <div className="space-y-6">
        {withLines(key).map((g) => (
          <div key={g.id}>
            {many ? <h3 id={anchors ? generationAnchor(g) : undefined} className="type-heading scroll-mt-6 text-lg">{groupLabel(g)}</h3> : null}
            {render(g)}
          </div>
        ))}
      </div>
    );
  }

  const count = (key: GuideSection) => guides.reduce((n, g) => n + g.body[key].length, 0);
  const all: Chapter[] = [
    { key: "known_issues", count: count("known_issues"), body: groups("known_issues", (g) => <Lines lines={g.body.known_issues} />, true) },
    {
      key: "visit_checklist",
      count: count("visit_checklist"),
      body: (
        <GuideVisit
          storageKey={slugMake && slugModel ? `guia-visita:${slugMake}/${slugModel}` : null}
          groups={withLines("visit_checklist").map((g) => ({
            key: String(g.id),
            label: many ? groupLabel(g) : null,
            items: g.body.visit_checklist.map((l) => ({ text: l.text, applies: l.applies_to ?? null })),
          }))}
        />
      ),
    },
    {
      key: "seller",
      count: questions ? questions.split("\n").length : 0,
      body: questions ? (
        <div className="rounded-md bg-muted px-4 pt-1.5 pb-4">
          <ol className="mb-4 list-decimal pl-5 text-[16px] leading-snug" data-testid="guide-questions">
            {questions.split("\n").map((q) => <li key={q} className="border-b border-background py-2.5 pl-1">{q}</li>)}
          </ol>
          <CopyGuideQuestions text={questions} slugMake={slugMake} slugModel={slugModel}>
            <a
              href={`https://wa.me/?text=${encodeURIComponent(`${GUIDE_COPY.whatsappIntro.replace("{name}", name)}\n${questions.split("\n").map((q, n) => `${n + 1}. ${q}`).join("\n")}`)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-[16px] font-semibold text-primary-foreground"
            >
              <MessageCircle aria-hidden="true" className="size-5" />
              {GUIDE_COPY.whatsapp}
            </a>
          </CopyGuideQuestions>
        </div>
      ) : null,
    },
    { key: "versions_equipment", count: count("versions_equipment"), body: groups("versions_equipment", (g) => <Lines lines={g.body.versions_equipment} />) },
    { key: "maintenance_costs", count: count("maintenance_costs"), body: groups("maintenance_costs", (g) => <Lines lines={g.body.maintenance_costs} />) },
    { key: "generations", count: count("generations"), body: groups("generations", (g) => <Timeline lines={g.body.generations} />) },
  ];
  const chapters = ORDER.map((key) => all.find((c) => c.key === key)!).filter((c) => c.count > 0);

  return (
    <div className="space-y-7">
      <GuideChapterOpener />
      {many ? (
        <nav aria-label="Generaciones" className="flex flex-wrap gap-2 text-sm">
          {guides.map((g) => (
            <a key={g.id} href={`#${generationAnchor(g)}`} className="inline-flex min-h-10 items-center rounded-md bg-muted px-3 underline-offset-4 hover:underline">
              {groupLabel(g)}
            </a>
          ))}
        </nav>
      ) : null}

      {chapters.length > 1 ? (
        <nav aria-labelledby="guide-toc">
          <h2 id="guide-toc" className="sr-only">{GUIDE_COPY.toc}</h2>
          <ol className="border-t-2 border-foreground">
            {chapters.map((c, n) => (
              <li key={c.key}>
                <a href={`#${CHAPTER_ID[c.key]}`} className="grid min-h-[50px] grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-x-1 border-b py-2 text-[16px] font-semibold">
                  <span className="type-figure text-xl">{n + 1}</span>
                  <span>{TOC_NAME[c.key]}</span>
                  <span className="text-[13px] font-normal text-muted-foreground">{c.count}</span>
                </a>
              </li>
            ))}
          </ol>
        </nav>
      ) : null}

      {chapters.map((c, n) => {
        const id = CHAPTER_ID[c.key];
        const title = sectionQuestion(c.key, name);
        return FOLDED.has(c.key) ? (
          <details key={c.key} id={id} className="group scroll-mt-4 pt-3" aria-labelledby={`${id}-titulo`}>
            <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
              <ChapterHead n={n + 1} id={id} title={title} folded />
            </summary>
            <div className="mt-2">{c.body}</div>
          </details>
        ) : (
          <section key={c.key} id={id} className="scroll-mt-4 pt-3" aria-labelledby={`${id}-titulo`}>
            <ChapterHead n={n + 1} id={id} title={title} />
            <div className="mt-3">{c.body}</div>
          </section>
        );
      })}

      {sources.length ? (
        <details className="group pt-2 text-sm text-muted-foreground">
          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 font-semibold [&::-webkit-details-marker]:hidden">
            <h2 id="guide-sources" className="inline">{GUIDE_COPY.sourcesFold.replace("{n}", String(sources.length))}</h2>
            <ChevronDown aria-hidden="true" className="size-4 transition-transform group-open:rotate-180" />
          </summary>
          <ul className="space-y-1.5 pb-2">
            {sources.map((s) => (
              <li key={s.url} className="[overflow-wrap:anywhere]">
                <a href={s.url} rel="nofollow noopener noreferrer" target="_blank" className="underline underline-offset-4">{s.title}</a> ({s.kind})
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {updated ? <p className="text-sm text-muted-foreground">{GUIDE_COPY.updated.replace("{date}", guideDate(updated))}</p> : null}
    </div>
  );
}
