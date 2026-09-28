import type { Metadata } from "next";
import Link from "next/link";

import { NotificationTable } from "@/components/admin/inspector";
import { EmptyRow, PageHeader, Section, Table, Td, Th } from "@/components/admin/ui";
import { count, daysAgo } from "@/lib/admin-format";
import { CHANNEL, NOTIFICATION_TITLE } from "@/lib/copy";
import { dayMonth } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";
import { cn } from "@/lib/utils";
import { Constants } from "@/types/database";

export const metadata: Metadata = { title: "Notificaciones" };

const KINDS = Constants.public.Enums.notification_kind;
const CHANNELS = Constants.public.Enums.notification_channel;
const STATUSES = Constants.public.Enums.notification_status;

type Filters = { kind?: string; channel?: string; status?: string };

// sección 10, "Notificaciones": sent, failed, degraded to the digest, clicks —
// and one click from any alert to "¿por qué se envió?".
export default async function NotificationsPage({ searchParams }: PageProps<"/admin/notifications">) {
  const q = await searchParams;
  const pick = <T extends string>(value: unknown, allowed: readonly T[]) =>
    typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
  const filters: Filters = {
    kind: pick(q.kind, KINDS),
    channel: pick(q.channel, CHANNELS),
    status: pick(q.status, STATUSES),
  };

  const admin = createAdminClient();
  let list = admin.from("notifications").select("*").order("id", { ascending: false }).limit(100);
  if (filters.kind) list = list.eq("kind", filters.kind as (typeof KINDS)[number]);
  if (filters.channel) list = list.eq("channel", filters.channel as (typeof CHANNELS)[number]);
  if (filters.status) list = list.eq("status", filters.status as (typeof STATUSES)[number]);
  const since = daysAgo(14, true);
  const [{ data: rows }, { data: daily }] = await Promise.all([
    list,
    admin.from("admin_notification_daily").select("*").gte("day", since).order("day", { ascending: false }),
  ]);
  const ids = [...new Set((rows ?? []).map((n) => n.user_id))];
  const { data: users } = ids.length ? await admin.from("profiles").select("id, email").in("id", ids) : { data: [] };
  const email = new Map((users ?? []).map((u) => [u.id, u.email]));

  const href = (next: Filters) => {
    const qs = new URLSearchParams(Object.entries({ ...filters, ...next }).filter(([, v]) => v) as [string, string][]);
    return `/admin/notifications${qs.size ? `?${qs}` : ""}`;
  };

  return (
    <>
      <PageHeader title="Notificaciones" description="«¿Por qué?» abre el inspector de cada alerta (§45)." />

      <Section title="Por día y canal" description="Últimos 14 días. Degradadas = pasaron el tope diario y fueron al digest.">
        <Table>
          <thead>
            <tr>
              <Th>Día</Th>
              <Th>Canal</Th>
              <Th numeric>Enviadas</Th>
              <Th numeric>Al digest</Th>
              <Th numeric>Degradadas</Th>
              <Th numeric>Digests</Th>
              <Th numeric>Fallidas</Th>
              <Th numeric>En cola</Th>
              <Th numeric>Clics</Th>
            </tr>
          </thead>
          <tbody>
            {(daily ?? []).map((d) => (
              <tr key={`${d.day}-${d.channel}`}>
                <Td>{d.day ? dayMonth(`${d.day}T12:00:00`) : "—"}</Td>
                <Td>{CHANNEL[d.channel ?? ""] ?? d.channel}</Td>
                <Td numeric>{count(d.sent)}</Td>
                <Td numeric>{count(d.to_digest)}</Td>
                <Td numeric>{count(d.degraded)}</Td>
                <Td numeric>{count(d.digests_sent)}</Td>
                <Td numeric className={d.failed ? "text-red-700" : undefined}>
                  {count(d.failed)}
                </Td>
                <Td numeric>{count(d.queued)}</Td>
                <Td numeric>{count(d.clicked)}</Td>
              </tr>
            ))}
            {!daily?.length ? <EmptyRow colSpan={9} /> : null}
          </tbody>
        </Table>
      </Section>

      <Section title="Alertas" description="Las 100 más recientes con estos filtros.">
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
          <FilterGroup label="Tipo" values={KINDS} current={filters.kind} labels={NOTIFICATION_TITLE} href={(v) => href({ kind: v })} />
          <FilterGroup label="Canal" values={CHANNELS} current={filters.channel} labels={CHANNEL} href={(v) => href({ channel: v })} />
          <FilterGroup label="Estado" values={STATUSES} current={filters.status} href={(v) => href({ status: v })} />
        </div>
        <NotificationTable rows={(rows ?? []).map((n) => ({ ...n, email: email.get(n.user_id) ?? null }))} showUser />
      </Section>
    </>
  );
}

function FilterGroup({
  label,
  values,
  current,
  labels,
  href,
}: {
  label: string;
  values: readonly string[];
  current?: string;
  labels?: Record<string, string>;
  href: (value: string | undefined) => string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="text-xs text-muted-foreground">{label}:</span>
      {[undefined, ...values].map((v) => (
        <Link
          key={v ?? "all"}
          href={href(v)}
          aria-current={current === v ? "true" : undefined}
          className={cn(
            "rounded-md px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted",
            current === v && "bg-foreground text-background hover:bg-foreground",
          )}
        >
          {v ? (labels?.[v] ?? v) : "Todos"}
        </Link>
      ))}
    </div>
  );
}
