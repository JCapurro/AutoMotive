import type { Metadata } from "next";

import { DashboardActivation, DashboardHeader, DashboardNav, DashboardOperation, DashboardRevenue, DashboardUnavailable, type DashboardView } from "@/components/admin/dashboard-ui";
import { requireAdmin } from "@/lib/admin";
import { loadAdminDashboard } from "@/lib/admin-dashboard-data";

export const metadata: Metadata = { title: "Métricas" };

export default async function MetricsPage({ searchParams }: PageProps<"/admin/metrics">) {
  await requireAdmin();
  const query = await searchParams;
  const view: DashboardView = query.view === "revenue" || query.view === "operation" ? query.view : "activation";
  const data = await loadAdminDashboard(query.days);

  return (
    <>
      <DashboardHeader title="Métricas" description="De la primera búsqueda a los cobros y al funcionamiento del servicio." period={data.period} view={view} />
      <DashboardNav days={data.period.days} active={view} />
      {view === "operation" ? <DashboardOperation data={data} /> : data.metrics.data ? view === "revenue"
        ? <DashboardRevenue snapshot={data.metrics.data} />
        : <DashboardActivation snapshot={data.metrics.data} />
        : <DashboardUnavailable title={`${view === "revenue" ? "Ingresos" : "Activación"}: datos no disponibles`} error={data.metrics.error} />}
    </>
  );
}
