import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { siteUrl } from "@/lib/env";
import { GuideLeaders } from "@/components/guides/guide-leaders";
import { GUIDE_COPY, guideIndexJsonLd, guidePath, jsonLdScript, makePath, METHOD_PATH, yearsText } from "@/lib/guides";
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

/** The anchor of a letter in the index (#letra-c). */
function letterId(make: string): string {
  return `letra-${make.normalize("NFD").replace(/[̀-ͯ]/g, "").charAt(0).toLowerCase()}`;
}

export default async function GuidesIndex() {
  const entries = await entriesOrEmptyAtBuild();
  const byMake = new Map<string, GuideIndexEntry[]>();
  for (const e of entries) byMake.set(e.make, [...(byMake.get(e.make) ?? []), e]);
  const letters = [...new Set([...byMake.keys()].map(letterId))];
  const seen = new Set<string>();

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pt-5 pb-16 sm:px-6 md:pt-10">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(guideIndexJsonLd(entries, siteUrl)) }} />
        {/* A printed guide's index: the masthead, letters to jump, makes with their models and years. */}
        <header className="border-b-2 border-foreground pb-4">
          <p className="text-[12.5px] font-bold tracking-[0.1em] text-muted-foreground uppercase">{GUIDE_COPY.indexEyebrow}</p>
          <h1 className="type-display mt-1.5 text-[2.5rem] leading-[0.98] text-balance md:text-6xl">{GUIDE_COPY.indexHeading}</h1>
          <p className="mt-3 text-[16px] leading-snug text-muted-foreground">{GUIDE_COPY.indexIntro}</p>
        </header>
        {byMake.size ? (
          <>
            {letters.length > 1 ? (
              <nav aria-label={GUIDE_COPY.letters} className="sticky top-0 z-10 -mx-4 flex overflow-x-auto border-b bg-background px-3 py-1.5 [scrollbar-width:none] sm:-mx-6 sm:px-5">
                {letters.map((l) => (
                  <a key={l} href={`#${l}`} className="grid h-11 min-w-8 flex-[1_0_32px] place-items-center rounded-md text-[15px] font-extrabold uppercase active:bg-muted">
                    {l.slice(-1)}
                  </a>
                ))}
              </nav>
            ) : null}
            <div className="space-y-2">
              {[...byMake.entries()].map(([make, models]) => {
                const letter = letterId(make);
                const first = !seen.has(letter);
                seen.add(letter);
                return (
                  <section key={make} id={first ? letter : undefined} aria-labelledby={`marca-${models[0].slugMake}`} className="scroll-mt-16 pt-6">
                    <h2 id={`marca-${models[0].slugMake}`} className="type-heading flex items-baseline gap-2.5 text-[22px]">
                      <Link href={makePath(models[0].slugMake)} className="hover:underline underline-offset-4">{make}</Link>
                      <small className="text-[13px] font-semibold tracking-normal text-muted-foreground">
                        {models.length === 1 ? GUIDE_COPY.model : GUIDE_COPY.models.replace("{n}", String(models.length))}
                      </small>
                    </h2>
                    <GuideLeaders items={models.map((m) => ({ href: guidePath(m.slugMake, m.slugModel), hidden: m.make, label: m.model, years: yearsText(m.yearFrom, m.yearTo) }))} />
                  </section>
                );
              })}
            </div>
            <p className="mt-6 text-sm">
              <Link href={METHOD_PATH} className="inline-flex min-h-11 items-center underline underline-offset-4">{GUIDE_COPY.method}</Link>
            </p>
          </>
        ) : (
          <div className="mt-6 space-y-3">
            <p>{GUIDE_COPY.indexEmpty}</p>
            <Link href="/" className="text-sm underline underline-offset-4">{GUIDE_COPY.indexBack}</Link>
          </div>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
