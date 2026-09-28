import type { Metadata } from "next";

import { EmptyRow, PageHeader, Pill, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { when } from "@/lib/admin-format";
import { money, number, vehicle } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Listings" };

function escapeLike(value: string): string {
  return value.replace(/[\\%_,()]/g, (c) => `\\${c}`);
}

// sección 10, "Listings": search by source, id or model.
export default async function ListingsPage({ searchParams }: PageProps<"/admin/listings">) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q.trim().slice(0, 80) : "";
  const source = typeof params.source === "string" ? params.source : "";
  const admin = createAdminClient();

  let query = admin
    .from("listings")
    .select("id, source, external_id, title, make, model, trim, year, price, currency, mileage_km, status, first_seen_at, probable_repost_of")
    .order("first_seen_at", { ascending: false })
    .limit(100);
  if (source) query = query.eq("source", source);
  if (/^\d+$/.test(q)) {
    query = query.or(`id.eq.${q},external_id.eq.${q}`);
  } else if (q) {
    const like = `%${escapeLike(q)}%`;
    query = query.or(`title.ilike.${like},model.ilike.${like},make.ilike.${like},external_id.ilike.${like}`);
  }
  const [{ data: listings }, { data: sources }] = await Promise.all([query, admin.from("sources").select("id, name").order("priority")]);

  return (
    <>
      <PageHeader title="Listings" description="Por id (nuestro o de la fuente), modelo o título." />
      <form className="flex flex-wrap items-center gap-2" action="/admin/listings">
        <Input name="q" defaultValue={q} placeholder="4837, MLA123…, Fiesta" aria-label="Buscar" className="h-8 w-64" />
        <NativeSelect name="source" defaultValue={source} aria-label="Fuente">
          <option value="">Todas las fuentes</option>
          {(sources ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </NativeSelect>
        <Button type="submit" size="sm">
          Buscar
        </Button>
      </form>
      <Table>
        <thead>
          <tr>
            <Th>#</Th>
            <Th>Publicación</Th>
            <Th>Fuente</Th>
            <Th numeric>Precio</Th>
            <Th numeric>Km</Th>
            <Th>Estado</Th>
            <Th>Detectada</Th>
          </tr>
        </thead>
        <tbody>
          {(listings ?? []).map((l) => (
            <tr key={l.id}>
              <Td className="tabular-nums">
                <TextLink href={`/admin/listings/${l.id}`}>{l.id}</TextLink>
              </Td>
              <Td className="max-w-80">
                <span className="line-clamp-1">{vehicle(l)}</span>
                <span className="line-clamp-1 text-xs text-muted-foreground">{l.title}</span>
              </Td>
              <Td className="whitespace-nowrap">
                {l.source}
                <span className="block font-mono text-xs text-muted-foreground">{l.external_id}</span>
              </Td>
              <Td numeric className="whitespace-nowrap">
                {money(l.price, l.currency)}
              </Td>
              <Td numeric>{number(l.mileage_km)}</Td>
              <Td>
                <Pill tone={l.status === "active" ? "ok" : "muted"}>{l.status}</Pill>
                {l.probable_repost_of ? <span className="ml-1 text-xs text-muted-foreground">🔁</span> : null}
              </Td>
              <Td className="whitespace-nowrap">{when(l.first_seen_at)}</Td>
            </tr>
          ))}
          {!listings?.length ? <EmptyRow colSpan={7}>No hay publicaciones con esa búsqueda.</EmptyRow> : null}
        </tbody>
      </Table>
    </>
  );
}
