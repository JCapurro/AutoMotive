import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Card } from "@/components/admin/dash";
import { EmptyRow, Json, PageHeader, Pill, Stat, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { channelOf, CHANNEL_LABEL, landingKind, parseOrigin } from "@/lib/acquisition";
import { count, filterSummary, when } from "@/lib/admin-format";
import { requireAdmin } from "@/lib/admin";
import { SYSTEM_EVENTS } from "@/lib/admin-users-data";
import { EVENT_LABEL } from "@/lib/admin-event-labels";
import { money } from "@/lib/format";
import { PLAN_NAMES } from "@/lib/pro";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Usuario" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// sección 10, "Usuarios": one account, where it came from and everything it did.
export default async function AdminUserPage({ params }: PageProps<"/admin/users/[id]">) {
  await requireAdmin();
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  const db = createAdminClient();
  const [{ data: user }, { data: events }, { data: searches }, { data: notes }, { data: payments }] = await Promise.all([
    db.from("admin_users").select("*").eq("id", id).maybeSingle(),
    db.from("events").select("id,name,props,created_at").eq("user_id", id).order("created_at", { ascending: false }).limit(400),
    db.from("admin_searches").select("*").eq("user_id", id).order("created_at", { ascending: false }),
    db.from("notifications").select("search_profile_id,kind,channel,sent_at,opened_at,clicked_at").eq("user_id", id).eq("status", "sent"),
    db.from("commercial_payments").select("offer,amount,currency,paid_at,refunded_at").eq("user_id", id).order("paid_at", { ascending: false }),
  ]);
  if (!user) notFound();

  const signup = (events ?? []).findLast((e) => e.name === "signup_completed");
  const props = (signup?.props ?? {}) as Record<string, unknown>;
  const origin = parseOrigin(props.origin);
  const channel = origin ? channelOf(origin) : "unknown";
  const all = notes ?? [];
  const bySearch = new Map<number, { sent: number; clicked: number }>();
  for (const n of all) {
    if (n.search_profile_id == null) continue;
    const s = bySearch.get(n.search_profile_id) ?? { sent: 0, clicked: 0 };
    s.sent += 1;
    if (n.clicked_at) s.clicked += 1;
    bySearch.set(n.search_profile_id, s);
  }
  const own = (events ?? []).filter((e) => !SYSTEM_EVENTS.has(e.name) && e.name !== "alert_sent" && e.name !== "lifecycle_email_sent");
  const activeDays = new Set(own.map((e) => e.created_at.slice(0, 10))).size;

  return (
    <>
      <PageHeader title={user.email ?? "Solo Telegram"} description={`Registro ${when(user.created_at)} · ${user.plan ? PLAN_NAMES[user.plan] : "—"}`}>
        <TextLink href="/admin/users" className="text-sm">← Usuarios</TextLink>
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Canal" value={<span className="text-lg">{CHANNEL_LABEL[channel]}</span>} />
        <Stat label="Búsquedas" value={`${count(user.enabled_searches)} / ${count(user.searches)}`} note="activas / total" />
        <Stat label="Alertas recibidas" value={count(all.length)} />
        <Stat label="Abiertas" value={count(all.filter((n) => n.opened_at || n.clicked_at).length)} />
        <Stat label="Con clic" value={count(all.filter((n) => n.clicked_at).length)} />
        <Stat label="Días activo" value={count(activeDays)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Origen" description="Primer contacto guardado al registrarse.">
          {origin ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Primera página</dt>
              <dd>{landingKind(origin.landing)} <span className="text-xs text-muted-foreground">{origin.landing}</span></dd>
              <dt className="text-muted-foreground">Vino de</dt>
              <dd>{origin.referrer ?? "—"}</dd>
              <dt className="text-muted-foreground">UTM</dt>
              <dd>{[origin.source, origin.medium, origin.campaign, origin.content].filter(Boolean).join(" / ") || "—"}</dd>
              <dt className="text-muted-foreground">Clic de anuncio</dt>
              <dd>{origin.click ?? "—"}</dd>
              <dt className="text-muted-foreground">Primera visita</dt>
              <dd>{when(origin.at)}</dd>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">Sin dato: la cuenta es anterior a la medición o rechazó el seguimiento.</p>
          )}
          <p className="text-xs text-muted-foreground">Registro por: {typeof props.method === "string" ? props.method : "—"}</p>
        </Card>

        <Card title="Pagos">
          {payments?.length ? (
            <ul className="space-y-1 text-sm">
              {payments.map((p, i) => (
                <li key={i}>
                  {p.offer} · {money(Number(p.amount), p.currency)} · {when(p.paid_at)} {p.refunded_at ? <Pill tone="bad">devuelto</Pill> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No pagó.</p>
          )}
        </Card>
      </div>

      <Card title="Búsquedas">
        <Table>
          <thead>
            <tr>
              <Th>Búsqueda</Th>
              <Th numeric>Matches</Th>
              <Th numeric>🔥</Th>
              <Th numeric>Alertas</Th>
              <Th numeric>Clics</Th>
              <Th>Creada</Th>
            </tr>
          </thead>
          <tbody>
            {(searches ?? []).map((s) => (
              <tr key={s.id}>
                <Td className="max-w-80">
                  <TextLink href={`/admin/searches#search-${s.id}`}>{s.name}</TextLink> {!s.enabled ? <Pill>pausada</Pill> : null}
                  <span className="block text-xs text-muted-foreground">{filterSummary(s.filters)}</span>
                </Td>
                <Td numeric>{count(s.matches)}</Td>
                <Td numeric>{count(s.high_matches)}</Td>
                <Td numeric>{count(bySearch.get(s.id!)?.sent ?? 0)}</Td>
                <Td numeric>{count(bySearch.get(s.id!)?.clicked ?? 0)}</Td>
                <Td className="whitespace-nowrap">{when(s.created_at)}</Td>
              </tr>
            ))}
            {!searches?.length ? <EmptyRow colSpan={6}>No creó búsquedas.</EmptyRow> : null}
          </tbody>
        </Table>
      </Card>

      <Card title="Línea de tiempo" description={`Los últimos ${count(events?.length ?? 0)} eventos, del más nuevo al más viejo. Los marcados «sistema» no los hizo el usuario.`}>
        <ol className="divide-y text-sm">
          {(events ?? []).map((e) => {
            const system = SYSTEM_EVENTS.has(e.name) || e.name === "alert_sent" || e.name === "lifecycle_email_sent";
            const p = e.props && typeof e.props === "object" && Object.keys(e.props).length ? e.props : null;
            return (
              <li key={e.id} className={system ? "py-1.5 text-muted-foreground" : "py-1.5"}>
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="w-32 shrink-0 text-xs tabular-nums text-muted-foreground">{when(e.created_at)}</span>
                  <span className={system ? "" : "font-medium"}>{EVENT_LABEL[e.name] ?? e.name}</span>
                  {system ? <Pill>sistema</Pill> : null}
                </div>
                {p ? (
                  <details className="ml-35 text-xs">
                    <summary className="cursor-pointer text-muted-foreground">datos</summary>
                    <Json value={p} className="mt-1" />
                  </details>
                ) : null}
              </li>
            );
          })}
          {!events?.length ? <li className="py-2 text-muted-foreground">Sin eventos.</li> : null}
        </ol>
      </Card>
    </>
  );
}
