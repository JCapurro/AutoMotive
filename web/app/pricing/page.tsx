import type { Metadata } from "next";

import { PublicPlans } from "@/components/public-plans";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { currentUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";

export const metadata: Metadata = {
  title: "Pricing · Planes",
  description: "Compará la prueba gratis, Particular, Agencia y Custom con precio a convenir. Elegí cómo buscar con Ese Auto.",
};

export default async function PricingPage() {
  const [user, cfg] = await Promise.all([currentUser(), webConfig()]);

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={Boolean(user)} page="pricing" />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-10 pb-16 sm:px-6 md:pt-16 lg:px-10">
        <p className="text-sm font-semibold text-muted-foreground">Pricing</p>
        <h1 className="type-display mt-3 max-w-[23ch] text-[2.4rem] leading-[1.05] text-balance md:text-5xl">Un plan para tu forma de buscar.</h1>
        <p className="mt-5 mb-10 max-w-2xl text-lg text-muted-foreground">Empezá con una prueba gratis. Después, elegí un plan para tu próximo auto, para buscar habitualmente o una propuesta Custom a convenir.</p>
        <section aria-labelledby="pricing-plans">
          <h2 id="pricing-plans" className="sr-only">Compará los planes</h2>
          <PublicPlans cfg={cfg} signedIn={Boolean(user)} />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
