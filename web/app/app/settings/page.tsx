import type { Metadata } from "next";
import Link from "next/link";

import { DeleteAccount } from "@/components/app/delete-account";
import { BillingStatus } from "@/components/app/billing-status";
import { RenewalButton } from "@/components/app/renewal-button";
import { ProCtaButton } from "@/components/app/pro-cta";
import { ChannelsForm, FrequencyForm } from "@/components/app/settings-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { isWaitlistPlan, PLAN_COPY, PLAN_NAMES, accessDescription, accessDate, planPrice, type PlanLimits } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Ajustes" };

export default async function SettingsPage() {
  const user = await requireUser();
  const cfg = await webConfig();
  const supabase = await createClient();
  const [{ data: profile }, { data: waitlist }, { data: rawAccess }, { data: payments }, { data: declines }, { data: subscriptions }] = await Promise.all([
    supabase
      .from("profiles")
      .select("email, plan, default_channels, default_notification_frequency")
      .single(),
    supabase.from("pro_waitlist").select("plan").maybeSingle(),
    supabase.rpc("my_plan_limits"),
    supabase.from("commercial_payments").select("id,offer,amount,currency,period_start,period_end,refunded_at").order("verified_at", { ascending: false }).limit(10),
    supabase.from("events").select("props").eq("name", "renewal_declined").order("created_at", { ascending: false }).limit(10),
    supabase.from("billing_checkouts").select("id,offer,amount,status,init_point,next_payment_at,sync_error,created_at").eq("offer", "pro_monthly").order("created_at", { ascending: false }).limit(3),
  ]);
  const access = rawAccess as PlanLimits | null;
  const declined = (declines ?? []).some((d) => (d.props as { period_end?: string })?.period_end === access?.expires_at);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Ajustes</h1>

      <Card>
        <CardHeader>
          <CardTitle>Canales</CardTitle>
          <CardDescription>Por dónde te avisamos. Aplica a todas tus búsquedas.</CardDescription>
        </CardHeader>
        <CardContent>
          <ChannelsForm
            channels={profile?.default_channels ?? ["email", "web"]}
            email={profile?.email ?? user.email}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preferencias</CardTitle>
          {access?.enforced && access.plan === "free" ? <CardDescription>Durante la prueba, las nuevas coincidencias llegan en el resumen diario. Tu preferencia se aplica al activar un plan pago.</CardDescription> : null}
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <FrequencyForm value={profile?.default_notification_frequency ?? "immediate"} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Plan</CardTitle>
          <CardDescription>
            {access ? accessDescription(access) : "Consultá los planes disponibles."}
          </CardDescription>
        </CardHeader>
          <CardContent className="space-y-3">
            {access ? <p className="text-sm">{PLAN_NAMES[access.plan]} · {access.active_searches ?? 0} búsquedas activas
              {access.enforced ? ` de ${access.limits.max_profiles ?? "sin límite"}` : ""}.</p> : null}
            {(subscriptions ?? []).map((checkout) => <BillingStatus key={checkout.id} checkout={checkout} />)}
            {access?.plan === "pro" && access.active && !subscriptions?.length ? <>
              <p className="text-sm text-muted-foreground">Tu acceso en S Auto se registró manualmente por 30 días.
                Podés avisar que no vas a renovar; el período pagado sigue vigente.</p>
              <p className="text-sm text-muted-foreground">Si contrataste con un enlace de suscripción de Mercado Pago, cancelalo también desde tu cuenta de Mercado Pago. Este aviso por sí solo no detiene sus cobros.</p>
              <RenewalButton declined={declined} />
            </> : null}
            {access?.state === "expired" ? <p className="text-sm text-muted-foreground">Después de activar un plan, reanudá las búsquedas que quieras seguir desde sus resultados.</p> : null}
            {waitlist?.plan ? (
              <p className="text-sm text-muted-foreground">
                {cfg.commercialPilot ? "Solicitaste" : "Estás en la lista de espera de"} {isWaitlistPlan(waitlist.plan) ? PLAN_COPY[waitlist.plan].name : waitlist.plan}.
              </p>
            ) : null}
            <ProCtaButton placement="settings" variant="outline" />
            {payments?.length ? <div className="border-t pt-3">
              <h2 className="text-sm font-medium">Períodos pagados</h2>
              <ul className="mt-2 space-y-2 text-sm text-muted-foreground">{payments.map((p) => <li key={p.id}>
                {isWaitlistPlan(p.offer) ? PLAN_COPY[p.offer].name : p.offer} · {planPrice(p.amount)} ARS · hasta {accessDate(p.period_end)}
                {p.refunded_at ? " · devolución registrada" : ""}
              </li>)}</ul>
            </div> : null}
            <p className="text-sm text-muted-foreground">Ayuda para pagos y devoluciones: <Link href="/terminos" className="underline">contacto y condiciones</Link>.</p>
          </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cuenta</CardTitle>
          <CardDescription>{profile?.email ?? user.email}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <form action="/auth/signout" method="post">
            <Button type="submit" variant="outline">
              Cerrar sesión
            </Button>
          </form>
          <DeleteAccount />
        </CardContent>
      </Card>
    </div>
  );
}
