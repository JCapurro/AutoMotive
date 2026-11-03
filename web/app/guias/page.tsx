import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { siteUrl } from "@/lib/env";
import { GUIDE_COPY, guideIndexJsonLd, guideName, guidePath, jsonLdScript } from "@/lib/guides";
import { type GuideIndexEntry, publishedGuideIndex } from "@/lib/guides-data";

// PAR-04: static, regenerated at most once an hour and at once on publishing.
export const revalidate = 3600;

export const metadata: Metadata = {
  title: GUIDE_COPY.indexTitle,
  description: GUIDE_COPY.indexIntro,
  alternates: { canonical: "/guias" },
  // Its own: without it the layout's (the landing's) title and description are shared.
  openGraph: { type: "website", locale: "es_AR", siteName: "eseauto.com.ar", title: GUIDE_COPY.indexTitle, description: GUIDE_COPY.indexIntro, url: "/guias" },
};

/** /guias: the published guides by make. Without any it is still a page (the sitemap links it). */
/**
 * The published entries. At build time a database problem renders the empty
 * index (regenerated within the hour) instead of failing the deploy; at
 * runtime it throws, and ISR keeps serving the page it had.
 */
async function entriesOrEmptyAtBuild(): Promise<GuideIndexEntry[]> {
  try {
    return await publishedGuideIndex();
  } catch (error) {
    if (process.env.NEXT_PHASE === "phase-production-build") return [];
    throw error;
  }
}

export default async function GuidesIndex() {
  const entries = await entriesOrEmptyAtBuild();
  const byMake = new Map<string, GuideIndexEntry[]>();
  for (const e of entries) byMake.set(e.make, [...(byMake.get(e.make) ?? []), e]);

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-4 pt-8 pb-16 sm:px-6 md:pt-12">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(guideIndexJsonLd(entries, siteUrl)) }} />
        <header className="space-y-4">
          <h1 className="type-display text-[2.1rem] leading-[1.05] text-balance md:text-5xl">{GUIDE_COPY.indexTitle}</h1>
          <p className="text-[17px] leading-snug text-muted-foreground">{GUIDE_COPY.indexIntro}</p>
        </header>
        {byMake.size ? (
          <div className="space-y-6">
            {[...byMake.entries()].map(([make, models]) => (
              <section key={make} aria-labelledby={`marca-${models[0].slugMake}`} className="space-y-2">
                <h2 id={`marca-${models[0].slugMake}`} className="text-lg font-semibold">{make}</h2>
                <ul className="space-y-1.5">
                  {models.map((m) => (
                    <li key={m.slugModel}>
                      <Link href={guidePath(m.slugMake, m.slugModel)} className="inline-flex min-h-11 items-center text-[16px] underline underline-offset-4">
                        {guideName(m.make, m.model)}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <p>{GUIDE_COPY.indexEmpty}</p>
            <Link href="/" className="text-sm underline underline-offset-4">{GUIDE_COPY.indexBack}</Link>
          </div>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
