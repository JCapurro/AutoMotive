import type { Metadata } from "next";

import { BarList, Card, rate } from "@/components/admin/dash";
import { EmptyRow, PageHeader, Pill, Stat, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { CAUSE_LABEL, buildDemandDashboard } from "@/lib/admin-demand-data";
import { loadDemandInput } from "@/lib/admin-demand-load";
import { count, when } from "@/lib/admin-format";
import { LEVEL } from "@/lib/copy";

export const metadata: Metadata = { title: "Demanda insatisfecha" };
export const dynamic = "force-dynamic";

// Searches that find little or nothing, why, and what the free plan's cap hides.
// Everything is precomputed by the worker's nightly job: this page only reads.
export default async function DemandPage() {
  const { rows, run } = await loadDemandInput();
  const d = buildDemandDashboard(rows, run, new Date());
  const sample = `Sobre ${count(d.total)} búsquedas`;

  return (
    <>
      <PageHeader
        title="Demanda insatisfecha"
        description="Búsquedas activas que encuentran poco o nada, qué las destrabaría y cuántos buenos autos esconde el cupo del plan gratis."
      />

      {!d.computedAt ? (
        <Card title="Todavía no se calculó">
          <p className="text-sm text-muted-foreground">
            El cálculo corre solo una vez por noche y está apagado hasta que se prenda <code>unmet_demand</code> en Config. Mientras tanto no hay datos acá.
          </p>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">
          Calculado: {when(d.computedAt)} ({d.seconds} s).{" "}
          {d.stale ? <Pill tone="warn">Desactualizado: hace más de un día y medio</Pill> : null}{" "}
          Cuenta búsquedas con {d.threshold?.maxResults} resultados o menos y más de {d.threshold?.minAgeHours} h de creadas
          {d.skippedModelLess ? `; deja afuera ${count(d.skippedModelLess)} sin modelo (por carrocería)` : ""}.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Búsquedas con poco o nada" value={count(d.total)} />
        <Stat label="Se destraban con un cambio" value={count(d.total - (d.causes.find((c) => c.key === "none")?.value ?? 0))} note={`${rate(d.total - (d.causes.find((c) => c.key === "none")?.value ?? 0), d.total)} de ${count(d.total)}`} />
        <Stat label="Sin oferta" value={count(d.causes.find((c) => c.key === "none")?.value ?? 0)} note={`${rate(d.causes.find((c) => c.key === "none")?.value ?? 0, d.total)} de ${count(d.total)}`} />
        <Stat label="Buenos autos tapados por el cupo" value={d.hidden.known ? count(d.hidden.total) : "—"} note={d.hidden.known ? `${count(d.hidden.accounts)} cuentas gratis` : undefined} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Por qué no encuentran" description={`${sample}. La causa es el cambio suelto que más autos suma; «Sin oferta» es que ninguno suma.`}>
          <BarList rows={d.causes.map((c) => ({ key: c.key, label: c.label, value: c.value, note: undefined }))} total={d.total} />
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {d.causes.map((c) => <li key={c.key}><strong>{c.label}:</strong> {c.note}</li>)}
          </ul>
        </Card>

        <Card
          title="Lo que el cupo esconde"
          description="Coincidencias de cuentas gratis que quedaron fuera de su cupo (autos activos), por nivel. Una por cuenta y auto."
        >
          {!d.hidden.known ? (
            <p className="text-sm text-muted-foreground">Sin datos todavía.</p>
          ) : !d.hidden.enforced ? (
            <p className="text-sm text-muted-foreground">El cupo no está activo (plan_limits.enforced está en false): no se esconde nada.</p>
          ) : d.hidden.levels.length === 0 ? (
            <p className="text-sm text-muted-foreground">Ninguna cuenta gratis tiene coincidencias fuera del cupo.</p>
          ) : (
            <>
              <BarList
                rows={d.hidden.levels.map((l) => ({ key: l.level, label: `${LEVEL[l.level].emoji} ${LEVEL[l.level].label}`, value: l.value }))}
                total={d.hidden.total}
              />
              <p className="text-xs text-muted-foreground">
                {count(d.hidden.total)} coincidencias en {count(d.hidden.accounts)} cuentas; los porcentajes son sobre esas {count(d.hidden.total)}.
              </p>
            </>
          )}
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold tracking-tight">
          Modelo y zona <span className="text-sm font-normal text-muted-foreground">búsquedas esperando contra autos publicados (últimos 30 días)</span>
        </h2>
        <Table>
          <thead>
            <tr>
              <Th>Modelo</Th>
              <Th>Zona</Th>
              <Th numeric>Búsquedas esperando</Th>
              <Th numeric>Autos activos en la zona</Th>
              <Th numeric>Autos activos del modelo</Th>
              <Th>Causa principal</Th>
            </tr>
          </thead>
          <tbody>
            {d.modelZones.length === 0 ? <EmptyRow colSpan={6} /> : d.modelZones.map((m) => (
              <tr key={m.key}>
                <Td className="font-medium">{m.model}</Td>
                <Td>{m.zone}</Td>
                <Td numeric>{count(m.searches)}</Td>
                <Td numeric>{count(m.listingsInZone)}</Td>
                <Td numeric>{count(m.listings)}</Td>
                <Td>{CAUSE_LABEL[m.cause]}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold tracking-tight">
          Búsquedas afectadas <span className="text-sm font-normal text-muted-foreground">{count(d.affected.length)} de {count(d.total)}, las que más ganarían primero</span>
        </h2>
        <Table>
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Búsqueda</Th>
              <Th>Zona</Th>
              <Th numeric>Resultados</Th>
              <Th>Causa</Th>
              <Th numeric>Sumaría</Th>
            </tr>
          </thead>
          <tbody>
            {d.affected.length === 0 ? <EmptyRow colSpan={6} /> : d.affected.map((s) => (
              <tr key={s.search_profile_id}>
                <Td className="tabular-nums">{s.search_profile_id}</Td>
                <Td><TextLink href={`/admin/users/${s.user_id}`}>{s.vehicle}</TextLink></Td>
                <Td>{s.zone_label ?? "Sin zona"}</Td>
                <Td numeric>{count(s.result_count)}</Td>
                <Td>{CAUSE_LABEL[s.cause]}</Td>
                <Td numeric>{s.unlocks ? `+${count(s.unlocks)}` : "—"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </section>
    </>
  );
}
