import type { Metadata } from "next";
import { PaymentForm, PilotLaunch, RefundForm } from "@/components/admin/billing-forms";
import { PageHeader, Table, Th, Td, EmptyRow } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { webConfig } from "@/lib/config";
import { accessDate, PLAN_COPY, planPrice, type WaitlistPlan } from "@/lib/pro";
import { createAdminClient } from "@/lib/supabase/admin";
import { paymentsConfigured } from "@/lib/mercadopago-server";

export const metadata: Metadata = { title: "Cobros" };
export default async function BillingPage() {
  await requireAdmin();
  const db = createAdminClient();
  const [cfg, { data: users }, { data: payments, error }, { data: revenue }, { data: declines }, { data: checkouts, error: checkoutError }] = await Promise.all([
    webConfig(), db.from("admin_users").select("id,email,plan,enabled_searches,waitlist_plan").limit(500),
    db.from("commercial_payments").select("*").order("verified_at", { ascending: false }).limit(100),
    db.from("commercial_revenue").select("*").maybeSingle(),
    db.from("events").select("user_id,created_at,props").eq("name", "renewal_declined").order("created_at", { ascending: false }).limit(100),
    db.from("billing_checkouts").select("id,user_id,offer,status,last_synced_at,sync_error").order("created_at", { ascending: false }).limit(100),
  ]);
  const email = new Map((users ?? []).map((u) => [u.id, u.email ?? "Solo Telegram"]));
  const pending = (users ?? []).filter((u) => u.waitlist_plan);
  const excess = (users ?? []).reduce((n, u) => n + Math.max(0, (u.enabled_searches ?? 0) - (u.plan === "pro" ? 10 : u.plan === "pass" ? 3 : 1)), 0);
  return <div className="space-y-6">
    <PageHeader title="Cobros y acceso" description="Mercado Pago procesa los cobros. Acá revisás el acceso y registrás pagos asistidos ya verificados." />
    <p className="rounded border p-4 text-sm">{checkoutError ? "Falta la migración de Mercado Pago." : !paymentsConfigured() ? "Falta configurar los secretos de Mercado Pago y la conciliación." : cfg.automaticPayments ? "Cobro y acceso automáticos habilitados." : "Integración configurada; contratación automática deshabilitada."}</p>
    <section className="space-y-2"><h2 className="font-semibold">Contrataciones de Mercado Pago</h2>
      <ul className="space-y-1 text-sm">{(checkouts ?? []).map((c) => <li key={c.id}>{email.get(c.user_id) ?? c.user_id} · {PLAN_COPY[c.offer as WaitlistPlan]?.name} · {c.status}
        {c.sync_error ? " · requiere revisión" : ""}{c.last_synced_at ? ` · consultado ${accessDate(c.last_synced_at)}` : " · aún sin conciliación"}<span className="block text-xs text-muted-foreground">{c.id}</span></li>)}</ul>
      <p className="text-sm text-muted-foreground">Enlaces para cobro asistido: <a href="https://mpago.la/2Vf746M" className="underline" target="_blank" rel="noreferrer">Particular</a> · <a href="https://mpago.la/1t6wWDT" className="underline" target="_blank" rel="noreferrer">Agencia</a>. Requieren asociar manualmente el pago y gestionar la suscripción en Mercado Pago.</p>
    </section>
    {error ? <p role="alert" className="rounded border p-4 text-sm">Falta aplicar la migración comercial en esta base. Las altas están pendientes.</p> : <>
      <PilotLaunch enabled={cfg.commercialPilot} freeUsers={(users ?? []).filter((u) => u.plan === "free" && (u.enabled_searches ?? 0) > 0).length} excessSearches={excess} />
      <dl className="grid gap-4 rounded-xl border p-5 sm:grid-cols-3">
        <div><dt className="text-sm text-muted-foreground">Ingresos confirmados del mes</dt><dd className="text-xl font-bold">{planPrice(revenue?.confirmed_revenue ?? 0)}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Particular vendidos este mes</dt><dd className="text-xl font-bold">{revenue?.particular_sales ?? 0}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Mensualidades Agencia vigentes</dt><dd className="text-xl font-bold">{planPrice(revenue?.agency_monthly_equivalent ?? 0)}</dd></div>
      </dl>
      <p className="text-sm text-muted-foreground">Las mensualidades vigentes incluyen períodos asistidos y automáticos; no equivalen por sí solas a suscripciones autorizadas.
        Devoluciones registradas este mes: {planPrice(revenue?.refunds ?? 0)}. Costos y horas se registran en la planilla operativa del piloto.</p>
      <section className="space-y-2"><h2 className="font-semibold">Solicitudes de alta o renovación</h2>
        {pending.length ? <ul className="space-y-1 text-sm">{pending.map((u) => <li key={u.id}>{email.get(u.id)} · {PLAN_COPY[u.waitlist_plan as WaitlistPlan]?.name ?? u.waitlist_plan}</li>)}</ul>
          : <p className="text-sm text-muted-foreground">Sin solicitudes pendientes.</p>}</section>
      <PaymentForm users={(users ?? []).filter((u): u is typeof u & { id: string } => Boolean(u.id))} offer={cfg.proOffer} />
      <section className="space-y-2"><h2 className="font-semibold">Avisos de no renovación</h2>
        {declines?.length ? <ul className="space-y-1 text-sm">{declines.map((d, i) => <li key={i}>{email.get(d.user_id)} · {accessDate(d.created_at)}</li>)}</ul> : <p className="text-sm text-muted-foreground">Sin avisos.</p>}</section>
      <Table><thead><tr><Th>Cuenta / referencia</Th><Th>Plan / importe</Th><Th>Período pagado</Th><Th>Devolución</Th></tr></thead>
        <tbody>{(payments ?? []).map((p) => <tr key={p.id}>
          <Td>{email.get(p.user_id)}<span className="block text-xs text-muted-foreground">{p.provider} · {p.reference}</span></Td>
          <Td>{PLAN_COPY[p.offer as WaitlistPlan]?.name}<span className="block">{planPrice(p.amount)} ARS</span></Td>
          <Td>{accessDate(p.period_start)}<span className="block">hasta {accessDate(p.period_end)}</span></Td>
          <Td>{p.refunded_at ? `Registrada ${accessDate(p.refunded_at)}` : <RefundForm id={p.id} />}</Td>
        </tr>)}{!payments?.length ? <EmptyRow colSpan={4} /> : null}</tbody>
      </Table>
    </>}
  </div>;
}
