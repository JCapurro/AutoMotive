import type { Metadata } from "next";

import { LevelBadge } from "@/components/app/badges";
import { ScoreHistogram } from "@/components/admin/score-histogram";
import { EmptyRow, PageHeader, Pill, Section, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { count, when } from "@/lib/admin-format";
import { LEVEL, LEVELS, type Level } from "@/lib/copy";
import { vehicle } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Matches" };

// sección 10, "Matches y scores": the distribution by level and source, and the latest matches.
export default async function MatchesPage() {
  const admin = createAdminClient();
  const [{ data: histogram }, { data: recent }] = await Promise.all([
    admin.from("admin_score_histogram").select("*"),
    admin
      .from("matches")
      .select("id, score, level, is_backfill, generated_at, search_profile_id, listing_id, listings(title, make, model, trim, year, source)")
      .order("id", { ascending: false })
      .limit(50),
  ]);
  const rows = histogram ?? [];
  const buckets = new Map<number, number>();
  const bySource = new Map<string, Record<string, number>>();
  for (const r of rows) {
    buckets.set(r.bucket ?? 0, (buckets.get(r.bucket ?? 0) ?? 0) + (r.matches ?? 0));
    const s = bySource.get(r.source ?? "?") ?? {};
    s[r.level ?? "low"] = (s[r.level ?? "low"] ?? 0) + (r.matches ?? 0);
    bySource.set(r.source ?? "?", s);
  }
  const total = (s: Record<string, number>) => LEVELS.reduce((sum, l) => sum + (s[l] ?? 0), 0);
  const all = LEVELS.reduce<Record<string, number>>((acc, l) => {
    acc[l] = [...bySource.values()].reduce((sum, s) => sum + (s[l] ?? 0), 0);
    return acc;
  }, {});

  return (
    <>
      <PageHeader title="Matches y scores" description="Cómo se reparten los Opportunity Scores (sección 6.3) por nivel y por fuente." />

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Distribución de scores" description="Matches por rango de 10 puntos.">
          <ScoreHistogram buckets={[...buckets].map(([bucket, matches]) => ({ bucket, matches }))} />
        </Section>
        <Section title="Por nivel y fuente">
          <Table>
            <thead>
              <tr>
                <Th>Fuente</Th>
                {LEVELS.map((l) => (
                  <Th key={l} numeric>
                    <span title={LEVEL[l].label} aria-hidden>
                      {LEVEL[l].emoji}
                    </span>
                    <span className="sr-only">{LEVEL[l].label}</span>
                  </Th>
                ))}
                <Th numeric>Total</Th>
              </tr>
            </thead>
            <tbody>
              {[...bySource].map(([source, s]) => (
                <tr key={source}>
                  <Td>{source}</Td>
                  {LEVELS.map((l) => (
                    <Td key={l} numeric>
                      {count(s[l] ?? 0)}
                    </Td>
                  ))}
                  <Td numeric className="font-medium">
                    {count(total(s))}
                  </Td>
                </tr>
              ))}
              {bySource.size ? (
                <tr className="bg-muted/50">
                  <Td className="font-medium">Todas</Td>
                  {LEVELS.map((l) => (
                    <Td key={l} numeric className="font-medium">
                      {count(all[l])}
                    </Td>
                  ))}
                  <Td numeric className="font-medium">
                    {count(total(all))}
                  </Td>
                </tr>
              ) : (
                <EmptyRow colSpan={LEVELS.length + 2} />
              )}
            </tbody>
          </Table>
        </Section>
      </div>

      <Section title="Últimos matches" description="«Inspeccionar» muestra razones, score, comparables y red flags.">
        <Table>
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Nivel</Th>
              <Th>Publicación</Th>
              <Th>Búsqueda</Th>
              <Th>Generado</Th>
              <Th>
                <span className="sr-only">Inspeccionar</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {(recent ?? []).map((m) => (
              <tr key={m.id}>
                <Td className="tabular-nums">{m.id}</Td>
                <Td>
                  <LevelBadge level={m.level as Level} score={m.score} />
                </Td>
                <Td className="max-w-72">
                  <span className="line-clamp-1">{m.listings ? vehicle(m.listings) : `#${m.listing_id}`}</span>
                  <span className="text-xs text-muted-foreground">
                    #{m.listing_id} · {m.listings?.source}
                  </span>
                </Td>
                <Td className="tabular-nums">
                  #{m.search_profile_id} {m.is_backfill ? <Pill>backfill</Pill> : null}
                </Td>
                <Td className="whitespace-nowrap">{when(m.generated_at)}</Td>
                <Td>
                  <TextLink href={`/admin/matches/${m.id}`}>Inspeccionar</TextLink>
                </Td>
              </tr>
            ))}
            {!recent?.length ? <EmptyRow colSpan={6} /> : null}
          </tbody>
        </Table>
      </Section>
    </>
  );
}
