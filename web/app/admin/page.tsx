import type { Metadata } from "next";

import { ContactedMetric, CriteriaGrid } from "@/components/admin/criteria";
import { DashboardAttention, DashboardCashNote, DashboardHeader, DashboardSummaryKpis, DashboardTrend, DashboardUnavailable } from "@/components/admin/dashboard-ui";
import { Section, TextLink } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { loadAdminDashboard } from "@/lib/admin-dashboard-data";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Resumen" };

export default async function AdminHome({ searchParams }: PageProps<"/admin">) {
  await requireAdmin();
  const { days } = await searchParams;
  const admin = createAdminClient();
  const [data, criteria, contacted] = await Promise.all([
    loadAdminDashboard(days),
    admin.from("v_validation_criteria").select("*").order("ordinal"),
    admin.from("v_contacted_metric").select("users, events").maybeSingle(),
  ]);
  const snapshot = data.metrics.data;

  return (
    <>
      <DashboardHeader title="Resumen" description="Cómo se usa Ese Auto, qué valor entrega y qué necesita atención." period={data.period} />

      <Section title="El período en seis números" description="Cada indicador se compara con los días inmediatamente anteriores. Los admins quedan fuera de los agregados de usuarios.">
        {snapshot ? <><DashboardSummaryKpis snapshot={snapshot} /><DashboardCashNote snapshot={snapshot} /></> : <DashboardUnavailable title="Indicadores del período no disponibles" error={data.metrics.error} />}
      </Section>

      <DashboardAttention data={data} />

      {snapshot ? <Section title="Actividad diaria" description="Personas con al menos una acción humana por día. Una persona puede aparecer en más de un día; el total del período cuenta personas únicas.">
        <DashboardTrend daily={snapshot.daily} field="activeUsers" label="Usuarios activos" />
        <TextLink href={`/admin/metrics?view=activation&days=${data.period.days}`} className="text-sm">Explorar activación, ingresos y operación →</TextLink>
      </Section> : null}

      <Section title="Criterios de validación (§53)" description="Los seis criterios históricos del MVP. Sus ventanas y umbrales son propios; no siguen el filtro de este resumen.">
        {criteria.error ? <DashboardUnavailable title="Criterios no disponibles" error={criteria.error.message} /> : <CriteriaGrid rows={criteria.data ?? []} />}
        <ContactedMetric row={contacted.error ? null : (contacted.data ?? null)} />
        <div className="flex flex-wrap gap-4 text-xs"><TextLink href="/admin/config#validation_criteria">Revisar umbrales →</TextLink><TextLink href="/admin/metrics/diagnostic">Abrir diagnóstico histórico →</TextLink></div>
      </Section>
    </>
  );
}
