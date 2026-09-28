import type { Metadata } from "next";

import { EmptyRow, PageHeader, Pill, Table, Td, Th } from "@/components/admin/ui";
import { count, isPast, when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Usuarios" };

const WAITLIST: Record<string, string> = { pro_monthly: "Pro mensual", pass_30: "Pass 30 días", pass_90: "Pass 90 días" };

// sección 10, "Usuarios": plan, searches, alerts per day, last activity.
export default async function UsersPage() {
  const { data: users } = await createAdminClient()
    .from("admin_users")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(500);

  return (
    <>
      <PageHeader title="Usuarios" description={`${count(users?.length ?? 0)} cuentas. Alertas/día: promedio de los últimos 7 días.`} />
      <Table>
        <thead>
          <tr>
            <Th>Usuario</Th>
            <Th>Plan</Th>
            <Th>Lista de espera</Th>
            <Th numeric>Búsquedas</Th>
            <Th numeric>Alertas/día</Th>
            <Th>Telegram</Th>
            <Th>Registro</Th>
            <Th>Última actividad</Th>
          </tr>
        </thead>
        <tbody>
          {(users ?? []).map((u) => {
            const expired = u.plan !== "free" && isPast(u.plan_expires_at);
            return (
              <tr key={u.id}>
                <Td className="max-w-56">
                  <span className="block truncate">{u.email ?? "Solo Telegram"}</span>
                  {u.role === "admin" ? <Pill tone="warn">admin</Pill> : null}
                </Td>
                <Td className="whitespace-nowrap">
                  {u.plan}
                  {u.plan_expires_at ? (
                    <span className="block text-xs text-muted-foreground">
                      {expired ? "venció" : "vence"} {when(u.plan_expires_at)}
                    </span>
                  ) : null}
                </Td>
                <Td>{u.waitlist_plan ? <Pill tone="ok">{WAITLIST[u.waitlist_plan] ?? u.waitlist_plan}</Pill> : "—"}</Td>
                <Td numeric>
                  {count(u.enabled_searches)} / {count(u.searches)}
                </Td>
                <Td numeric>{((u.alerts_7d ?? 0) / 7).toFixed(1).replace(".", ",")}</Td>
                <Td>{u.telegram_linked ? "Vinculado" : "—"}</Td>
                <Td className="whitespace-nowrap">{when(u.created_at)}</Td>
                <Td className="whitespace-nowrap">{when(u.last_activity_at)}</Td>
              </tr>
            );
          })}
          {!users?.length ? <EmptyRow colSpan={8} /> : null}
        </tbody>
      </Table>
    </>
  );
}
