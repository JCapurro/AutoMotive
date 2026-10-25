import type { Metadata } from "next";

import { EmptyRow, PageHeader, Table, Td, Th } from "@/components/admin/ui";
import { count, when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Modelos pedidos" };

// catalog_misses: what the assisted mode was asked for that vehicle_catalog
// doesn't have (the worker counts it, pipeline/llm_jobs.py). Most asked first:
// the next migration of the catalog starts here.
export default async function CatalogMissesPage() {
  const { data: misses } = await createAdminClient()
    .from("catalog_misses")
    .select("*")
    .order("count", { ascending: false })
    .order("last_seen_at", { ascending: false })
    .limit(500);

  return (
    <>
      <PageHeader
        title="Modelos pedidos que no tenemos"
        description="Lo que se pidió en el modo asistido y no está en vehicle_catalog, por texto normalizado."
      />
      <Table>
        <thead>
          <tr>
            <Th>Pedido</Th>
            <Th>Marca del catálogo</Th>
            <Th numeric>Veces</Th>
            <Th>Primera vez</Th>
            <Th>Última vez</Th>
            <Th numeric>Último job</Th>
          </tr>
        </thead>
        <tbody>
          {(misses ?? []).map((m) => (
            <tr key={m.said}>
              <Td className="font-medium">{m.said}</Td>
              <Td>{m.make ?? "—"}</Td>
              <Td numeric>{count(m.count)}</Td>
              <Td className="whitespace-nowrap">{when(m.first_seen_at)}</Td>
              <Td className="whitespace-nowrap">{when(m.last_seen_at)}</Td>
              <Td numeric>{m.last_llm_job_id ?? "—"}</Td>
            </tr>
          ))}
          {!misses?.length ? <EmptyRow colSpan={6}>Nadie pidió un modelo que no tengamos.</EmptyRow> : null}
        </tbody>
      </Table>
    </>
  );
}
