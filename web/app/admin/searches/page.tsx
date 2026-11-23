import type { Metadata } from "next";

import { BarList, Card, LinkTabs, rate, withParams } from "@/components/admin/dash";
import { EmptyRow, PageHeader, Pill, Stat, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { count, filterSummary, when } from "@/lib/admin-format";
import { loadSearchesInput } from "@/lib/admin-load";
import { buildSearchesDashboard } from "@/lib/admin-searches-data";
import { PERIODS, periodDays } from "@/lib/admin-users-data";
import { CHANNEL, LEVEL } from "@/lib/copy";

export const metadata: Metadata = { title: "Búsquedas" };

const VIEWS = [
  { key: "todas", label: "Todas" },
  { key: "activas", label: "Activas" },
  { key: "sin-resultados", label: "Sin resultados" },
  { key: "con-clics", label: "Con clics" },
  { key: "pausadas", label: "Pausadas" },
] as const;
const TABLE_LIMIT = 300;

// sección 10, "Búsquedas": what people look for, what finds nothing, how alerts do.
export default async function SearchesPage({ searchParams }: PageProps<"/admin/searches">) {
  const params = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const current = { periodo: one(params.periodo), vista: one(params.vista) };
  const days = periodDays(current.periodo);
  const periodKey = PERIODS.find((p) => p.days === days)!.key;
  let input: Awaited<ReturnType<typeof loadSearchesInput>>;
  try {
    input = await loadSearchesInput();
  } catch (e) {
    // Only a failed read (timeout) becomes a notice; the admin check's redirect/404 must still propagate.
    if (!(e instanceof Error) || !e.message.startsWith("admin read failed")) throw e;
    console.error("admin searches:", e.message);
    return (
      <>
        <PageHeader title="Búsquedas" description="No se pudieron leer las búsquedas." />
        <p role="status" className="rounded-lg bg-muted p-4 text-sm">
          La base tardó demasiado en responder. Recargá la página en un minuto; si sigue igual, avisá.
        </p>
      </>
    );
  }
  const { searches, notifications } = input;
  const d =buildSearchesDashboard(searches, notifications, new Date(), days);
  const { kpis } = d;
  const view = VIEWS.find((v) => v.key === current.vista)?.key ?? "todas";
  const listed = d.inPeriod
    .filter((s) =>
      view === "activas" ? s.enabled : view === "sin-resultados" ? s.noResults : view === "con-clics" ? s.clicked > 0 : view === "pausadas" ? !s.enabled : true,
    )
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const periodText = days ? `los últimos ${days} días` : "todo el historial";

  return (
    <>
      <PageHeader title="Búsquedas" description={`${count(kpis.total)} búsquedas, ${count(kpis.active)} activas. Lo de abajo mira las creadas en ${periodText}.`}>
        <LinkTabs
          label="Período"
          current={periodKey}
          items={PERIODS.map((p) => ({ key: p.key, label: p.label, href: withParams("/admin/searches", current, { periodo: p.key === "30" ? null : p.key }) }))}
        />
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Creadas" value={count(kpis.created)} note={`de ${count(kpis.users)} usuarios`} />
        <Stat label="Siguen activas" value={rate(kpis.activeInPeriod, kpis.created)} />
        <Stat label="Sin resultados" value={count(kpis.noResults)} note={`${rate(kpis.noResults, kpis.activeInPeriod)} de las activas`} />
        <Stat label="Matches (mediana)" value={count(kpis.medianMatches)} />
        <Stat label="Alertas enviadas" value={count(kpis.sent)} note={`${kpis.openRate}% abiertas`} />
        <Stat label="Clic en alertas" value={`${kpis.clickRate}%`} note={`${count(kpis.pending)} esperan su primer match`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Qué autos buscan" description="Marca y modelo; al lado, cuántas no encuentran nada o los matches promedio.">
          <BarList rows={d.topModels} />
        </Card>
        <Card title="Marcas">
          <BarList rows={d.makes} total={kpis.created} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Presupuesto en dólares">
          <BarList rows={d.usd} />
        </Card>
        <Card title="Presupuesto en pesos">
          <BarList rows={d.ars} />
        </Card>
        <Card title="Otros datos" description={`${count(d.noPrice)} búsquedas sin precio máximo.`}>
          <div className="space-y-4">
            <BarList rows={d.years} total={kpis.created} />
            <BarList rows={d.frequency} total={kpis.created} />
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Zonas">
          <BarList rows={d.zones} total={kpis.created} />
        </Card>
        <Card title="Radio">
          <BarList rows={d.radius} total={kpis.created} />
        </Card>
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold tracking-tight">
            Búsquedas{" "}
            <span className="text-sm font-normal text-muted-foreground">
              {count(listed.length)}
              {listed.length > TABLE_LIMIT ? `, se muestran las ${TABLE_LIMIT} más nuevas` : ""}
            </span>
          </h2>
          <LinkTabs label="Vista" current={view} items={VIEWS.map((v) => ({ key: v.key, label: v.label, href: withParams("/admin/searches", current, { vista: v.key === "todas" ? null : v.key }) }))} />
        </div>
        <Table>
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Búsqueda</Th>
              <Th>Usuario</Th>
              <Th>Alertas</Th>
              <Th numeric>Matches</Th>
              <Th numeric>🔥</Th>
              <Th numeric>Enviadas</Th>
              <Th numeric>Abiertas</Th>
              <Th numeric>Clics</Th>
              <Th>Estado</Th>
              <Th>Creada</Th>
            </tr>
          </thead>
          <tbody>
            {listed.slice(0, TABLE_LIMIT).map((s) => (
              <tr key={s.id} id={`search-${s.id}`}>
                <Td className="tabular-nums">{s.id}</Td>
                <Td className="max-w-72">
                  <span className="block font-medium">{s.name}</span>
                  <span className="text-xs text-muted-foreground">{filterSummary(s.filters)}</span>
                </Td>
                <Td className="max-w-48">
                  <TextLink href={`/admin/users/${s.user_id}`} className="block truncate">{s.email ?? "Solo Telegram"}</TextLink>
                </Td>
                <Td className="text-xs whitespace-nowrap">
                  {s.notification_frequency === "immediate" ? "Inmediata" : "Diaria"} · ≥ {s.notify_min_level ? LEVEL[s.notify_min_level as keyof typeof LEVEL]?.emoji : ""}
                  <span className="block text-muted-foreground">{(s.channels ?? []).map((c) => CHANNEL[c as keyof typeof CHANNEL] ?? c).join(", ")}</span>
                </Td>
                <Td numeric>{count(s.matches)}</Td>
                <Td numeric>{count(s.high_matches)}</Td>
                <Td numeric>{count(s.sent)}</Td>
                <Td numeric>{s.sent ? rate(s.opened, s.sent) : "—"}</Td>
                <Td numeric>{count(s.clicked)}</Td>
                <Td className="whitespace-nowrap">
                  {!s.enabled ? (
                    <Pill>pausada</Pill>
                  ) : s.rematch_requested_at ? (
                    <Pill tone="warn">re-match pendiente</Pill>
                  ) : !s.bootstrapped_at ? (
                    <Pill tone="warn">pendiente</Pill>
                  ) : s.noResults ? (
                    <Pill tone="bad">sin resultados</Pill>
                  ) : (
                    <Pill tone="ok">activa</Pill>
                  )}
                </Td>
                <Td className="whitespace-nowrap">{when(s.created_at)}</Td>
              </tr>
            ))}
            {!listed.length ? <EmptyRow colSpan={11} /> : null}
          </tbody>
        </Table>
      </section>
    </>
  );
}
