import type { Metadata } from "next";

import { SourceHealthTable } from "@/components/admin/sources";
import { EmptyRow, PageHeader, Pill, Section, Table, Td, Th } from "@/components/admin/ui";
import { count, when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Fuentes" };

// sección 10, "Fuentes / collectors": collector_runs, failure streaks and the cadence.
export default async function SourcesPage({ searchParams }: PageProps<"/admin/sources">) {
  const { source } = await searchParams;
  const filter = typeof source === "string" && source ? source : null;
  const admin = createAdminClient();
  let runsQuery = admin.from("collector_runs").select("*").order("started_at", { ascending: false }).limit(100);
  if (filter) runsQuery = runsQuery.eq("source", filter);
  const [{ data: health }, { data: runs }, { data: cfg }, { data: beat }] = await Promise.all([
    admin.from("admin_source_health").select("*").order("priority"),
    runsQuery,
    admin.from("app_config").select("value").eq("key", "collector_failure_alert_after").maybeSingle(),
    admin.from("worker_heartbeat").select("started_at, beat_at, host").maybeSingle(),
  ]);
  const alertAfter = Number(cfg?.value ?? 3);

  return (
    <>
      <PageHeader
        title="Fuentes"
        description={`Con ${alertAfter} fallas seguidas el worker avisa por Telegram (TELEGRAM_ADMIN_CHAT_ID). La cadencia se aplica en el próximo tick.`}
      />
      <WorkerStatus beat={beat} />
      <SourceHealthTable rows={health ?? []} editable alertAfter={alertAfter} />

      <Section title={filter ? `Corridas de ${filter}` : "Últimas corridas"} description="collector_runs, las 100 más recientes.">
        <Table>
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Fuente</Th>
              <Th>Target</Th>
              <Th>Inicio</Th>
              <Th numeric>Duración</Th>
              <Th>Estado</Th>
              <Th numeric>Encontrados</Th>
              <Th numeric>Nuevos</Th>
              <Th numeric>Actualizados</Th>
              <Th>Error</Th>
            </tr>
          </thead>
          <tbody>
            {(runs ?? []).map((r) => (
              <tr key={r.id}>
                <Td className="tabular-nums">{r.id}</Td>
                <Td>{r.source}</Td>
                <Td className="tabular-nums">{r.target_id ?? "—"}</Td>
                <Td className="whitespace-nowrap">{when(r.started_at)}</Td>
                <Td numeric>
                  {r.finished_at ? `${Math.round((Date.parse(r.finished_at) - Date.parse(r.started_at)) / 1000)} s` : "—"}
                </Td>
                <Td>
                  <Pill tone={r.status === "ok" ? "ok" : r.status === "failed" ? "bad" : "warn"}>{r.status}</Pill>
                </Td>
                <Td numeric>{count(r.found)}</Td>
                <Td numeric>{count(r.new)}</Td>
                <Td numeric>{count(r.updated)}</Td>
                <Td className="max-w-72">
                  {r.error ? (
                    <details>
                      <summary className="cursor-pointer truncate font-mono text-xs">{r.error.trim().split("\n").pop()}</summary>
                      <pre className="mt-1 max-h-60 overflow-auto rounded bg-muted p-2 text-[11px]">{r.error}</pre>
                    </details>
                  ) : (
                    "—"
                  )}
                </Td>
              </tr>
            ))}
            {!runs?.length ? <EmptyRow colSpan={10} /> : null}
          </tbody>
        </Table>
      </Section>
    </>
  );
}

/** F7, punto 8: the worker's heartbeat (worker_heartbeat, every minute). */
function WorkerStatus({ beat }: { beat: { started_at: string; beat_at: string; host: string | null } | null }) {
  // eslint-disable-next-line react-hooks/purity -- a server render: "now" is the request time
  const minutes = beat ? Math.floor((Date.now() - new Date(beat.beat_at).getTime()) / 60_000) : null;
  const tone = minutes == null || minutes >= 10 ? "bad" : minutes >= 3 ? "warn" : "ok";
  return (
    <p className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      <span>Worker:</span>
      <Pill tone={tone}>
        {minutes == null ? "nunca latió" : minutes < 1 ? "late ahora" : `último latido hace ${minutes} min`}
      </Pill>
      {beat ? (
        <span>
          {beat.host ?? "—"} · arrancó {when(beat.started_at)}
        </span>
      ) : null}
    </p>
  );
}
