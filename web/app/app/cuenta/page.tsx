import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AccountSteps } from "@/components/app/account-steps";
import { ContinueToPayment } from "@/components/app/continue-to-payment";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { liveAccount } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { hasFreshProof } from "@/lib/email-only";
import { safeNext } from "@/lib/navigation";
import { payPlan, PLAN_COPY, planPrice } from "@/lib/pro";

export const metadata: Metadata = { title: "Tu cuenta" };

/**
 * An email-only account (the free search) becomes a full one: inbox proven
 * through a code or a link, then a password. Paying a plan requires the proof;
 * on the way to Mercado Pago the code alone is enough (docs/PAGO_CON_CODIGO.md).
 */
export default async function AccountPage({ searchParams }: PageProps<"/app/cuenta">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  const account = await liveAccount();
  // A session closed elsewhere still passes the proxy until its token expires, and /login would bounce it.
  if (!account) return <RevokedSession />;
  const paying = next.startsWith("/app/pro");
  const cfg = await webConfig();
  // «Camino al pago»: the code takes it to Mercado Pago, no password (payments on, and /app/pro as the destination).
  const checkout = paying && cfg.automaticPayments;
  const plan = payPlan(next);
  const offer = plan ? { plan, copy: PLAN_COPY[plan], version: cfg.proOffer.version, ...cfg.proOffer[plan] } : null;
  // Next renders this page again in the action's response once the code completed the account: a plan still goes on.
  if (!account.emailOnly || !account.email) {
    if (!(checkout && offer && account.email)) redirect(next);
  }
  // This session proved the inbox in the last hour: the code was just typed (or the link opened) here.
  const fresh = account.sessionId ? await hasFreshProof(account.id, account.sessionId) : false;
  const proven = !account.emailOnly || fresh;
  const email = account.email ?? "";

  return (
    <div className="mx-auto max-w-md space-y-5">
      {offer ? <p className="text-sm text-muted-foreground">{offer.copy.name} · {planPrice(offer.amount)} · {offer.copy.period}</p> : null}
      <Card>
        {checkout && proven ? <>
          <CardHeader>
            <CardTitle>Seguí en Mercado Pago</CardTitle>
            <CardDescription>
              Tu email está confirmado. {offer ? <>Pagás {offer.copy.name} en Mercado Pago y activamos tu acceso al confirmar el pago.</> : "Seguí para elegir cómo pagar."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ContinueToPayment next={next} autostart={params.pagar === "1" && fresh}
              offer={offer ? { plan: offer.plan, version: offer.version, amount: offer.amount, currency: offer.currency } : null} />
          </CardContent>
        </> : <>
          <CardHeader>
            <CardTitle>{proven ? "Elegí una contraseña" : checkout ? "Escribí el código que te mandamos" : paying ? "Confirmá tu email para contratar" : "Confirmá tu email"}</CardTitle>
            <CardDescription>
              {proven
                ? paying ? "Para contratar, elegí una contraseña. Así entrás desde cualquier dispositivo y ves tus pagos."
                  : "Así entrás más rápido la próxima vez. La vas a necesitar para contratar un plan."
                : checkout
                  ? <>Te lo mandamos a <b className="text-foreground [overflow-wrap:anywhere]">{email}</b> para confirmar que el email es tuyo. Lo escribís acá y {offer ? "seguís a Mercado Pago" : "seguís"}.</>
                  : <>Para {paying ? "pagar" : "elegir una contraseña"} necesitamos confirmar que <b className="text-foreground [overflow-wrap:anywhere]">{email}</b> es tuyo.
                    Te vamos a mandar un código: lo escribís acá y elegís tu contraseña.</>}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {params.error === "security" ? (
              <p role="alert" className="mb-4 text-sm text-destructive">
                No pudimos terminar de proteger tu cuenta. Pedí un código nuevo para volver a intentarlo.
              </p>
            ) : null}
            <AccountSteps email={email} next={next} proven={proven} paying={paying}
              checkout={checkout ? { amount: offer?.amount ?? null } : undefined} />
          </CardContent>
        </>}
      </Card>
    </div>
  );
}

function RevokedSession() {
  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>Tu sesión se cerró</CardTitle>
          <CardDescription>Se cerró desde otro dispositivo, por ejemplo al entrar con un link. Cerrá sesión acá y volvé a entrar.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action="/auth/signout" method="post">
            <Button type="submit" className="h-10 w-full">Cerrar sesión</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
