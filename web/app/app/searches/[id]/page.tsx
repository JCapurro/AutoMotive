import { Loader2, Pencil } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/app/auto-refresh";
import { LISTING_ROWS, ListingCard } from "@/components/app/listing-card";
import { ProBanner, VisibleResultsReport } from "@/components/app/pro-cta";
import { FrequencySelect, PauseButton } from "@/components/app/search-actions";
import { SortSelect } from "@/components/app/sort-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import { type PlanLimits, visibleResults } from "@/lib/pro";
import { describeVehicle, filterParts } from "@/lib/search";
import { isSort, type Sort } from "@/lib/sorts";
import { createClient } from "@/lib/supabase/server";
import type { Filters } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Resultados" };

// §29
const FILTERS = {
  new: "Nuevos",
  opportunities: "Oportunidades",
  all: "Todos",
  saved: "Favoritos",
  discarded: "Descartados",
} as const;
type Filter = keyof typeof FILTERS;
const COUNT_KEY: Record<Filter, string> = {
  new: "new_count",
  opportunities: "opportunities_count",
  all: "all_count",
  saved: "saved_count",
  discarded: "discarded_count",
};
const EMPTY: Record<Filter, string> = {
  new: "No hay publicaciones nuevas sin ver.",
  opportunities: "Todavía no hay oportunidades para esta búsqueda.",
  all: "Todavía no hay publicaciones que coincidan. Te avisamos cuando aparezca una.",
  saved: "No guardaste publicaciones de esta búsqueda.",
  discarded: "No descartaste publicaciones.",
};
const PAGE_SIZE = 50;

export default async function SearchResultsPage({ params, searchParams }: PageProps<"/app/searches/[id]">) {
  await requireUser();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const query = await searchParams;
  const filter: Filter = typeof query.f === "string" && Object.hasOwn(FILTERS, query.f) ? (query.f as Filter) : "all";
  const sort: Sort = isSort(query.s) ? query.s : "recent";
  const page = Math.max(Number(query.p) || 1, 1);

  const supabase = await createClient();
  const profileId = Number(id);
  const [{ data: profile }, { data: results }, { data: counts }, { data: planLimits }] = await Promise.all([
    supabase.from("search_profiles").select("*").eq("id", profileId).maybeSingle(),
    supabase.rpc("search_results", {
      p_profile_id: profileId,
      p_filter: filter,
      p_sort: sort,
      p_limit: PAGE_SIZE * page + 1,
      p_offset: 0,
    }),
    supabase.rpc("search_result_counts", { p_profile_id: profileId }),
    supabase.rpc("my_plan_limits"),
  ]);
  if (!profile) notFound();

  const filters = profile.filters as Filters;
  const pending = !profile.bootstrapped_at || Boolean(profile.rematch_requested_at);
  const count = (counts?.[0] ?? {}) as Record<string, number>;
  // §33: the free plan's visible results. Not enforced (the pilot): all of
  // them, and the database records plan_limit_hit. Enforced: capped.
  const limit = visibleResults(count.all_count ?? 0, (planLimits ?? null) as PlanLimits | null);
  const rows = results ?? [];
  const reach = limit.cap != null ? Math.min(PAGE_SIZE * page, limit.cap) : PAGE_SIZE * page;
  const more = rows.length > reach && reach === PAGE_SIZE * page;
  const shown = rows.slice(0, reach);
  const href = (next: Partial<{ f: Filter; s: Sort; p: number }>) => {
    const qs = new URLSearchParams({ f: next.f ?? filter, s: next.s ?? sort });
    if (next.p && next.p > 1) qs.set("p", String(next.p));
    return `/app/searches/${profileId}?${qs}`;
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h1 className="type-heading flex items-center gap-2 text-[28px] leading-tight">
            <span className="truncate">{profile.name}</span>
            {!profile.enabled ? <Badge variant="secondary">Pausada</Badge> : null}
          </h1>
          <ul aria-label="Filtros" className="flex flex-wrap gap-1.5">
            {[describeVehicle(filters), ...filterParts(filters, profile.radius_km)].filter(Boolean).map((part) => (
              <li key={part} className="rounded bg-muted px-2 py-0.5 text-[13px] text-muted-foreground [font-stretch:92%]">
                {part}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FrequencySelect id={profile.id} value={profile.notification_frequency} dailyOnly={Boolean((planLimits as PlanLimits | null)?.enforced && (planLimits as PlanLimits | null)?.plan === "free")} />
          <PauseButton id={profile.id} enabled={profile.enabled} />
          <Button asChild variant="outline" size="sm">
            <Link href={`/app/searches/${profile.id}/edit`}>
              <Pencil aria-hidden /> Editar
            </Link>
          </Button>
        </div>
      </div>

      {pending ? (
        <div
          role="status"
          className="flex items-center gap-2.5 rounded-lg bg-muted p-4 text-sm"
        >
          <Loader2 className="size-4 shrink-0 animate-spin motion-reduce:animate-none" aria-hidden />
          Estamos buscando coincidencias entre las publicaciones de los últimos 30 días. Aparecen acá en unos minutos.
          <AutoRefresh />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav aria-label="Filtros" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          {(Object.keys(FILTERS) as Filter[]).map((f) => (
            <Link
              key={f}
              href={href({ f, p: 1 })}
              aria-current={f === filter ? "page" : undefined}
              className={cn(
                "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm ring-1 ring-border",
                f === filter ? "bg-primary font-semibold text-primary-foreground ring-primary" : "bg-background hover:bg-muted",
              )}
            >
              {FILTERS[f]}
              <span className="tabular-nums opacity-70">{count[COUNT_KEY[f]] ?? 0}</span>
            </Link>
          ))}
        </nav>
        <SortSelect value={sort} />
      </div>

      {shown.length ? (
        <div className={LISTING_ROWS} data-testid="results">
          {shown.map((card) => (
            <ListingCard key={card.listing_id} card={card} />
          ))}
        </div>
      ) : (
        <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
          {pending ? "Buscando…" : EMPTY[filter]}
        </p>
      )}

      {limit.over ? (
        <>
          <VisibleResultsReport profileId={profileId} total={count.all_count ?? 0} />
          {limit.cap != null && rows.length > limit.cap ? <ProBanner placement="results" reason="results" /> : null}
        </>
      ) : null}

      {more ? (
        <div className="text-center">
          <Button asChild variant="outline">
            <Link href={href({ p: page + 1 })} scroll={false}>
              Ver más
            </Link>
          </Button>
        </div>
      ) : null}
    </div>
  );
}
