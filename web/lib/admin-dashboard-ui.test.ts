import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DashboardActivation, DashboardAttention, DashboardHeader, DashboardKpi, DashboardOperation, DashboardRevenue, DashboardSummaryKpis, DashboardTrend } from "@/components/admin/dashboard-ui";
import { getDashboardPeriod, type DashboardData, type DashboardMetrics, type DashboardSnapshot } from "@/lib/admin-dashboard";

const period = getDashboardPeriod("7", new Date("2026-10-27T18:00:00Z"));
const empty: DashboardMetrics = {
  signups: 0, activationEligible: 0, activatedWithin24h: 0, activeUsers: 0,
  searchesCreated: 0, firstValueEligible: 0, firstValueUnobserved: 0, firstValueWithin24h: 0, firstValueMedianHours: null,
  grossRevenue: 0, refunds: 0, particularSales: 0, agencyPayments: 0, firstPayingUsers: 0,
};
function snapshot(current: Partial<DashboardMetrics> = {}): DashboardSnapshot {
  const currentState = { enabledSearches: 0, searchesWithoutValue24h: 0, pendingNotifications: 0,
    failedNotifications: 0, pendingCheckouts: 0, checkoutSyncErrors: 0, agencyMonthlyEquivalent: 0, authorizedRecurringMrr: 0 };
  return { ...period, firstValueTrackingSince: "2026-10-01T03:00:00Z", current: { ...empty, ...current }, previous: empty, daily: [], currentState };
}
function data(): DashboardData {
  return { period, metrics: { data: snapshot(), error: null }, sources: { data: [], error: null }, llm: { data: [], error: null } };
}

describe("admin decision UI", () => {
  it("does not invent growth when the previous count is zero", () => {
    const html = renderToStaticMarkup(createElement(DashboardKpi, { label: "Cuentas", current: 5, previous: 0, definition: "Altas" }));
    expect(html).toContain("Base anterior 0 · sin variación porcentual");
    expect(html).not.toMatch(/100%|Infinity|NaN/);
  });

  it("keeps unknown rates separate from measured zero counts", () => {
    const html = renderToStaticMarkup(createElement(DashboardSummaryKpis, { snapshot: snapshot() }));
    expect(html.match(/<article/g)).toHaveLength(6);
    expect(html.match(/Sin base para comparar/g)).toHaveLength(2);
    expect(html).toContain("0 de 0 cuentas");
    expect(html).not.toContain("NaN");
  });

  it("shows the cohort denominator, missing first values and fractional achieved-only median", () => {
    const html = renderToStaticMarkup(createElement(DashboardActivation, { snapshot: snapshot({ signups: 10, activationEligible: 8,
      activatedWithin24h: 4, searchesCreated: 6, firstValueEligible: 5, firstValueWithin24h: 2, firstValueMedianHours: 1.5 }) }));
    expect(html).toContain("4 de 8 cuentas observables");
    expect(html).toContain("2 de 5 búsquedas observables");
    expect(html).toContain("3 sin ese resultado");
    expect(html).toContain("1,5 h");
    expect(html).toContain("solo entre las 2 búsquedas");
  });

  it("keeps historical searches without complete observation outside the first-value rate", () => {
    const html = renderToStaticMarkup(createElement(DashboardActivation, { snapshot: snapshot({
      searchesCreated: 9, firstValueEligible: 2, firstValueUnobserved: 6, firstValueWithin24h: 1,
    }) }));
    expect(html).toContain("1 de 2 búsquedas observables");
    expect(html).toContain("6 en este período");
    expect(html).toContain("El score actual no reconstruye un logro histórico");
  });

  it("keeps source and LLM read failures visible independently without claiming empty results", () => {
    const value = data();
    value.sources = { data: null, error: "No se pudo consultar fuentes" };
    value.llm = { data: null, error: "No se pudo consultar trabajos" };
    const html = renderToStaticMarkup(createElement(DashboardOperation, { data: value }));
    expect(html).toContain("No se pudo consultar fuentes");
    expect(html).toContain("No se pudo consultar trabajos");
    expect(html).not.toContain("Sin pendientes en estos controles");
    expect(html).not.toContain("No hubo trabajos");
    expect(html).not.toContain("No hay fuentes registradas");
  });

  it("does not claim operational health when metrics could not be read", () => {
    const value = data();
    value.metrics = { data: null, error: "RPC no disponible; aplicar migración" };
    const html = renderToStaticMarkup(createElement(DashboardAttention, { data: value }));
    expect(html).toContain("RPC no disponible; aplicar migración");
    expect(html).not.toContain("Sin pendientes en estos controles");
  });

  it("shows refunds and the arithmetic cash difference while keeping missing costs explicit", () => {
    const html = renderToStaticMarkup(createElement(DashboardRevenue, { snapshot: snapshot({ grossRevenue: 1000, refunds: 1200 }) }));
    expect(html).toContain("ARS -200");
    expect(html).toContain("por fecha de devolución");
    expect(html).toContain("Costos de anuncios, infraestructura y proveedores: sin conectar");
    expect(html).toContain("no se presenta como MRR");
  });

  it("labels completed Argentina days, the prior range and the filter", () => {
    const html = renderToStaticMarkup(createElement(DashboardHeader, { title: "Resumen", description: "Actividad", period }));
    expect(html).toContain("20/10/2026 al 26/10/2026");
    expect(html).toContain("13/10/2026 al 19/10/2026");
    expect(html).toContain('for="dashboard-days"');
    expect(html).toContain('name="days"');
    expect(html).toContain("El día de hoy queda fuera");
  });

  it("provides exact daily values and reports an empty observed maximum honestly", () => {
    const html = renderToStaticMarkup(createElement(DashboardTrend, { daily: [{ day: "2026-10-20", signups: 0,
      activeUsers: 0, searchesCreated: 0, grossRevenue: 0, refunds: 0 }], field: "activeUsers", label: "Usuarios activos" }));
    expect(html).toContain("máximo diario 0");
    expect(html).toContain("Ver valores diarios");
    expect(html).toContain("20/10/2026");
    expect(html).not.toContain("NaN");
  });
});
