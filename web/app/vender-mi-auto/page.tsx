import type { Metadata } from "next";
import Link from "next/link";

import { Logo } from "@/components/logo";
import { SellIntentConfirm, SellIntentNotice } from "@/components/sell-intent";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { webConfig } from "@/lib/config";
import { SELL_INTENT, type SellIntentAnswer, sellIntentAnswer, sellIntentEmailId } from "@/lib/sell-intent";
import { currentAnswer, resolveViewer } from "@/lib/sell-intent-server";

export const metadata: Metadata = { title: "Tu auto actual", robots: { index: false } };
export const dynamic = "force-dynamic";

/**
 * PAR-05, Prueba B: «¿Tenés que vender tu auto actual para comprar?». From the
 * welcome email (?e=<id>&r=si|no&s=<signature>) or from the listing page's
 * line (a session). Nothing is shared with anyone.
 */
export default async function SellIntentPage({ searchParams }: PageProps<"/vender-mi-auto">) {
  const query = await searchParams;
  const id = sellIntentEmailId(query.e);
  const signature = typeof query.s === "string" ? query.s : null;
  const chosen = sellIntentAnswer(query.r);
  const [viewer, config] = await Promise.all([resolveViewer(id, signature), webConfig()]);
  const row = viewer ? await currentAnswer(viewer) : null;
  const confirm = viewer && (row == null || (chosen != null && chosen !== row.answer));

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Logo />
      <Card className="w-full max-w-sm">
        {!viewer ? (
          <CardHeader>
            <CardTitle className="text-lg">{SELL_INTENT.invalid}</CardTitle>
            <CardDescription>
              {SELL_INTENT.invalidDetail}{" "}
              <Link href="/login?next=/vender-mi-auto" className="underline">
                Entrar
              </Link>
            </CardDescription>
          </CardHeader>
        ) : confirm || !row ? (
          <SellIntentConfirm viewer={viewer} chosen={chosen ?? (row?.answer as SellIntentAnswer | undefined) ?? null} />
        ) : row.answer === "yes" ? (
          <SellIntentNotice viewer={viewer} row={row} agenciesContact={config.sellIntent.agenciesContact} />
        ) : (
          <CardHeader>
            <CardTitle className="text-lg">{SELL_INTENT.noThanks}</CardTitle>
            <CardDescription>
              {SELL_INTENT.noThanksDetail}{" "}
              <Link href="/app" className="underline">
                Ver mis búsquedas
              </Link>
            </CardDescription>
          </CardHeader>
        )}
      </Card>
    </main>
  );
}
