import type { Metadata } from "next";
import Link from "next/link";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { unsubscribeToken } from "@/lib/unsubscribe";

import { unsubscribe } from "./actions";

export const metadata: Metadata = { title: "Dejar de recibir emails", robots: { index: false } };

/**
 * The link at the foot of every alert email (F7, punto 7). Opening it changes
 * nothing — mail scanners open links too —; the button does.
 */
export default async function UnsubscribePage({ searchParams }: PageProps<"/baja">) {
  const params = await searchParams;
  const token = unsubscribeToken(params.t);
  const done = params.listo === "1";

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Logo />
      <Card className="w-full max-w-sm">
        {done ? (
          <CardHeader>
            <CardTitle className="text-lg">Listo, no te mandamos más emails</CardTitle>
            <CardDescription>
              Tus búsquedas siguen activas y las alertas te llegan por los otros canales. Podés volver a activar el
              email desde <Link href="/app/settings" className="underline">Ajustes</Link>.
            </CardDescription>
          </CardHeader>
        ) : token ? (
          <>
            <CardHeader>
              <CardTitle className="text-lg">¿Dejar de recibir emails?</CardTitle>
              <CardDescription>
                Dejamos de mandarte alertas por email. Tus búsquedas siguen activas en la web y en Telegram.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form action={unsubscribe}>
                <input type="hidden" name="t" value={token} />
                <Button type="submit" className="h-10 w-full">
                  Dejar de recibir emails
                </Button>
              </form>
            </CardContent>
          </>
        ) : (
          <CardHeader>
            <CardTitle className="text-lg">Este link no es válido</CardTitle>
            <CardDescription>
              Podés elegir por dónde te avisamos desde <Link href="/app/settings" className="underline">Ajustes</Link>.
            </CardDescription>
          </CardHeader>
        )}
      </Card>
    </main>
  );
}
