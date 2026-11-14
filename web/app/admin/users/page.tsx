import type { Metadata } from "next";

import { BarList, Card, HeatCell, LinkTabs, rate, withParams } from "@/components/admin/dash";
import { EmptyRow, PageHeader, Pill, Stat, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { type Channel, CHANNEL_LABEL, landingKind } from "@/lib/acquisition";
import { count, isPast, when } from "@/lib/admin-format";
import { loadUsersInput } from "@/lib/admin-load";
import { buildUsersDashboard, PERIODS, periodDays } from "@/lib/admin-users-data";
import { money } from "@/lib/format";
import { PLAN_NAMES } from "@/lib/pro";

export const metadata: Metadata = { title: "Usuarios" };

const WAITLIST: Record<string, string> = { pro_monthly: "Pro", pass_30: "Particular", pass_7: "Particular 7 días", pass_90: "Pase anterior 90 días" };
const TABLE_LIMIT = 300;

// sección 10, "Usuarios": where they come from, what they did, and each account.
export default async function UsersPage({ searchParams }: PageProps<"/admin/users">) {
  const params = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const current = { periodo: one(params.periodo), canal: one(params.canal) };
  const days = periodDays(current.periodo);
  const periodKey = PERIODS.find((p) => p.days === days)!.key;
  const d = buildUsersDashboard(await loadUsersInput(), new Date(), days);
  const { kpis } = d;
  const channel = current.canal && current.canal in CHANNEL_LABEL ? (current.canal as Channel) : null;
  const listed = d.inPeriod.filter((u) => !channel || u.channel === channel).sort((a, b) => b.created_at.localeCompare(a.created_at));
  const periodText = days ? `los últimos ${days} días` : "todo el historial";
  const delta = kpis.prevSignups != null ? kpis.signups - kpis.prevSignups : null;

  return (
    <>
      <PageHeader title="Usuarios" description={`${count(d.users.length)} cuentas en total. Los números de abajo miran a quienes se registraron en ${periodText}.`}>
        <LinkTabs
          label="Período"
          current={periodKey}
          items={PERIODS.map((p) => ({ key: p.key, label: p.label, href: withParams("/admin/users", current, { periodo: p.key === "30" ? null : p.key }) }))}
        />
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Registros" value={count(kpis.signups)} note={delta != null ? `${delta >= 0 ? "+" : ""}${delta} vs. período anterior` : undefined} />
        <Stat label="Crearon búsqueda" value={`${kpis.searchedPct}%`} />
        <Stat label="Miraron un auto" value={`${kpis.engagedPct}%`} note="Clic en alerta, ficha o aviso" />
        <Stat label="Pagaron" value={rate(kpis.paid, kpis.signups)} note={`${count(kpis.paid)} cuentas`} />
        <Stat label="Activos 7 días" value={count(kpis.active7d)} note="De todas las cuentas" />
        <Stat label="Con origen" value={count(kpis.withOrigin)} note="Primer contacto medido" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Embudo" description="Cada paso cuenta a quien llegó alguna vez, entre los registrados del período.">
          <BarList rows={d.funnel.map((s) => ({ label: s.label, value: s.users }))} total={d.funnel[0].users} />
        </Card>

        <Card title="De dónde vienen" description="Canal del primer contacto. «Sin dato»: cuentas anteriores a la medición o que rechazaron el seguimiento.">
          <BarList
            rows={d.channels.map((c) => ({ key: c.channel, label: CHANNEL_LABEL[c.channel], value: c.users }))}
            total={kpis.signups}
            href={(key) => withParams("/admin/users", current, { canal: key === current.canal ? null : key })}
          />
        </Card>
      </div>

      <Card title="Qué hizo cada canal" description="Sobre los registrados del período de cada canal.">
        <Table>
          <thead>
            <tr>
              <Th>Canal</Th>
              <Th numeric>Usuarios</Th>
              <Th numeric>Crearon búsqueda</Th>
              <Th numeric>Miraron un auto</Th>
              <Th numeric>Pagaron</Th>
              <Th numeric>Cobrado</Th>
            </tr>
          </thead>
          <tbody>
            {d.channels.map((c) => (
              <tr key={c.channel}>
                <Td>
                  <TextLink href={withParams("/admin/users", current, { canal: c.channel })}>{CHANNEL_LABEL[c.channel]}</TextLink>
                </Td>
                <Td numeric>{count(c.users)}</Td>
                <Td numeric>{rate(c.searched, c.users)}</Td>
                <Td numeric>{rate(c.engaged, c.users)}</Td>
                <Td numeric>{c.paid ? `${c.paid} (${rate(c.paid, c.users)})` : "—"}</Td>
                <Td numeric>{c.revenue ? money(c.revenue, "ARS") : "—"}</Td>
              </tr>
            ))}
            {!d.channels.length ? <EmptyRow colSpan={6} /> : null}
          </tbody>
        </Table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Cómo se registraron">
          <BarList rows={d.methods.map((m) => ({ label: m.label, value: m.users }))} total={kpis.signups} />
        </Card>
        <Card title="Primera página" description="Solo cuentas con origen medido.">
          <BarList rows={d.landings.map((m) => ({ label: m.label, value: m.users }))} empty="Todavía no hay registros con origen." />
        </Card>
        <Card title="Campañas (UTM)" description="Fuente / medio / campaña.">
          <BarList rows={d.campaigns.slice(0, 10).map((m) => ({ label: m.label, value: m.users }))} empty="Ningún registro llegó con UTM todavía." />
        </Card>
      </div>

      <Card title="Retención por semana de registro" description="Qué parte de cada camada hizo algo en la app 1, 2, 3 y 4 semanas después de registrarse. «…»: esa semana todavía no terminó.">
        <Table>
          <thead>
            <tr>
              <Th>Semana del</Th>
              <Th numeric>Registros</Th>
              <Th className="text-center">Sem. 1</Th>
              <Th className="text-center">Sem. 2</Th>
              <Th className="text-center">Sem. 3</Th>
              <Th className="text-center">Sem. 4</Th>
            </tr>
          </thead>
          <tbody>
            {d.cohorts.map((c) => (
              <tr key={c.week}>
                <Td className="whitespace-nowrap">{c.week.split("-").reverse().join("/")}</Td>
                <Td numeric>{count(c.users)}</Td>
                {c.retention.map((r, i) => (
                  <HeatCell key={i} value={r} />
                ))}
              </tr>
            ))}
            {!d.cohorts.length ? <EmptyRow colSpan={6} /> : null}
          </tbody>
        </Table>
      </Card>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold tracking-tight">
            Cuentas {channel ? <>· {CHANNEL_LABEL[channel]}</> : null}{" "}
            <span className="text-sm font-normal text-muted-foreground">
              {count(listed.length)}
              {listed.length > TABLE_LIMIT ? `, se muestran las ${TABLE_LIMIT} más nuevas` : ""}
            </span>
          </h2>
          {channel ? <TextLink href={withParams("/admin/users", current, { canal: null })} className="text-sm">Ver todos los canales</TextLink> : null}
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Usuario</Th>
              <Th>Origen</Th>
              <Th>Plan</Th>
              <Th numeric>Búsquedas</Th>
              <Th numeric>Alertas</Th>
              <Th numeric>Abiertas</Th>
              <Th numeric>Clics</Th>
              <Th numeric>Fichas</Th>
              <Th numeric>Días activo</Th>
              <Th>Registro</Th>
              <Th>Última actividad</Th>
            </tr>
          </thead>
          <tbody>
            {listed.slice(0, TABLE_LIMIT).map((u) => {
              const expired = u.plan !== "free" && isPast(u.plan_expires_at);
              return (
                <tr key={u.id}>
                  <Td className="max-w-56">
                    <TextLink href={`/admin/users/${u.id}`} className="block truncate">{u.email ?? "Solo Telegram"}</TextLink>
                    {u.role === "admin" ? <Pill tone="warn">admin</Pill> : null}
                    {u.paid ? <Pill tone="ok">pagó</Pill> : null}
                    {u.telegram_linked ? <Pill>Telegram</Pill> : null}
                  </Td>
                  <Td className="text-xs whitespace-nowrap">
                    {CHANNEL_LABEL[u.channel]}
                    {u.origin ? <span className="block text-muted-foreground">{[landingKind(u.origin.landing), u.origin.campaign ?? u.origin.referrer].filter(Boolean).join(" · ")}</span> : null}
                  </Td>
                  <Td className="whitespace-nowrap">
                    {u.plan ? PLAN_NAMES[u.plan as keyof typeof PLAN_NAMES] : "—"}
                    {u.plan_expires_at ? (
                      <span className="block text-xs text-muted-foreground">
                        {expired ? "venció" : "vence"} {when(u.plan_expires_at)}
                      </span>
                    ) : null}
                    {u.waitlist_plan ? <span className="block text-xs text-muted-foreground">espera {WAITLIST[u.waitlist_plan] ?? u.waitlist_plan}</span> : null}
                  </Td>
                  <Td numeric>{count(u.enabled_searches)} / {count(u.searches)}</Td>
                  <Td numeric>{count(u.alerts)}</Td>
                  <Td numeric>{u.alerts ? rate(u.alertsOpened, u.alerts) : "—"}</Td>
                  <Td numeric>{count(u.alertsClicked)}</Td>
                  <Td numeric>{count(u.detailViews)}</Td>
                  <Td numeric>{count(u.activeDays)}</Td>
                  <Td className="whitespace-nowrap">{when(u.created_at)}</Td>
                  <Td className="whitespace-nowrap">{when(u.lastActivityAt)}</Td>
                </tr>
              );
            })}
            {!listed.length ? <EmptyRow colSpan={11} /> : null}
          </tbody>
        </Table>
      </section>
    </>
  );
}
