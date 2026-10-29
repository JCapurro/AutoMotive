import { Pencil } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LISTING_ROWS, ListingCard } from "@/components/app/listing-card";
import { AutoRefresh } from "@/components/app/auto-refresh";
import { FreeResultLimit } from "@/components/app/free-result-limit";
import { ProBanner, VisibleResultsReport } from "@/components/app/pro-cta";
import { FrequencySelect, PauseButton } from "@/components/app/search-actions";
import { SearchCriteriaSummary } from "@/components/app/search-criteria-summary";
import { SearchPreparation } from "@/components/app/search-preparation";
import { SortSelect } from "@/components/app/sort-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { FOLLOW_EMPTY, FOLLOW_LABEL } from "@/lib/copy";
import { accessDate, freeResultQuota, includesImmediateAlerts, type PlanLimits, visibleResults } from "@/lib/pro";
import { describeVehicle } from "@/lib/search";
import { collectionPending } from "@/lib/search-collection";
import { loadSearchCollection } from "@/lib/search-collection-server";
import { isSort, type Sort } from "@/lib/sorts";
import { createClient } from "@/lib/supabase/server";
import type { Filters, Preferences } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Resultados" };

/**
 * X-01: search_follow_counts' three numbers, or zeros when the RPC is missing
 * or fails (the web may reach a database without the migration yet).
 */
function followCounts(data: unknown): Record<string, number> {
  const row = (Array.isArray(data) ? data[0] : null) as Record<string, unknown> | null;
  const n = (key: string) => (typeof row?.[key] === "number" ? (row[key] as number) : 0);
  return { contacted_count: n("contacted_count"), visit_scheduled_count: n("visit_scheduled_count"), purchased_count: n("purchased_count") };
}

// §29, plus X-01's follow-up states (search_follow_counts), always shown.
const FILTERS = {
  new: "Nuevos",
  opportunities: "Oportunidades",
  all: "Todos",
  saved: "Favoritos",
  discarded: "Descartados",
  ...FOLLOW_LABEL,
} as const;
type Filter = keyof typeof FILTERS;
const COUNT_KEY: Record<Filter, string> = {
  new: "new_count",
  opportunities: "opportunities_count",
  all: "all_count",
  saved: "saved_count",
  discarded: "discarded_count",
  contacted: "contacted_count",
  visit_scheduled: "visit_scheduled_count",
  purchased: "purchased_count",
};
const EMPTY: Record<Filter, string> = {
  new: "No hay publicaciones nuevas sin ver.",
  opportunities: "Todavía no hay oportunidades para esta búsqueda.",
  all: "Todavía no hay publicaciones que coincidan. Te avisamos cuando aparezca una.",
  saved: "No guardaste publicaciones de esta búsqueda.",
  discarded: "No descartaste publicaciones.",
  ...FOLLOW_EMPTY,
};
const PAGE_SIZE = 50;

export default async function SearchResultsPage({ params, searchParams }: PageProps<"/app/searches/[id]">) {
  const user = await requireUser();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const query = await searchParams;
  const filter: Filter = typeof query.f === "string" && Object.hasOwn(FILTERS, query.f) ? (query.f as Filter) : "all";
  const sort: Sort = isSort(query.s) ? query.s : "score";
  const page = Math.max(Number(query.p) || 1, 1);

  const supabase = await createClient();
  const profileId = Number(id);
  const [{ data: profile }, { data: results }, { data: counts }, follow, { data: planLimits }, { data: sources }] = await Promise.all([
    supabase.from("search_profiles").select("*").eq("id", profileId).maybeSingle(),
    supabase.rpc("search_results", {
      p_profile_id: profileId,
      p_filter: filter,
      p_sort: sort,
      p_limit: PAGE_SIZE * page + 1,
      p_offset: 0,
    }),
    supabase.rpc("search_result_counts", { p_profile_id: profileId }),
    supabase.rpc("search_follow_counts", { p_profile_id: profileId }),
    supabase.rpc("my_plan_limits"),
    supabase.from("sources").select("id,name,enabled").order("priority"),
  ]);
  if (!profile) notFound();

  const filters = profile.filters as Filters;
  const collectionSources = await loadSearchCollection(profile, user.id, sources);
  const collecting = collectionPending(collectionSources);
  const needsPreparation = !profile.bootstrapped_at || Boolean(profile.rematch_requested_at) || collecting;
  const pending = profile.enabled && needsPreparation;
  const retryCollection = profile.enabled && collectionSources?.some((source) => source.collectionState === "failed" || source.collectionState === "unknown");
  const count = { ...(counts?.[0] ?? {}), ...followCounts(follow?.data) } as Record<string, number>;
  const access = (planLimits ?? null) as PlanLimits | null;
  const quota = freeResultQuota(access);
  const checkoutConfig = quota?.reached ? await webConfig() : null;
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
      {!pending && retryCollection ? <AutoRefresh every={10_000} /> : null}
      <header className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="type-heading flex min-w-0 max-w-full items-center gap-2 text-[28px] leading-tight">
            <span className="truncate">{profile.name.trim() || describeVehicle(filters) || "Búsqueda"}</span>
            {!profile.enabled ? <Badge variant="secondary">Pausada</Badge> : null}
          </h1>
          <div className="flex flex-wrap items-center gap-2">
            <FrequencySelect id={profile.id} value={profile.notification_frequency} dailyOnly={!includesImmediateAlerts(planLimits as PlanLimits | null)} />
            <PauseButton id={profile.id} enabled={profile.enabled} />
            <Button asChild variant="outline" size="sm">
              <Link href={`/app/searches/${profile.id}/edit`}>
                <Pencil aria-hidden /> Editar
              </Link>
            </Button>
          </div>
        </div>
        <SearchCriteriaSummary
          name={profile.name}
          filters={filters}
          preferences={(profile.preferences ?? {}) as Preferences}
          radiusKm={profile.radius_km}
          hasLocation={profile.origin_lat != null && profile.origin_lon != null}
          sources={collectionSources}
        />
      </header>

      {quota?.reached && checkoutConfig ? <FreeResultLimit profileId={profileId} limit={quota.limit} offer={checkoutConfig.proOffer} automatic={checkoutConfig.automaticPayments} pilot={checkoutConfig.commercialPilot} /> : null}

      {pending ? (
        <SearchPreparation
          email={user.email}
          trialEnds={access?.state === "trial" && access.expires_at ? accessDate(access.expires_at) : null}
        />
      ) : needsPreparation ? (
        <p role="status" className="rounded-lg border bg-muted p-5 text-sm">
          Reanudá la búsqueda para preparar {profile.bootstrapped_at ? "los resultados con tus nuevos filtros" : "tus primeros resultados"}.
        </p>
      ) : null}

      {!needsPreparation || shown.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav aria-label="Filtros" data-testid="result-filters" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
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
      ) : null}

      {shown.length ? (
        <div className={LISTING_ROWS} data-testid="results">
          {shown.map((card) => (
            <ListingCard key={card.listing_id} card={card} />
          ))}
        </div>
      ) : needsPreparation ? null : (
        <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
          {EMPTY[filter]}
        </p>
      )}

      {limit.over ? (
        <>
          <VisibleResultsReport profileId={profileId} total={count.all_count ?? 0} />
          {limit.cap != null && reach >= limit.cap ? <ProBanner placement="results" reason="results" maxResults={limit.cap} /> : null}
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
