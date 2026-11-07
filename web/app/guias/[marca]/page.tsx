import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { GuideLeaders } from "@/components/guides/guide-leaders";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { siteUrl } from "@/lib/env";
import {
  GUIDE_COPY,
  guideDate,
  guidePath,
  jsonLdScript,
  makeBreadcrumb,
  makeIndexJsonLd,
  makePath,
  METHOD_PATH,
  modelYears,
  yearsText,
} from "@/lib/guides";
import { publishedMakeGuides } from "@/lib/guides-data";

// Like the model's page: ISR, nothing built at deploy time, invalidated at once on publishing.
export const revalidate = 3600;
export const dynamicParams = true;

export async function generateStaticParams(): Promise<{ marca: string }[]> {
  return [];
}

export async function generateMetadata({ params }: PageProps<"/guias/[marca]">): Promise<Metadata> {
  const { marca } = await params;
  const models = await publishedMakeGuides(marca);
  if (!models) return { title: "No encontramos estas guías", robots: { index: false } };
  const make = models[0][0].make;
  const title = GUIDE_COPY.makeTitle.replace("{make}", make);
  const description = GUIDE_COPY.makeIntro.replace("{make}", make);
  const path = makePath(marca);
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "website", locale: "es_AR", siteName: "eseauto.com.ar", title, description, url: path },
  };
}

/** /guias/<marca>: the make's published models, each with its years and its first known issue. 404 without any. */
export default async function MakeGuides({ params }: PageProps<"/guias/[marca]">) {
  const { marca } = await params;
  const models = await publishedMakeGuides(marca);
  if (!models) notFound();
  const make = models[0][0].make;
  const entries = models.map((guides) => ({ make: guides[0].make, model: guides[0].model, slugMake: guides[0].slugMake, slugModel: guides[0].slugModel }));
  const updated = models.flat().map((g) => g.updatedAt).sort().at(-1);

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-5 px-4 pt-3 pb-16 sm:px-6 md:pt-8">
        {[makeIndexJsonLd(make, marca, entries, siteUrl), makeBreadcrumb(make, marca, siteUrl)].map((ld, n) => (
          <script key={n} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(ld) }} />
        ))}
        <nav aria-label="Ruta" className="text-sm text-muted-foreground">
          <Link href="/guias" className="inline-flex min-h-8 items-center underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
        </nav>
        <header className="border-b-2 border-foreground pb-4">
          <p className="text-[12.5px] font-bold tracking-[0.1em] text-muted-foreground uppercase">
            {GUIDE_COPY.indexEyebrow} · {models.length === 1 ? GUIDE_COPY.model : GUIDE_COPY.models.replace("{n}", String(models.length))}
          </p>
          <h1 className="type-display mt-1.5 text-[2.3rem] leading-[1] text-balance md:text-5xl">{GUIDE_COPY.makeTitle.replace("{make}", make)}</h1>
          <p className="mt-3 text-[16px] leading-snug text-muted-foreground">{GUIDE_COPY.makeIntro.replace("{make}", make)}</p>
          {updated ? (
            <p className="mt-3 text-sm text-muted-foreground">
              {GUIDE_COPY.updatedTop.split("{date}")[0]}
              <time dateTime={updated}>{guideDate(updated)}</time>
            </p>
          ) : null}
        </header>
        <GuideLeaders
          items={models.map((guides) => {
            const { make: m, model, slugMake, slugModel } = guides[0];
            const years = modelYears(guides);
            const issue = guides.flatMap((g) => g.body.known_issues)[0];
            return {
              href: guidePath(slugMake, slugModel),
              hidden: m,
              label: model,
              years: yearsText(years.from, years.to),
              note: issue ? GUIDE_COPY.makeIssue.replace("{text}", issue.text) : undefined,
            };
          })}
        />
        <p className="text-sm">
          <Link href={METHOD_PATH} className="inline-flex min-h-11 items-center underline underline-offset-4">{GUIDE_COPY.method}</Link>
        </p>
      </main>
      <SiteFooter />
    </div>
  );
}
