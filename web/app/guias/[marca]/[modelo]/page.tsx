import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { GuideContent, GuideNotice } from "@/components/guides/guide-content";
import { GuideCta } from "@/components/guides/guide-cta";
import { GuideLeaders } from "@/components/guides/guide-leaders";
import { GuideTracker } from "@/components/guides/guide-tracker";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { siteUrl } from "@/lib/env";
import {
  articleJsonLd,
  ctaPrompt,
  faqJsonLd,
  GUIDE_COPY,
  guideBreadcrumb,
  guideDate,
  guideDates,
  guideDescription,
  guideName,
  guidePath,
  guideSummaryParts,
  guideTitle,
  jsonLdScript,
  makePath,
  METHOD_PATH,
  modelYears,
  relatedGuides,
  yearsText,
} from "@/lib/guides";
import { type GuideIndexEntry, publishedGuideIndex, publishedModelGuides } from "@/lib/guides-data";

// PAR-04: ISR. Nothing is built at deploy time (a database problem never
// breaks the build); each page is generated on its first visit, cached for an
// hour and invalidated at once when Juan publishes (revalidatePath in
// app/admin/guides/actions.ts). The page reads no cookies: the anonymous
// client and RLS (published only) decide what exists.
export const revalidate = 3600;
export const dynamicParams = true;

export async function generateStaticParams(): Promise<{ marca: string; modelo: string }[]> {
  return [];
}

export async function generateMetadata({ params }: PageProps<"/guias/[marca]/[modelo]">): Promise<Metadata> {
  const { marca, modelo } = await params;
  const guides = await publishedModelGuides(marca, modelo);
  if (!guides) return { title: "No encontramos esta guía", robots: { index: false } };
  const { make, model } = guides[0];
  const years = modelYears(guides);
  const title = guideTitle(make, model);
  const description = guideDescription(make, model, yearsText(years.from, years.to));
  const path = guidePath(marca, modelo);
  const dates = guideDates(guides);
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      type: "article",
      locale: "es_AR",
      siteName: "eseauto.com.ar",
      title,
      description,
      url: path,
      ...(dates.modified ? { modifiedTime: dates.modified } : {}),
      ...(dates.published ? { publishedTime: dates.published } : {}),
    },
  };
}

const WRAP = "mx-auto w-full max-w-3xl px-4 sm:px-6";

/** «Otras guías» is extra: a problem reading the index never takes the guide down. */
async function indexOrEmpty(): Promise<GuideIndexEntry[]> {
  try {
    return await publishedGuideIndex();
  } catch {
    return [];
  }
}

/** /guias/<marca>/<modelo>: the published guides of one model. 404 for anything else. */
export default async function GuidePage({ params }: PageProps<"/guias/[marca]/[modelo]">) {
  const { marca, modelo } = await params;
  const guides = await publishedModelGuides(marca, modelo);
  if (!guides) notFound();
  const { make, model } = guides[0];
  const name = guideName(make, model);
  const years = modelYears(guides);
  // Everything an engine reads is in the HTML (server-rendered): the FAQ first,
  // then the Article and the breadcrumb, and the «En resumen» paragraph on top.
  const faq = faqJsonLd(guides, `${siteUrl}${guidePath(marca, modelo)}`);
  const article = articleJsonLd(guides, siteUrl);
  const breadcrumb = guideBreadcrumb(make, model, marca, modelo, siteUrl);
  const summary = guideSummaryParts(guides);
  const sources = guides.reduce((n, g) => n + g.sources.length, 0);
  const { modified } = guideDates(guides);
  const related = relatedGuides(await indexOrEmpty(), marca, modelo);

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="flex-1 pt-3 pb-16 md:pt-8">
        {[faq, article, breadcrumb].map((ld, n) => ld ? <script key={n} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(ld) }} /> : null)}
        <GuideTracker slugMake={marca} slugModel={modelo} name={name} />
        <div className={`${WRAP} space-y-5`}>
          <nav aria-label="Ruta" className="flex flex-wrap gap-x-2 text-sm text-muted-foreground">
            <Link href="/guias" className="inline-flex min-h-8 items-center underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
            <span aria-hidden="true" className="self-center">›</span>
            <Link href={makePath(marca)} className="inline-flex min-h-8 items-center underline underline-offset-4">{make}</Link>
          </nav>
          <header className="border-b-2 border-foreground pb-4">
            <p className="text-[12.5px] font-bold tracking-[0.1em] text-muted-foreground uppercase">
              {[GUIDE_COPY.badge, yearsText(years.from, years.to)].filter(Boolean).join(" · ")}
            </p>
            <h1 className="type-display mt-1.5 text-[2.1rem] leading-[1.02] text-balance md:text-5xl">{guideTitle(make, model)}</h1>
            {/* GEO: the date up top, where a reader and an engine see how current the page is. */}
            <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
              {modified ? (
                <span data-testid="guide-updated">
                  {GUIDE_COPY.updatedTop.split("{date}")[0]}
                  <time dateTime={modified}>{guideDate(modified)}</time>
                </span>
              ) : null}
              {sources ? <span>{sources === 1 ? GUIDE_COPY.source : GUIDE_COPY.sources.replace("{n}", String(sources))}</span> : null}
            </p>
          </header>
          {summary ? (
            <section aria-labelledby="guide-summary" data-testid="guide-summary" className="space-y-1.5">
              <h2 id="guide-summary" className="text-[12.5px] font-bold tracking-[0.1em] text-muted-foreground uppercase">{GUIDE_COPY.summaryTitle}</h2>
              {/* The one yellow on the page: what to check first. */}
              <p className="text-[18px] leading-relaxed">
                {summary.map((part, n) => part.mark ? <mark key={n} className="mark mx-[-0.3em] bg-transparent">{part.text}</mark> : part.text)}
              </p>
            </section>
          ) : null}
          <GuideNotice />
          <p className="flex items-center justify-between gap-3 rounded-md bg-muted p-3.5 text-[15px] leading-snug">
            <span>{GUIDE_COPY.ctaTopText.replace("{name}", name)}</span>
            {/* The form is the one at the bottom (a single signup form per page). */}
            <a href="#crear-busqueda" data-testid="guide-cta-top" className="inline-flex min-h-11 shrink-0 items-center rounded-md bg-primary px-3.5 font-semibold text-primary-foreground">
              {GUIDE_COPY.ctaTopShort}
            </a>
          </p>
          <GuideContent guides={guides} slugMake={marca} slugModel={modelo} />
          <section id="crear-busqueda" aria-labelledby="guide-cta" className="scroll-mt-6 rounded-md border-2 border-foreground p-4 sm:p-6">
            <h2 id="guide-cta" className="type-display text-[1.6rem] leading-tight text-balance">{GUIDE_COPY.ctaTitle.replace("{name}", name)}</h2>
            <p className="mt-2 text-[15px] text-muted-foreground">{GUIDE_COPY.ctaText}</p>
            <GuideCta prompt={ctaPrompt(make, model, years.from, years.to)} slugMake={marca} slugModel={modelo} />
          </section>
          {related.length ? (
            <nav aria-labelledby="guide-related" data-testid="guide-related" className="pt-2">
              <h2 id="guide-related" className="type-heading text-lg">{GUIDE_COPY.related}</h2>
              <GuideLeaders items={related.map((g) => ({ href: guidePath(g.slugMake, g.slugModel), label: guideName(g.make, g.model), years: yearsText(g.yearFrom, g.yearTo) }))} />
              <Link href={makePath(marca)} className="inline-flex min-h-11 items-center text-sm text-muted-foreground underline underline-offset-4">
                {GUIDE_COPY.allFromMake.replace("{make}", make)}
              </Link>
            </nav>
          ) : null}
          <p className="text-sm">
            <Link href={METHOD_PATH} className="inline-flex min-h-11 items-center underline underline-offset-4">{GUIDE_COPY.method}</Link>
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
