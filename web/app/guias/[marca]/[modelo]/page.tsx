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
  ctaPrompt,
  faqJsonLd,
  GUIDE_COPY,
  guideDescription,
  guideName,
  guidePath,
  guideTitle,
  jsonLdScript,
  modelYears,
  yearsText,
} from "@/lib/guides";
import { publishedModelGuides } from "@/lib/guides-data";

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
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "article", locale: "es_AR", siteName: "eseauto.com.ar", title, description, url: path },
  };
}

const WRAP = "mx-auto w-full max-w-3xl px-4 sm:px-6";

/** /guias/<marca>/<modelo>: the published guides of one model. 404 for anything else. */
export default async function GuidePage({ params }: PageProps<"/guias/[marca]/[modelo]">) {
  const { marca, modelo } = await params;
  const guides = await publishedModelGuides(marca, modelo);
  if (!guides) notFound();
  const { make, model } = guides[0];
  const name = guideName(make, model);
  const years = modelYears(guides);
  const faq = faqJsonLd(guides, `${siteUrl}${guidePath(marca, modelo)}`);

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="flex-1 pt-8 pb-16 md:pt-12">
        {faq ? <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(faq) }} /> : null}
        <GuideTracker slugMake={marca} slugModel={modelo} name={name} />
        <div className={`${WRAP} space-y-8`}>
          <nav aria-label="Ruta" className="text-sm text-muted-foreground">
            <Link href="/guias" className="underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
          </nav>
          <header className="space-y-4">
            <p className="text-sm font-semibold text-muted-foreground">{GUIDE_COPY.badge}</p>
            <h1 className="type-display text-[2.1rem] leading-[1.05] text-balance md:text-5xl">{guideTitle(make, model)}</h1>
            <GuideNotice />
          </header>
          <GuideContent guides={guides} slugMake={marca} slugModel={modelo} />
          <section id="crear-busqueda" aria-labelledby="guide-cta" className="scroll-mt-24 rounded-xl border p-4 sm:p-6">
            <h2 id="guide-cta" className="text-xl font-semibold tracking-tight">{GUIDE_COPY.ctaTitle.replace("{name}", name)}</h2>
            <p className="mt-2 text-[15px] text-muted-foreground">{GUIDE_COPY.ctaText}</p>
            <GuideCta prompt={ctaPrompt(make, model, years.from, years.to)} slugMake={marca} slugModel={modelo} />
          </section>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
