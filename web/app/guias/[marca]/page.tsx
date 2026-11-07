import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { siteUrl } from "@/lib/env";
import {
  GUIDE_COPY,
  guideDate,
  guideName,
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
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-4 pt-8 pb-16 sm:px-6 md:pt-12">
        {[makeIndexJsonLd(make, marca, entries, siteUrl), makeBreadcrumb(make, marca, siteUrl)].map((ld, n) => (
          <script key={n} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(ld) }} />
        ))}
        <nav aria-label="Ruta" className="text-sm text-muted-foreground">
          <Link href="/guias" className="underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
        </nav>
        <header className="space-y-4">
          <h1 className="type-display text-[2.1rem] leading-[1.05] text-balance md:text-5xl">{GUIDE_COPY.makeTitle.replace("{make}", make)}</h1>
          <p className="text-[17px] leading-snug text-muted-foreground">{GUIDE_COPY.makeIntro.replace("{make}", make)}</p>
          {updated ? (
            <p className="text-sm text-muted-foreground">
              {GUIDE_COPY.updatedTop.split("{date}")[0]}
              <time dateTime={updated}>{guideDate(updated)}</time>
            </p>
          ) : null}
        </header>
        <ul className="space-y-6">
          {models.map((guides) => {
            const { make: m, model, slugMake, slugModel } = guides[0];
            const years = modelYears(guides);
            const issue = guides.flatMap((g) => g.body.known_issues)[0];
            return (
              <li key={slugModel} className="space-y-1.5">
                <h2 className="text-lg font-semibold">
                  <Link href={guidePath(slugMake, slugModel)} className="underline underline-offset-4">{guideName(m, model)}</Link>
                  {yearsText(years.from, years.to) ? <span className="font-normal text-muted-foreground"> · {yearsText(years.from, years.to)}</span> : null}
                </h2>
                {issue ? <p className="text-[15px] leading-relaxed text-muted-foreground">{GUIDE_COPY.makeIssue.replace("{text}", issue.text)}</p> : null}
              </li>
            );
          })}
        </ul>
        <p className="text-sm">
          <Link href={METHOD_PATH} className="underline underline-offset-4">{GUIDE_COPY.method}</Link>
        </p>
      </main>
      <SiteFooter />
    </div>
  );
}
