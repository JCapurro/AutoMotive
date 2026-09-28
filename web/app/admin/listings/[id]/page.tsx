import { AlertTriangle, ExternalLink, Info } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LevelBadge } from "@/components/app/badges";
import { EmptyRow, Json, PageHeader, Section, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { when } from "@/lib/admin-format";
import { SNAPSHOT_CHANGE } from "@/lib/copy";
import { money, number, vehicle } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";
import type { RedFlag } from "@/lib/types";

export const metadata: Metadata = { title: "Listing" };

// sección 10, "Listings": one listing with its snapshots, matches and red flags.
export default async function AdminListingPage({ params }: PageProps<"/admin/listings/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const listingId = Number(id);
  const admin = createAdminClient();
  const [{ data: listing }, { data: snapshots }, { data: matches }] = await Promise.all([
    admin.from("listings").select("*").eq("id", listingId).maybeSingle(),
    admin.from("listing_snapshots").select("*").eq("listing_id", listingId).order("observed_at", { ascending: false }),
    admin
      .from("matches")
      .select("id, score, level, is_backfill, generated_at, red_flags, search_profile_id, search_profiles(name, profiles(email))")
      .eq("listing_id", listingId)
      .order("score", { ascending: false }),
  ]);
  if (!listing) notFound();
  const flags = new Map<string, RedFlag>();
  for (const m of matches ?? []) for (const f of (m.red_flags ?? []) as RedFlag[]) flags.set(f.id, f);

  return (
    <>
      <PageHeader title={`#${listing.id} · ${vehicle(listing)}`} description={`${listing.source} · ${listing.external_id} · ${listing.status}`}>
        <a href={listing.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium hover:underline">
          Ver en la fuente <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Matches" description="«Inspeccionar» abre el ¿por qué? de cada uno.">
          <Table>
            <thead>
              <tr>
                <Th>Nivel</Th>
                <Th>Búsqueda</Th>
                <Th>Generado</Th>
                <Th>
                  <span className="sr-only">Inspeccionar</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {(matches ?? []).map((m) => (
                <tr key={m.id}>
                  <Td>
                    <LevelBadge level={m.level} score={m.score} />
                  </Td>
                  <Td className="max-w-56">
                    #{m.search_profile_id} {m.search_profiles?.name}
                    <span className="block truncate text-xs text-muted-foreground">{m.search_profiles?.profiles?.email ?? "Solo Telegram"}</span>
                  </Td>
                  <Td className="whitespace-nowrap">
                    {when(m.generated_at)}
                    {m.is_backfill ? <span className="block text-xs text-muted-foreground">backfill</span> : null}
                  </Td>
                  <Td>
                    <TextLink href={`/admin/matches/${m.id}`}>Inspeccionar</TextLink>
                  </Td>
                </tr>
              ))}
              {!matches?.length ? <EmptyRow colSpan={4}>Sin matches.</EmptyRow> : null}
            </tbody>
          </Table>
        </Section>

        <Section title="Red flags">
          {flags.size ? (
            <ul className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
              {[...flags.values()].map((f) => (
                <li key={f.id} className="flex gap-2 text-sm">
                  {f.severity === "warning" ? (
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-label="warning" />
                  ) : (
                    <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="info" />
                  )}
                  {f.text}
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl bg-muted p-4 text-sm text-muted-foreground">Ninguna.</p>
          )}
        </Section>
      </div>

      <Section title="Snapshots" description="Una fila por cambio detectado (sección 5.3).">
        <Table>
          <thead>
            <tr>
              <Th>Cuándo</Th>
              <Th>Cambio</Th>
              <Th numeric>Precio</Th>
              <Th numeric>USD</Th>
              <Th numeric>Cotización</Th>
              <Th numeric>Km</Th>
            </tr>
          </thead>
          <tbody>
            {(snapshots ?? []).map((s) => (
              <tr key={s.id}>
                <Td className="whitespace-nowrap">{when(s.observed_at)}</Td>
                <Td>{SNAPSHOT_CHANGE[s.change_kind] ?? s.change_kind}</Td>
                <Td numeric className="whitespace-nowrap">
                  {money(s.price, s.currency)}
                </Td>
                <Td numeric>{number(s.price_usd)}</Td>
                <Td numeric>{number(s.fx_rate)}</Td>
                <Td numeric>{number(s.mileage_km)}</Td>
              </tr>
            ))}
            {!snapshots?.length ? <EmptyRow colSpan={6} /> : null}
          </tbody>
        </Table>
      </Section>

      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">Fila completa (JSON)</summary>
        <Json value={listing} className="mt-2" />
      </details>
    </>
  );
}
