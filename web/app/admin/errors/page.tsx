import type { Metadata } from "next";
import Link from "next/link";

import { EmptyRow, PageHeader, Section, Table, Td, Th } from "@/components/admin/ui";
import { count, daysAgo, when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Errores" };

// sección 10, "Errores": pipeline_errors by stage (§46).
export default async function ErrorsPage({ searchParams }: PageProps<"/admin/errors">) {
  const { stage } = await searchParams;
  const filter = typeof stage === "string" && stage ? stage : null;
  const admin = createAdminClient();
  const since = daysAgo(7);
  let list = admin.from("pipeline_errors").select("*").order("id", { ascending: false }).limit(100);
  if (filter) list = list.eq("stage", filter);
  const [{ data: recent }, { data: week }] = await Promise.all([
    list,
    admin.from("pipeline_errors").select("stage, created_at").gte("created_at", since).limit(5000),
  ]);
  const dayAgo = Date.parse(daysAgo(1));
  const stages = new Map<string, { day: number; week: number }>();
  for (const e of week ?? []) {
    const s = stages.get(e.stage) ?? { day: 0, week: 0 };
    s.week += 1;
    if (Date.parse(e.created_at) > dayAgo) s.day += 1;
    stages.set(e.stage, s);
  }

  return (
    <>
      <PageHeader title="Errores" description="pipeline_errors: normalización, ingesta, enrichment, notificaciones." />
      <Section title="Por etapa">
        <Table>
          <thead>
            <tr>
              <Th>Etapa</Th>
              <Th numeric>24 h</Th>
              <Th numeric>7 días</Th>
            </tr>
          </thead>
          <tbody>
            {[...stages].map(([name, s]) => (
              <tr key={name}>
                <Td>
                  <Link href={`/admin/errors?stage=${encodeURIComponent(name)}`} className={cn("hover:underline", filter === name && "font-semibold")}>
                    {name}
                  </Link>
                </Td>
                <Td numeric>{count(s.day)}</Td>
                <Td numeric>{count(s.week)}</Td>
              </tr>
            ))}
            {!stages.size ? <EmptyRow colSpan={3}>Sin errores en los últimos 7 días.</EmptyRow> : null}
          </tbody>
        </Table>
      </Section>
      <Section title={filter ? `Errores de ${filter}` : "Últimos errores"}>
        <Table>
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Etapa</Th>
              <Th>Referencia</Th>
              <Th>Cuándo</Th>
              <Th>Error</Th>
            </tr>
          </thead>
          <tbody>
            {(recent ?? []).map((e) => (
              <tr key={e.id}>
                <Td className="tabular-nums">{e.id}</Td>
                <Td>{e.stage}</Td>
                <Td className="font-mono text-xs">{e.ref ?? "—"}</Td>
                <Td className="whitespace-nowrap">{when(e.created_at)}</Td>
                <Td className="max-w-xl">
                  <details>
                    <summary className="cursor-pointer truncate font-mono text-xs">{e.error.trim().split("\n").pop()}</summary>
                    <pre className="mt-1 max-h-72 overflow-auto rounded bg-muted p-2 text-[11px]">{e.error}</pre>
                  </details>
                </Td>
              </tr>
            ))}
            {!recent?.length ? <EmptyRow colSpan={5} /> : null}
          </tbody>
        </Table>
      </Section>
    </>
  );
}
