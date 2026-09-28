import type { Metadata } from "next";

import { EmptyRow, PageHeader, Pill, Table, Td, Th } from "@/components/admin/ui";
import { count, filterSummary, when } from "@/lib/admin-format";
import { CHANNEL, LEVEL } from "@/lib/copy";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Búsquedas" };

// sección 10, "Búsquedas": filters, matches and alerts, bootstrap state.
export default async function SearchesPage() {
  const { data: searches } = await createAdminClient()
    .from("admin_searches")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(500);

  return (
    <>
      <PageHeader title="Búsquedas" description={`${count(searches?.length ?? 0)} Search Profiles.`} />
      <Table>
        <thead>
          <tr>
            <Th>#</Th>
            <Th>Búsqueda</Th>
            <Th>Usuario</Th>
            <Th>Alertas</Th>
            <Th numeric>Matches</Th>
            <Th numeric>🔥</Th>
            <Th numeric>Alertas enviadas</Th>
            <Th>Bootstrap</Th>
            <Th>Creada</Th>
          </tr>
        </thead>
        <tbody>
          {(searches ?? []).map((s) => (
            <tr key={s.id}>
              <Td className="tabular-nums">{s.id}</Td>
              <Td className="max-w-72">
                <span className="block font-medium">
                  {s.name} {!s.enabled ? <Pill>pausada</Pill> : null}
                </span>
                <span className="text-xs text-muted-foreground">{filterSummary(s.filters)}</span>
              </Td>
              <Td className="max-w-48 truncate">{s.email ?? "Solo Telegram"}</Td>
              <Td className="text-xs whitespace-nowrap">
                {s.notification_frequency === "immediate" ? "Inmediata" : "Diaria"} · ≥ {s.notify_min_level ? LEVEL[s.notify_min_level].emoji : ""}
                <span className="block text-muted-foreground">{(s.channels ?? []).map((c) => CHANNEL[c] ?? c).join(", ")}</span>
              </Td>
              <Td numeric>{count(s.matches)}</Td>
              <Td numeric>{count(s.high_matches)}</Td>
              <Td numeric>{count(s.alerts)}</Td>
              <Td className="whitespace-nowrap">
                {s.rematch_requested_at ? <Pill tone="warn">re-match pendiente</Pill> : s.bootstrapped_at ? when(s.bootstrapped_at) : <Pill tone="warn">pendiente</Pill>}
              </Td>
              <Td className="whitespace-nowrap">{when(s.created_at)}</Td>
            </tr>
          ))}
          {!searches?.length ? <EmptyRow colSpan={9} /> : null}
        </tbody>
      </Table>
    </>
  );
}
