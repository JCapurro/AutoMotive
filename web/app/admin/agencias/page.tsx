import type { Metadata } from "next";

import { DealerActions, SourceDecision } from "@/components/admin/dealer-admin";
import { EmptyRow, PageHeader, Pill, Section, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { when } from "@/lib/admin-format";
import { webConfig } from "@/lib/config";
import { channelOn } from "@/lib/dealer-program";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Agencias" };

type Counts = Record<string, number>;

function tally(rows: { dealer_id: number; status: string }[] | null): Map<number, Counts> {
  const out = new Map<number, Counts>();
  for (const r of rows ?? []) {
    const c = out.get(r.dealer_id) ?? {};
    c[r.status] = (c[r.status] ?? 0) + 1;
    out.set(r.dealer_id, c);
  }
  return out;
}

const line = (c: Counts | undefined, labels: Record<string, string>) =>
  Object.entries(labels).map(([k, label]) => `${c?.[k] ?? 0} ${label}`).join(" · ");

/**
 * Agencias (spec §6.1): who signed up, approval and pause, items and leads by
 * status (counts only: no buyer data here), and the sources waiting for the
 * seller account to be chosen.
 */
export default async function DealersAdminPage() {
  await requireAdmin();
  const admin = createAdminClient();
  const [{ data: dealers }, { data: items }, { data: leads }, { data: sources }, { dealerProgram }] = await Promise.all([
    admin.from("dealers").select("id, name, locality_label, status, approved_at, created_at, contact_email").order("created_at", { ascending: false }),
    admin.from("dealer_stock_items").select("dealer_id, status").limit(20000),
    admin.from("dealer_leads").select("dealer_id, status").limit(20000),
    admin.from("dealer_sources").select("id, dealer_id, source, profile_url, seller_name_hint, seller_key, status, created_at").order("created_at"),
    webConfig(),
  ]);
  const itemCounts = tally(items);
  const leadCounts = tally(leads);
  const names = new Map((dealers ?? []).map((d) => [d.id, d.name]));
  const pending = (sources ?? []).filter((s) => s.status === "pending");
  const candidates = await Promise.all(
    pending.map((s) =>
      s.seller_name_hint
        ? admin.rpc("admin_dealer_seller_candidates", { p_source: s.source, p_hint: s.seller_name_hint }).then(({ data }) => data ?? [])
        : Promise.resolve([]),
    ),
  );

  return (
    <>
      <PageHeader
        title="Agencias"
        description={`Panel ${dealerProgram.enabled ? "prendido" : "apagado"} · canal de venta ${channelOn(dealerProgram) ? "prendido" : "apagado"} (app_config.dealer_program). Aprobar prende la demanda y, con el canal, el envío a compradores.`}
      >
        <TextLink href="/admin/agencias/embudo">Ver el embudo del canal</TextLink>
      </PageHeader>
      <Section title="Agencias" description="Ítems y consultas por estado: solo conteos.">
        <Table>
          <thead>
            <tr><Th>Agencia</Th><Th>Alta</Th><Th>Estado</Th><Th>Stock</Th><Th>Consultas</Th><Th /></tr>
          </thead>
          <tbody>
            {(dealers ?? []).length === 0 ? <EmptyRow colSpan={6}>Todavía no se dio de alta ninguna agencia.</EmptyRow> : null}
            {(dealers ?? []).map((d) => (
              <tr key={d.id}>
                <Td>
                  <b className="font-semibold">{d.name}</b>
                  <span className="block text-xs text-muted-foreground">{d.locality_label}</span>
                </Td>
                <Td>{when(d.created_at)}</Td>
                <Td>
                  {d.status === "paused" ? <Pill tone="warn">Pausada</Pill> : d.approved_at ? <Pill tone="ok">Aprobada</Pill> : <Pill>Sin aprobar</Pill>}
                </Td>
                <Td className="text-xs">{line(itemCounts.get(d.id), { available: "disp.", reserved: "res.", sold: "vend.", archived: "fuera" })}</Td>
                <Td className="text-xs">{line(leadCounts.get(d.id), { new: "nuevas", contacted: "contact.", reserved: "res.", sold: "vend.", lost: "perd." })}</Td>
                <Td><DealerActions id={d.id} approved={d.approved_at != null} paused={d.status === "paused"} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>
      <Section title="Fuentes para sincronizar" description="La agencia pegó su link y cómo figura su nombre. Elegí la cuenta del vendedor que es suya: el worker enlaza sus avisos activos.">
        <Table>
          <thead>
            <tr><Th>Agencia</Th><Th>Fuente</Th><Th>Lo que pegó</Th><Th>Cuenta</Th></tr>
          </thead>
          <tbody>
            {pending.length === 0 ? <EmptyRow colSpan={4}>No hay fuentes pendientes.</EmptyRow> : null}
            {pending.map((s, i) => (
              <tr key={s.id}>
                <Td>{names.get(s.dealer_id) ?? s.dealer_id}</Td>
                <Td>{s.source}</Td>
                <Td className="max-w-80 text-xs break-all">
                  {s.seller_name_hint ? <b className="block">{s.seller_name_hint}</b> : null}
                  {s.profile_url ? <a href={s.profile_url} target="_blank" rel="noreferrer" className="underline">{s.profile_url}</a> : null}
                </Td>
                <Td><SourceDecision id={s.id} candidates={candidates[i]} suggested={s.seller_key} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>
    </>
  );
}
