import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { GuideContent, GuideNotice } from "@/components/guides/guide-content";
import { GuideCta } from "@/components/guides/guide-cta";
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
  guideSummary,
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
  const summary = guideSummary(guides);
  const { modified } = guideDates(guides);
  const related = relatedGuides(await indexOrEmpty(), marca, modelo);

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="flex-1 pt-8 pb-16 md:pt-12">
        {[faq, article, breadcrumb].map((ld, n) => ld ? <script key={n} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(ld) }} /> : null)}
        <GuideTracker slugMake={marca} slugModel={modelo} name={name} />
        <div className={`${WRAP} space-y-8`}>
          <nav aria-label="Ruta" className="flex flex-wrap gap-x-2 text-sm text-muted-foreground">
            <Link href="/guias" className="underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
            <span aria-hidden="true">›</span>
            <Link href={makePath(marca)} className="underline underline-offset-4">{make}</Link>
          </nav>
          <header className="space-y-4">
            <p className="text-sm font-semibold text-muted-foreground">{GUIDE_COPY.badge}</p>
            <h1 className="type-display text-[2.1rem] leading-[1.05] text-balance md:text-5xl">{guideTitle(make, model)}</h1>
            {/* GEO: the date up top, where a reader and an engine see how current the page is. */}
            {modified ? (
              <p data-testid="guide-updated" className="text-sm text-muted-foreground">
                {GUIDE_COPY.updatedTop.split("{date}")[0]}
                <time dateTime={modified}>{guideDate(modified)}</time>
              </p>
            ) : null}
            <GuideNotice />
          </header>
          {summary ? (
            <section aria-labelledby="guide-summary" data-testid="guide-summary" className="space-y-2">
              <h2 id="guide-summary" className="text-xl font-semibold tracking-tight">{GUIDE_COPY.summaryTitle}</h2>
              <p className="text-[17px] leading-relaxed">{summary}</p>
            </section>
          ) : null}
          <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[15px] text-muted-foreground">
            <span>{GUIDE_COPY.ctaTopText.replace("{name}", name)}</span>
            {/* The form is the one at the bottom (a single signup form per page). */}
            <a href="#crear-busqueda" data-testid="guide-cta-top" className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 font-medium text-primary-foreground">
              {GUIDE_COPY.ctaTop}
            </a>
          </p>
          <GuideContent guides={guides} slugMake={marca} slugModel={modelo} />
          <p className="text-sm">
            <Link href={METHOD_PATH} className="underline underline-offset-4">{GUIDE_COPY.method}</Link>
          </p>
          <section id="crear-busqueda" aria-labelledby="guide-cta" className="scroll-mt-24 rounded-xl border p-4 sm:p-6">
            <h2 id="guide-cta" className="text-xl font-semibold tracking-tight">{GUIDE_COPY.ctaTitle.replace("{name}", name)}</h2>
            <p className="mt-2 text-[15px] text-muted-foreground">{GUIDE_COPY.ctaText}</p>
            <GuideCta prompt={ctaPrompt(make, model, years.from, years.to)} slugMake={marca} slugModel={modelo} />
          </section>
          {related.length ? (
            <nav aria-labelledby="guide-related" data-testid="guide-related" className="space-y-3">
              <h2 id="guide-related" className="text-xl font-semibold tracking-tight">{GUIDE_COPY.related}</h2>
              <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                {related.map((g) => (
                  <li key={`${g.slugMake}/${g.slugModel}`}>
                    <Link href={guidePath(g.slugMake, g.slugModel)} className="inline-flex min-h-11 items-center text-[16px] underline underline-offset-4">
                      {guideName(g.make, g.model)}
                    </Link>
                  </li>
                ))}
              </ul>
              <Link href={makePath(marca)} className="inline-flex min-h-11 items-center text-sm text-muted-foreground underline underline-offset-4">
                {GUIDE_COPY.allFromMake.replace("{make}", make)}
              </Link>
            </nav>
          ) : null}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
