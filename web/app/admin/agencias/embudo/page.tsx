import type { Metadata } from "next";

import { EmptyRow, PageHeader, Pill, Section, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { DASHBOARD_DAYS, getDashboardPeriod } from "@/lib/admin-dashboard";
import { type FunnelCounts, funnelSteps, parseAdminFunnel, rateText, stepRate } from "@/lib/dealer-funnel";
import { number, TIME_ZONE } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Embudo de agencias" };

const fullDate = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: TIME_ZONE });

/**
 * The sales channel, step by step (admin_dealer_funnel, service role): per
 * agency and in total, for 7, 30 or 90 complete Argentina days. Aggregates
 * only: no buyer's name, phone or id comes out of the RPC.
 */
export default async function DealerFunnelPage({ searchParams }: PageProps<"/admin/agencias/embudo">) {
  await requireAdmin();
  const query = await searchParams;
  const period = getDashboardPeriod(query.days);
  const { data, error } = await createAdminClient().rpc("admin_dealer_funnel", { p_start: period.start, p_end: period.end });
  const funnel = error ? null : parseAdminFunnel(data);
  if (error) console.error("admin_dealer_funnel:", error.code);

  return (
    <>
      <PageHeader
        title="Embudo de agencias"
        description="Del stock cargado a la venta declarada. Stock y visibles son de hoy; el resto, del período."
      >
        <form method="get" className="flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor="funnel-days" className="font-medium">Período</label>
          <select id="funnel-days" name="days" defaultValue={period.days} className="h-9 rounded-md border bg-background px-2">
            {DASHBOARD_DAYS.map((days) => <option key={days} value={days}>{days} días completos</option>)}
          </select>
          <button type="submit" className="h-9 rounded-md bg-primary px-3 font-medium text-primary-foreground">Aplicar</button>
        </form>
      </PageHeader>
      <p className="border-y py-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{fullDate.format(new Date(period.start))} al {fullDate.format(new Date(Date.parse(period.end) - 1))}</span>
        {" "}· hora argentina · el día de hoy queda fuera · <TextLink href="/admin/agencias">Volver a agencias</TextLink>
      </p>

      {!funnel ? (
        <div role="status" className="rounded-lg border border-warn/30 bg-warn-soft p-4 text-sm">
          <p className="font-semibold text-warn">Embudo: datos no disponibles</p>
          <p className="text-muted-foreground">Falta la migración 20261230120000_dealer_funnel.sql o la consulta falló.</p>
        </div>
      ) : (
        <>
          <Section title="Total" description="Personas: distintas entre todas las agencias. Sin cuentas admin ni los propios miembros de cada agencia.">
            <FunnelTable counts={funnel.total} />
          </Section>
          <Section title="Por agencia" description="Solo conteos.">
            <Table>
              <thead>
                <tr>
                  <Th>Agencia</Th><Th numeric>Stock</Th><Th numeric>Visibles</Th><Th numeric>Coincid.</Th><Th numeric>En alerta</Th>
                  <Th numeric>Personas</Th><Th numeric>Consultas</Th><Th numeric>Contact.</Th><Th numeric>Reserv.</Th>
                  <Th numeric>Compraron</Th><Th numeric>No avanz.</Th><Th numeric>Ventas EA</Th><Th numeric>Consultas / persona</Th>
                </tr>
              </thead>
              <tbody>
                {funnel.dealers.length === 0 ? <EmptyRow colSpan={13}>Todavía no se dio de alta ninguna agencia.</EmptyRow> : null}
                {funnel.dealers.map((d) => (
                  <tr key={d.dealer_id}>
                    <Td>
                      <b className="font-semibold">{d.name}</b>{" "}
                      {d.status === "paused" ? <Pill tone="warn">Pausada</Pill> : d.approved ? null : <Pill>Sin aprobar</Pill>}
                    </Td>
                    <Td numeric>{number(d.stock)}</Td>
                    <Td numeric>{number(d.visible)}</Td>
                    <Td numeric>{number(d.matched_cars)}</Td>
                    <Td numeric>{number(d.alerted_cars)}</Td>
                    <Td numeric>{number(d.people)}</Td>
                    <Td numeric>{number(d.leads)}</Td>
                    <Td numeric>{number(d.contacted)}</Td>
                    <Td numeric>{number(d.reserved)}</Td>
                    <Td numeric>{number(d.sold)}</Td>
                    <Td numeric>{number(d.lost)}</Td>
                    <Td numeric>{number(d.sales_via_ese_auto)}{d.sales_elsewhere ? <span className="text-muted-foreground"> / {number(d.sales_elsewhere)} otro</span> : null}</Td>
                    <Td numeric>{rateText(stepRate(d.leads, d.people))}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Section>
        </>
      )}
    </>
  );
}

function FunnelTable({ counts }: { counts: FunnelCounts }) {
  return (
    <Table>
      <thead>
        <tr><Th>Paso</Th><Th numeric>Cantidad</Th><Th numeric>Tasa</Th><Th>Qué cuenta</Th></tr>
      </thead>
      <tbody>
        {funnelSteps(counts).map((s) => (
          <tr key={s.key} data-testid={`funnel-${s.key}`}>
            <Td className="font-medium">{s.label}</Td>
            <Td numeric>{number(s.value)}</Td>
            <Td numeric>{s.of ? <>{rateText(s.rate)} <span className="text-xs text-muted-foreground">{s.of}</span></> : ""}</Td>
            <Td className="text-xs text-muted-foreground">{s.hint}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
