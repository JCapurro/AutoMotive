import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AccountSteps } from "@/components/app/account-steps";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { liveAccount } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { hasFreshProof } from "@/lib/email-only";
import { safeNext } from "@/lib/navigation";
import { isWaitlistPlan, PLAN_COPY, planPrice } from "@/lib/pro";

export const metadata: Metadata = { title: "Tu cuenta" };

/**
 * An email-only account (the free search) becomes a full one: inbox proven
 * through a link, then a password. Paying a plan requires it.
 */
export default async function AccountPage({ searchParams }: PageProps<"/app/cuenta">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  const account = await liveAccount();
  // A session closed elsewhere still passes the proxy until its token expires, and /login would bounce it.
  if (!account) return <RevokedSession />;
  if (!account.emailOnly || !account.email) redirect(next);
  const proven = account.sessionId ? await hasFreshProof(account.id, account.sessionId) : false;
  const paying = next.startsWith("/app/pro");
  const plan = paying ? new URL(next, "https://x.invalid").searchParams.get("plan") : null;
  const offer = isWaitlistPlan(plan) ? { copy: PLAN_COPY[plan], amount: (await webConfig()).proOffer[plan].amount } : null;

  return (
    <div className="mx-auto max-w-md space-y-5">
      {offer ? <p className="text-sm text-muted-foreground">{offer.copy.name} · {planPrice(offer.amount)} · {offer.copy.period}</p> : null}
      <Card>
        <CardHeader>
          <CardTitle>{proven ? "Elegí una contraseña" : paying ? "Confirmá tu email para contratar" : "Confirmá tu email"}</CardTitle>
          <CardDescription>
            {proven
              ? paying ? "Para contratar, elegí una contraseña. Así entrás desde cualquier dispositivo y ves tus pagos."
                : "Así entrás más rápido la próxima vez. La vas a necesitar para contratar un plan."
              : <>Para {paying ? "pagar" : "elegir una contraseña"} necesitamos confirmar que <b className="text-foreground [overflow-wrap:anywhere]">{account.email}</b> es tuyo.
                Te vamos a mandar un link: lo abrís y elegís tu contraseña.</>}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AccountSteps email={account.email} next={next} proven={proven} paying={paying} />
        </CardContent>
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
