import Link from "next/link";

import { EmptyRow, PageHeader, Section, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { count, percent, when } from "@/lib/admin-format";
import {
  DASHBOARD_DAYS,
  metricChange,
  metricRate,
  type DashboardDaily,
  type DashboardData,
  type DashboardDays,
  type DashboardPeriod,
  type DashboardSnapshot,
} from "@/lib/admin-dashboard";
import { money, TIME_ZONE } from "@/lib/format";

export type DashboardView = "activation" | "revenue" | "operation" | "diagnostic";

const VIEWS: { id: DashboardView; label: string }[] = [
  { id: "activation", label: "Activación" },
  { id: "revenue", label: "Ingresos" },
  { id: "operation", label: "Operación" },
  { id: "diagnostic", label: "Diagnóstico" },
];

const fullDate = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: TIME_ZONE });
const dateTime = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: TIME_ZONE });

function periodRange(start: string, end: string) {
  return `${fullDate.format(new Date(start))} al ${fullDate.format(new Date(Date.parse(end) - 1))}`;
}

export function DashboardHeader({ title, description, period, view }: {
  title: string;
  description: string;
  period: DashboardPeriod;
  view?: DashboardView;
}) {
  return (
    <div className="space-y-4">
      <PageHeader title={title} description={description}>
        <form method="get" className="flex flex-wrap items-center gap-2 text-sm">
          {view ? <input type="hidden" name="view" value={view} /> : null}
          <label htmlFor="dashboard-days" className="font-medium">Período</label>
          <select id="dashboard-days" name="days" defaultValue={period.days} className="h-9 rounded-md border bg-background px-2">
            {DASHBOARD_DAYS.map((days) => <option key={days} value={days}>{days} días completos</option>)}
          </select>
          <button type="submit" className="h-9 rounded-md bg-primary px-3 font-medium text-primary-foreground">Aplicar</button>
        </form>
      </PageHeader>
      <div className="flex flex-wrap justify-between gap-x-6 gap-y-2 border-y py-3 text-xs text-muted-foreground">
        <div className="space-y-1">
          <p><span className="font-medium text-foreground">{periodRange(period.start, period.end)}</span> · hora argentina (ART)</p>
          <p>Comparado con {periodRange(period.previousStart, period.start)} · {period.days} días</p>
        </div>
        <p>Consulta: <time dateTime={period.asOf}>{dateTime.format(new Date(period.asOf))}</time> ART<br />El día de hoy queda fuera del período.</p>
      </div>
    </div>
  );
}

export function DashboardNav({ days, active }: { days: DashboardDays; active: DashboardView }) {
  return (
    <nav aria-label="Vistas de métricas" className="flex flex-wrap gap-1 border-b pb-2">
      {VIEWS.map(({ id, label }) => (
        <Link key={id} href={id === "diagnostic" ? "/admin/metrics/diagnostic" : `/admin/metrics?view=${id}&days=${days}`}
          aria-current={id === active ? "page" : undefined}
          className={`rounded-md px-3 py-2 text-sm font-medium ${id === active ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
          {label}
        </Link>
      ))}
    </nav>
  );
}

export function DashboardUnavailable({ title = "Datos no disponibles", error }: { title?: string; error: string | null }) {
  return (
    <div role="status" className="space-y-2 rounded-lg border border-warn/30 bg-warn-soft p-4 text-sm">
      <p className="font-semibold text-warn">{title}</p>
      <p className="break-words text-muted-foreground">{error || "La consulta no devolvió un resultado válido. Reintentá y revisá la conexión de datos."}</p>
      <p className="text-xs text-muted-foreground">Los valores quedan sin informar hasta completar la lectura.</p>
    </div>
  );
}

export function DashboardKpi({ label, current, previous, definition, rate, currency, hours }: {
  label: string;
  current: number | null;
  previous: number | null;
  definition: string;
  rate?: boolean;
  currency?: boolean;
  hours?: boolean;
}) {
  const format = (n: number | null) => n == null ? "—" : rate ? percent(n) : currency ? money(n, "ARS") : hours ? `${n.toFixed(1).replace(".", ",")} h` : count(n);
  const change = current == null || previous == null ? null : metricChange(current, previous);
  const difference = current == null || previous == null ? null : current - previous;
  const comparison = difference == null ? "Sin base para comparar" : rate
    ? `${difference > 0 ? "+" : ""}${difference.toFixed(1).replace(".", ",")} puntos porcentuales`
    : change == null ? (current === previous ? "Sin cambio · base anterior 0" : "Base anterior 0 · sin variación porcentual")
    : `${change > 0 ? "+" : ""}${percent(change)} frente al anterior`;
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-xl border bg-card p-4">
      <h3 className="text-sm font-medium text-muted-foreground">{label}</h3>
      <p className="type-figure break-words text-3xl leading-tight">{format(current)}</p>
      <div className="space-y-1 text-xs">
        <p className="font-medium">{comparison}</p>
        <p className="text-muted-foreground">Anterior: {format(previous)}</p>
      </div>
      <p className="mt-auto border-t pt-3 text-xs leading-relaxed text-muted-foreground">{definition}</p>
    </article>
  );
}

export function DashboardSummaryKpis({ snapshot }: { snapshot: DashboardSnapshot }) {
  const { current: c, previous: p } = snapshot;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Indicadores del período">
      <DashboardKpi label="Usuarios activos" current={c.activeUsers} previous={p.activeUsers} definition="Personas con acciones en la app durante el período. Recibir un email no cuenta. Excluye admins." />
      <DashboardKpi label="Cuentas nuevas" current={c.signups} previous={p.signups} definition="Cuentas creadas en el período. Excluye admins." />
      <DashboardKpi label="Activación en 24 h" current={metricRate(c.activatedWithin24h, c.activationEligible)} previous={metricRate(p.activatedWithin24h, p.activationEligible)} rate definition={`${count(c.activatedWithin24h)} de ${count(c.activationEligible)} cuentas con 24 h de observación crearon una búsqueda en sus primeras 24 h.`} />
      <DashboardKpi label="Primer valor en 24 h" current={metricRate(c.firstValueWithin24h, c.firstValueEligible)} previous={metricRate(p.firstValueWithin24h, p.firstValueEligible)} rate definition={`${count(c.firstValueWithin24h)} de ${count(c.firstValueEligible)} búsquedas con seguimiento completo y 24 h al cierre lograron un resultado bueno u oportunidad. ${count(c.firstValueUnobserved)} búsquedas anteriores sin historial verificable quedan fuera.`} />
      <DashboardKpi label="Cobros brutos" current={c.grossRevenue} previous={p.grossRevenue} currency definition="Pagos confirmados por fecha de pago. Las devoluciones se muestran por separado debajo." />
      <DashboardKpi label="Búsquedas creadas" current={c.searchesCreated} previous={p.searchesCreated} definition="Búsquedas creadas durante el período por cuentas que no son admin." />
    </div>
  );
}

export function DashboardCashNote({ snapshot }: { snapshot: DashboardSnapshot }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3 text-sm">
      <p>Devoluciones: <strong>{money(snapshot.current.refunds, "ARS")}</strong><span className="block text-xs text-muted-foreground">Anterior: {money(snapshot.previous.refunds, "ARS")} · por fecha de devolución</span></p>
      <p>Cobros menos devoluciones: <strong>{money(snapshot.current.grossRevenue - snapshot.current.refunds, "ARS")}</strong><span className="block text-xs text-muted-foreground">Diferencia del período; no mide ganancia ni ingresos devengados.</span></p>
      <TextLink href="/admin/billing" className="text-xs">Revisar cobros →</TextLink>
    </div>
  );
}

export function DashboardTrend({ daily, field, label, currency = false }: {
  daily: DashboardDaily[];
  field: "activeUsers" | "signups" | "searchesCreated" | "grossRevenue";
  label: string;
  currency?: boolean;
}) {
  const observedMax = Math.max(0, ...daily.map((d) => d[field]));
  const max = Math.max(1, observedMax);
  const points = daily.map((d, i) => `${32 + i * 584 / Math.max(1, daily.length - 1)},${136 - d[field] * 112 / max}`).join(" ");
  const date = (value: string) => fullDate.format(new Date(`${value}T12:00:00-03:00`));
  const format = (n: number) => currency ? money(n, "ARS") : count(n);
  return (
    <div className="min-w-0 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground"><p className="font-medium text-foreground">{label}</p><p>Escala desde 0 · máximo diario {format(observedMax)}</p></div>
      {daily.length ? (
        <>
          <svg viewBox="0 0 640 160" className="mt-3 h-40 w-full" role="img" aria-label={`${label} por día. Escala desde cero. Los valores están disponibles en la tabla diaria.`}>
            <line x1="32" x2="616" y1="136" y2="136" stroke="var(--border)" />
            <line x1="32" x2="616" y1="24" y2="24" stroke="var(--border)" strokeDasharray="3 5" />
            <text x="20" y="140" textAnchor="end" fontSize="10" fill="var(--muted-foreground)">0</text>
            <polyline points={points} fill="none" stroke="var(--foreground)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
            {daily.length <= 30 ? daily.map((d, i) => <circle key={d.day} cx={32 + i * 584 / Math.max(1, daily.length - 1)} cy={136 - d[field] * 112 / max} r="3" fill="var(--foreground)"><title>{date(d.day)}: {format(d[field])}</title></circle>) : null}
          </svg>
          <div className="flex justify-between gap-3 text-xs text-muted-foreground"><span>{date(daily[0].day)}</span><span>{date(daily[daily.length - 1].day)}</span></div>
          <details className="mt-4 border-t pt-3">
            <summary className="cursor-pointer text-xs font-medium">Ver valores diarios</summary>
            <div className="mt-3 max-h-64 overflow-y-auto">
              <Table><thead><tr><Th>Día (ART)</Th><Th numeric>{label}</Th></tr></thead><tbody>{daily.map((d) => <tr key={d.day}><Td>{date(d.day)}</Td><Td numeric>{format(d[field])}</Td></tr>)}</tbody></Table>
            </div>
          </details>
        </>
      ) : <p className="py-8 text-sm text-muted-foreground">Sin serie diaria disponible.</p>}
    </div>
  );
}

export function DashboardAttention({ data }: { data: DashboardData }) {
  const state = data.metrics.data?.currentState;
  const failures = data.sources.data?.filter((s) => s.enabled && s.consecutive_failures > 0);
  const unverified = data.sources.data?.filter((s) => s.enabled && s.consecutive_failures === 0 && !s.last_ok_at);
  const pending: { title: string; detail: string; href: string; action: string }[] = [];
  if (failures?.length) pending.push({ title: `${count(failures.length)} ${failures.length === 1 ? "fuente con fallas" : "fuentes con fallas"}`, detail: failures.map((s) => s.name).join(", "), href: "/admin/sources#sources", action: "Revisar fuentes" });
  if (unverified?.length) pending.push({ title: `${count(unverified.length)} fuentes sin corrida correcta registrada`, detail: unverified.map((s) => s.name).join(", "), href: "/admin/sources#sources", action: "Revisar fuentes" });
  if (state?.searchesWithoutValue24h) pending.push({ title: `${count(state.searchesWithoutValue24h)} búsquedas con más de 24 h sin resultados buenos actuales`, detail: "Búsquedas habilitadas sin ningún resultado bueno u oportunidad al consultar. El logro histórico de primer valor se mide por separado.", href: "/admin/searches", action: "Revisar búsquedas" });
  if (state?.failedNotifications) pending.push({ title: `${count(state.failedNotifications)} notificaciones fallidas`, detail: "Revisá el motivo y la configuración de entrega.", href: "/admin/notifications?status=failed", action: "Ver fallas" });
  if (state?.checkoutSyncErrors) pending.push({ title: `${count(state.checkoutSyncErrors)} ${state.checkoutSyncErrors === 1 ? "pago con error" : "pagos con error"} de sincronización`, detail: "Verificá el estado del proveedor antes de intervenir.", href: "/admin/billing", action: "Revisar cobros" });
  return (
    <Section title="Qué necesita atención" description="Estado actual al consultar. Estos pendientes no son una comparación histórica del período.">
      {data.metrics.error || !data.metrics.data ? <DashboardUnavailable title="Pendientes de búsquedas, alertas y cobros sin verificar" error={data.metrics.error} /> : null}
      {data.sources.error || !data.sources.data ? <DashboardUnavailable title="Salud de fuentes sin verificar" error={data.sources.error} /> : null}
      {pending.length ? <ul className="divide-y rounded-xl border bg-card">{pending.map((item) => <li key={item.title} className="flex flex-wrap items-start justify-between gap-3 p-4"><div className="min-w-0 flex-1 basis-48"><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 break-words text-xs text-muted-foreground">{item.detail}</p></div><TextLink href={item.href} className="text-sm">{item.action} →</TextLink></li>)}</ul>
        : state && data.sources.data ? <p className="rounded-xl border bg-card p-4 text-sm">Sin pendientes en estos controles.</p> : null}
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
        <TextLink href="/admin/config#pro_offer">Oferta Particular</TextLink>
        <TextLink href="/admin/config#plan_limits">Límites de planes</TextLink>
        <TextLink href="/admin/config#lifecycle_emails">Emails automáticos</TextLink>
        <TextLink href="/admin/sources#sources">Fuentes</TextLink>
      </div>
    </Section>
  );
}

export function DashboardActivation({ snapshot }: { snapshot: DashboardSnapshot }) {
  const { current: c, previous: p } = snapshot;
  return (
    <>
      <Section title="De la cuenta al primer resultado" description="Cohortes creadas dentro del período y con 24 h al cierre. El primer valor exige seguimiento completo desde la creación de la búsqueda.">
        <p className="rounded-lg border bg-card p-3 text-xs text-muted-foreground">El registro de primer valor comienza el {when(snapshot.firstValueTrackingSince)} ART. Las búsquedas anteriores sin observación completa se excluyen: {count(c.firstValueUnobserved)} en este período y {count(p.firstValueUnobserved)} en el anterior. El score actual no reconstruye un logro histórico.</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <DashboardKpi label="Cuentas nuevas" current={c.signups} previous={p.signups} definition="Altas del período, excluyendo admins." />
          <DashboardKpi label="Activación en 24 h" current={metricRate(c.activatedWithin24h, c.activationEligible)} previous={metricRate(p.activatedWithin24h, p.activationEligible)} rate definition={`${count(c.activatedWithin24h)} de ${count(c.activationEligible)} cuentas observables crearon una búsqueda en 24 h. ${count(c.signups - c.activationEligible)} altas aún fuera del denominador.`} />
          <DashboardKpi label="Primer valor en 24 h" current={metricRate(c.firstValueWithin24h, c.firstValueEligible)} previous={metricRate(p.firstValueWithin24h, p.firstValueEligible)} rate definition={`${count(c.firstValueWithin24h)} de ${count(c.firstValueEligible)} búsquedas observables lograron un resultado bueno u oportunidad en 24 h. ${count(c.firstValueEligible - c.firstValueWithin24h)} sin ese resultado en la ventana.`} />
          <DashboardKpi label="Mediana hasta primer valor" current={c.firstValueMedianHours} previous={p.firstValueMedianHours} hours definition={`Horas, solo entre las ${count(c.firstValueWithin24h)} búsquedas que lograron primer valor dentro de 24 h. Excluye las que no llegaron.`} />
        </div>
      </Section>
      <div className="grid gap-4 lg:grid-cols-2"><DashboardTrend daily={snapshot.daily} field="signups" label="Cuentas nuevas" /><DashboardTrend daily={snapshot.daily} field="searchesCreated" label="Búsquedas creadas" /></div>
      <Section title="Bases de comparación" description="Cada tasa compara su propia cohorte y su propio denominador; no mezcla todas las cuentas históricas.">
        <Table><thead><tr><Th>Etapa</Th><Th numeric>Período</Th><Th numeric>Anterior</Th></tr></thead><tbody>
          <tr><Td>Cuentas con 24 h al cierre</Td><Td numeric>{count(c.activationEligible)}</Td><Td numeric>{count(p.activationEligible)}</Td></tr>
          <tr><Td>Crearon búsqueda en 24 h</Td><Td numeric>{count(c.activatedWithin24h)}</Td><Td numeric>{count(p.activatedWithin24h)}</Td></tr>
          <tr><Td>Búsquedas con seguimiento completo y 24 h al cierre</Td><Td numeric>{count(c.firstValueEligible)}</Td><Td numeric>{count(p.firstValueEligible)}</Td></tr>
          <tr><Td>Búsquedas anteriores sin seguimiento completo (excluidas)</Td><Td numeric>{count(c.firstValueUnobserved)}</Td><Td numeric>{count(p.firstValueUnobserved)}</Td></tr>
          <tr><Td>Primer valor en 24 h</Td><Td numeric>{count(c.firstValueWithin24h)}</Td><Td numeric>{count(p.firstValueWithin24h)}</Td></tr>
          <tr><Td>Sin primer valor dentro de 24 h</Td><Td numeric>{count(c.firstValueEligible - c.firstValueWithin24h)}</Td><Td numeric>{count(p.firstValueEligible - p.firstValueWithin24h)}</Td></tr>
        </tbody></Table>
        <p className="text-xs text-muted-foreground">«Primer valor» = primer match de nivel bueno u oportunidad, incluido el resultado inicial. Una búsqueda puede alcanzar valor después de 24 h y seguir fuera de esta tasa.</p>
        <div className="flex flex-wrap gap-4 text-sm"><TextLink href="/admin/searches">Revisar búsquedas →</TextLink><TextLink href="/admin/config#lifecycle_emails">Revisar emails de activación →</TextLink></div>
      </Section>
    </>
  );
}

export function DashboardRevenue({ snapshot }: { snapshot: DashboardSnapshot }) {
  const { current: c, previous: p, currentState: state } = snapshot;
  return (
    <>
      <Section title="Cobros del período" description="ARS · pagos por fecha de pago y devoluciones por fecha de devolución. Cada movimiento pertenece a su propia fecha.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <DashboardKpi label="Cobros brutos" current={c.grossRevenue} previous={p.grossRevenue} currency definition="Suma de pagos confirmados, antes de devoluciones." />
          <DashboardKpi label="Devoluciones" current={c.refunds} previous={p.refunds} currency definition="Importes devueltos en el período, aunque el pago original sea anterior." />
          <DashboardKpi label="Compras Particular" current={c.particularSales} previous={p.particularSales} definition="Pagos confirmados de Particular. Acceso por 30 días; no es una suscripción." />
          <DashboardKpi label="Pagos de Agencia" current={c.agencyPayments} previous={p.agencyPayments} definition="Mensualidades confirmadas de Agencia. No implica renovación autorizada." />
        </div>
        <DashboardCashNote snapshot={snapshot} />
      </Section>
      <DashboardTrend daily={snapshot.daily} field="grossRevenue" label="Cobros brutos" currency />
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Primer pago" description="Personas cuyo primer pago confirmado ocurrió en el período; excluye admins.">
          <DashboardKpi label="Nuevos clientes pagos" current={c.firstPayingUsers} previous={p.firstPayingUsers} definition="Cuenta personas, no cantidad de transacciones. No atribuye un canal de adquisición." />
        </Section>
        <Section title="Mensualidades vigentes ahora" description="Foto actual al consultar; no está limitada por el período elegido.">
          <div className="space-y-2 rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Equivalente mensual de Agencia</p><p className="type-figure text-3xl">{money(state.agencyMonthlyEquivalent, "ARS")}</p><p className="text-xs leading-relaxed text-muted-foreground">Se calcula sobre accesos de Agencia vigentes. No demuestra suscripciones con renovación autorizada; no se presenta como MRR.</p></div>
        </Section>
      </div>
      <Section title="Qué falta para medir rentabilidad" description="Estas conexiones aún no forman parte de esta vista.">
        <div className="rounded-xl border bg-card p-4 text-sm"><p>Campañas y adquisición (GA4): sin conectar.</p><p className="mt-2">Costos de anuncios, infraestructura y proveedores: sin conectar.</p><p className="mt-3 text-xs text-muted-foreground">Con estos datos no se calculan CAC, margen ni retorno publicitario. Las compras de autos en Diagnóstico son autodeclaradas.</p></div>
        <div className="flex flex-wrap gap-4 text-sm"><TextLink href="/admin/billing">Detalle de cobros →</TextLink><TextLink href="/admin/config#pro_offer">Editar oferta Particular →</TextLink><TextLink href="/admin/config#plan_limits">Editar límites →</TextLink></div>
      </Section>
    </>
  );
}

export function DashboardOperation({ data }: { data: DashboardData }) {
  const snapshot = data.metrics.data;
  return (
    <>
      <DashboardAttention data={data} />
      <Section title="Fuentes: estado actual" description="Últimas 24 h y racha actual de fallas. Este bloque no cambia con el período histórico.">
        {data.sources.error || !data.sources.data ? <DashboardUnavailable title="Fuentes no disponibles" error={data.sources.error} /> : <Table><thead><tr><Th>Fuente</Th><Th>Estado</Th><Th numeric>Corridas 24 h</Th><Th numeric>Fallidas 24 h</Th><Th>Última correcta</Th></tr></thead><tbody>
          {data.sources.data.map((s) => <tr key={s.id}><Td><TextLink href={`/admin/sources?source=${encodeURIComponent(s.id)}#sources`}>{s.name}</TextLink>{s.enabled && s.consecutive_failures > 0 ? <p className="mt-1 max-w-64 break-words text-xs text-muted-foreground">{s.last_error || "Sin detalle del error"}</p> : null}</Td><Td>{!s.enabled ? "Pausada" : s.consecutive_failures > 0 ? `${count(s.consecutive_failures)} fallas seguidas` : s.last_ok_at ? "Sin fallas seguidas" : "Sin corrida correcta registrada"}</Td><Td numeric>{count(s.runs_24h)}</Td><Td numeric>{count(s.failed_24h)}</Td><Td>{when(s.last_ok_at)}</Td></tr>)}
          {!data.sources.data.length ? <EmptyRow colSpan={5}>No hay fuentes registradas.</EmptyRow> : null}
        </tbody></Table>}
      </Section>
      <Section title="Procesamiento asistido" description="Trabajos agrupados por día UTC, proveedor y tarea. Los días UTC pueden solaparse con los bordes del período ART. p50: mediana de duración; p95: el 95% terminó en ese tiempo o menos. No se promedian percentiles entre grupos.">
        {data.llm.error || !data.llm.data ? <DashboardUnavailable title="Estadísticas LLM no disponibles" error={data.llm.error} /> : <Table><thead><tr><Th>Día (UTC)</Th><Th>Proveedor · tarea</Th><Th numeric>Trabajos</Th><Th numeric>Fallidos</Th><Th numeric>Latencia p50</Th><Th numeric>Latencia p95</Th></tr></thead><tbody>
          {data.llm.data.map((j) => <tr key={`${j.day}-${j.provider}-${j.kind}`}><Td>{j.day.slice(0, 10)}</Td><Td>{j.provider}<span className="block text-xs text-muted-foreground">{j.kind}</span></Td><Td numeric>{count(j.jobs)}</Td><Td numeric>{count(j.failed)}<span className="block text-xs text-muted-foreground">{percent(metricRate(j.failed, j.jobs))}</span></Td><Td numeric>{j.latency_p50_ms == null ? "—" : `${(j.latency_p50_ms / 1000).toFixed(1).replace(".", ",")} s`}</Td><Td numeric>{j.latency_p95_ms == null ? "—" : `${(j.latency_p95_ms / 1000).toFixed(1).replace(".", ",")} s`}</Td></tr>)}
          {!data.llm.data.length ? <EmptyRow colSpan={6}>No hubo trabajos en los días consultados.</EmptyRow> : null}
        </tbody></Table>}
      </Section>
      <Section title="Colas actuales" description="Foto actual de búsquedas, notificaciones y cobros. Un pendiente no equivale por sí solo a una falla.">
        {snapshot ? <Table><thead><tr><Th>Control</Th><Th numeric>Ahora</Th><Th>Revisar</Th></tr></thead><tbody>
          <tr><Td>Búsquedas activas</Td><Td numeric>{count(snapshot.currentState.enabledSearches)}</Td><Td><TextLink href="/admin/searches">Búsquedas</TextLink></Td></tr>
          <tr><Td>Notificaciones pendientes</Td><Td numeric>{count(snapshot.currentState.pendingNotifications)}</Td><Td><TextLink href="/admin/notifications">Notificaciones</TextLink></Td></tr>
          <tr><Td>Pagos pendientes</Td><Td numeric>{count(snapshot.currentState.pendingCheckouts)}</Td><Td><TextLink href="/admin/billing">Cobros</TextLink></Td></tr>
        </tbody></Table> : <DashboardUnavailable title="Colas sin verificar" error={data.metrics.error} />}
      </Section>
    </>
  );
}
