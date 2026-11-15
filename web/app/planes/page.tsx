import type { Metadata } from "next";

import { PublicPlans } from "@/components/public-plans";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { currentUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { isPassOffer } from "@/lib/pro";

export const metadata: Metadata = {
  title: "Planes",
  description: "Compará la prueba gratis, Particular, Pro y Custom con precio a convenir. Elegí cómo buscar con Ese Auto.",
};

export default async function PlanesPage({ searchParams }: PageProps<"/planes">) {
  const [user, cfg, params] = await Promise.all([currentUser(), webConfig(), searchParams]);
  // /planes?plan=pass_7 opens Particular on the 7-day pass; anything else keeps 30 days.
  const plan = Array.isArray(params.plan) ? params.plan[0] : params.plan;
  const pass = isPassOffer(plan) ? plan : undefined;

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={Boolean(user)} page="planes" />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-10 pb-16 sm:px-6 md:pt-16 lg:px-10">
        <p className="text-sm font-semibold text-muted-foreground">Planes</p>
        <h1 className="type-display mt-3 max-w-[23ch] text-[2.4rem] leading-[1.05] text-balance md:text-5xl">Un plan para tu forma de buscar.</h1>
        <p className="mt-5 mb-10 max-w-2xl text-lg text-muted-foreground">Empezá con una prueba gratis. Después, elegí un plan para tu próximo auto, para buscar habitualmente o una propuesta Custom a convenir.</p>
        <section aria-labelledby="plans-list">
          <h2 id="plans-list" className="sr-only">Compará los planes</h2>
          <PublicPlans cfg={cfg} signedIn={Boolean(user)} pass={pass} />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
