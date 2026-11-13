import { Pencil } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LISTING_ROWS, ListingCard } from "@/components/app/listing-card";
import { PhonePrompt } from "@/components/app/phone-form";
import { AutoRefresh } from "@/components/app/auto-refresh";
import { FreeResultLimit } from "@/components/app/free-result-limit";
import { LowResultsNotice } from "@/components/app/low-results-notice";
import { ProBanner, VisibleResultsReport } from "@/components/app/pro-cta";
import { FrequencySelect, PauseButton } from "@/components/app/search-actions";
import { SearchCriteriaSummary } from "@/components/app/search-criteria-summary";
import { SearchPreparation } from "@/components/app/search-preparation";
import { SortSelect } from "@/components/app/sort-select";
import { ZoneNoticePanel } from "@/components/app/zone-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { costLinesFor } from "@/lib/cost-estimate-data";
import { FOLLOW_EMPTY, FOLLOW_LABEL } from "@/lib/copy";
import { marginAccess, marginLinesFor, marginTeasersFor } from "@/lib/margin-data";
import { fetchPriceTracks } from "@/lib/price-track";
import { accessDate, freeResultQuota, includesImmediateAlerts, type PlanLimits, visibleResults, withoutPro } from "@/lib/pro";
import { describeVehicle } from "@/lib/search";
import { collectionPending } from "@/lib/search-collection";
import { loadSearchCollection } from "@/lib/search-collection-server";
import { storedSellerTypes } from "@/lib/search-form";
import { effectiveSort, type Sort, sortsFor } from "@/lib/sorts";
import { wantsColor } from "@/lib/listing-color";
import { createClient } from "@/lib/supabase/server";
import type { Filters, Preferences } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEARCH_TITLE_ID, sameZone, zoneOf } from "@/lib/zone-notice";
import { allCount, dismissedZones, zoneNotice } from "@/lib/zone-notice-server";

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
/** Prueba gratis: an empty list whose matches the trial hides (my_search_hidden_results). */
function hiddenText(n: number): string {
  return n === 1
    ? "Hay 1 publicación que coincide y tu prueba no muestra."
    : `Hay ${n} publicaciones que coinciden y tu prueba no muestra.`;
}

export default async function SearchResultsPage({ params, searchParams }: PageProps<"/app/searches/[id]">) {
  const user = await requireUser();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const query = await searchParams;
  const filter: Filter = typeof query.f === "string" && Object.hasOwn(FILTERS, query.f) ? (query.f as Filter) : "all";
  const page = Math.max(Number(query.p) || 1, 1);

  const supabase = await createClient();
  // PRO-02: «Mayor margen estimado» and the margin line, only for Pro (null on a database without the migration).
  const margin = await marginAccess(supabase);
  const sort: Sort = effectiveSort(query.s, margin != null);
  const profileId = Number(id);
  const [{ data: profile }, { data: results }, { data: counts }, follow, { data: planLimits, error: limitsError }, { data: sources }, { data: diagnosis }, dismissed, { data: hiddenData }] = await Promise.all([
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
    // Bot de pocos resultados; null (no row, or a database without the table) hides the card.
    supabase.from("search_diagnoses").select("explanation,suggestions,max_results,created_at,dismissed_at").eq("search_profile_id", profileId).maybeSingle(),
    // Aviso de zona: the zones «Dejar así» hid.
    dismissedZones(supabase, profileId),
    // Prueba gratis: this search's matches the trial hides (0 without a trial quota; on error, 0).
    supabase.rpc("my_search_hidden_results", { p_profile_id: profileId }),
  ]);
  if (!profile) notFound();

  const filters = profile.filters as Filters;
  // PRO-01: only a search with the strict seller filter asks whether the plan applies it.
  const sellerFilter = storedSellerTypes(filters).length > 0
    && (await supabase.rpc("my_plan_feature", { p_feature: "seller_filter" })).data === true;
  const collectionSources = await loadSearchCollection(profile, user.id, sources);
  const collecting = collectionPending(collectionSources);
  const needsPreparation = !profile.bootstrapped_at || Boolean(profile.rematch_requested_at) || collecting;
  const pending = profile.enabled && needsPreparation;
  const retryCollection = profile.enabled && collectionSources?.some((source) => source.collectionState === "failed" || source.collectionState === "unknown");
  const count = { ...(counts?.[0] ?? {}), ...followCounts(follow?.data) } as Record<string, number>;
  const access = (planLimits ?? null) as PlanLimits | null;
  // Juan, 02/11: without Pro, «Mayor margen estimado» in view and disabled, when Pro has it.
  const lockedSorts: Sort[] = margin == null && withoutPro(access) && (await webConfig()).planLimits.pro.dealerMargin ? ["margin"] : [];
  // The diagnosis still applies: not hidden, the search still short of results
  // and not prepared again (edited filters) since it was written. A zone kept
  // with the zone notice's «Dejar así» hides it too: on the card that happens
  // before the bot writes it (docs/AVISO_ZONA.md).
  const kept = dismissed?.some((zone) => sameZone(zone, zoneOf(profile))) ?? false;
  const hidden = typeof hiddenData === "number" && hiddenData > 0 ? hiddenData : 0;
  // With matches the trial hides, «few results» isn't the zone or the filters.
  const showDiagnosis =
    hidden === 0 &&
    diagnosis != null &&
    !diagnosis.dismissed_at &&
    !kept &&
    !needsPreparation &&
    (count.all_count ?? 0) <= diagnosis.max_results &&
    (!profile.bootstrapped_at || Date.parse(profile.bootstrapped_at) <= Date.parse(diagnosis.created_at));
  const quota = freeResultQuota(access);
  const checkoutConfig = quota?.reached ? await webConfig() : null;
  // §33: the free plan's visible results. Not enforced (the pilot): all of
  // them, and the database records plan_limit_hit. Enforced: capped.
  const limit = visibleResults(count.all_count ?? 0, (planLimits ?? null) as PlanLimits | null);
  const rows = results ?? [];
  const reach = limit.cap != null ? Math.min(PAGE_SIZE * page, limit.cap) : PAGE_SIZE * page;
  const more = rows.length > reach && reach === PAGE_SIZE * page;
  const shown = rows.slice(0, reach);
  // Aviso de zona's switch (app_config.zone_notice): off, the page neither counts nor shows it.
  const zoneSwitch = (await webConfig()).zoneNotice;
  // PAR-03: the drops of the listings on this page only, in one call; on error, no drop line.
  // PAR-01: the total cost line, with the plan's flag only (one listings query for the page).
  // PRO-02: the margin line for Pro; the other plans, where it would be (Juan, 02/11).
  // Aviso de zona: counted only when nothing else rules it out (lib/zone-notice-server.ts).
  const [tracks, costLines, marginLines, marginTeasers, zone, { data: contact }] = await Promise.all([
    fetchPriceTracks(
      (fn, args) => supabase.rpc(fn, args),
      shown.map((card) => card.listing_id).filter((lid): lid is number => lid != null),
    ),
    costLinesFor(supabase, user.id, shown),
    marginLinesFor(supabase, margin, shown),
    marginTeasersFor(user.id, margin, shown),
    // The switch unread, or the plan's limits (the trial's quota and cap): not now.
    zoneSwitch?.enabled === false
      ? { state: "none" as const }
      : zoneSwitch == null || limitsError
        ? { state: "pending" as const }
        : zoneNotice(supabase, { profile, count: allCount(counts), access, sources: collectionSources, dismissed }),
    // Option B (04/11): the mobile is asked here, once the results are showing.
    supabase.from("profiles").select("phone").eq("id", user.id).maybeSingle(),
  ]);
  const href = (next: Partial<{ f: Filter; s: Sort; p: number }>) => {
    const qs = new URLSearchParams({ f: next.f ?? filter, s: next.s ?? sort });
    if (next.p && next.p > 1) qs.set("p", String(next.p));
    return `/app/searches/${profileId}?${qs}`;
  };

  return (
    <div className="space-y-5">
      {!pending && retryCollection ? <AutoRefresh every={10_000} /> : null}
      {/* Aviso de zona: once the preparation's refresher goes, a first read's batch is still being
          matched (or a source hasn't started), and the page asks again until the notice can decide. */}
      {!pending && !retryCollection && zone.state === "pending" && collectionSources?.some((source) => source.firstRead)
        ? <AutoRefresh every={15_000} />
        : null}
      <header className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          {/* Where focus goes after the zone notice's buttons, which go with the refresh. */}
          <h1 id={SEARCH_TITLE_ID} tabIndex={-1} className="type-heading flex min-w-0 max-w-full items-center gap-2 text-[28px] leading-tight outline-none">
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
          sellerFilter={sellerFilter}
        />
      </header>

      {quota?.reached && checkoutConfig ? <FreeResultLimit profileId={profileId} limit={quota.limit} opportunities={count.opportunities_count ?? 0} offer={checkoutConfig.proOffer} pro={checkoutConfig.planLimits.pro} automatic={checkoutConfig.automaticPayments} pilot={checkoutConfig.commercialPilot} /> : null}

      {pending ? (
        <SearchPreparation
          email={user.email}
          trialEnds={access?.state === "trial" && access.expires_at ? accessDate(access.expires_at) : null}
          trialFull={quota?.reached ? quota.limit : null}
          immediate={includesImmediateAlerts(planLimits as PlanLimits | null)}
        />
      ) : needsPreparation ? (
        <p role="status" className="rounded-lg border bg-muted p-5 text-sm">
          Reanudá la búsqueda para preparar {profile.bootstrapped_at ? "los resultados con tus nuevos filtros" : "tus primeros resultados"}.
        </p>
      ) : null}

      {/* The zone notice takes the bot's place while it shows: both would say «widen the zone». */}
      {zone.state === "show" ? (
        <ZoneNoticePanel notice={zone.notice} />
      ) : showDiagnosis ? (
        <LowResultsNotice
          profileId={profileId}
          explanation={diagnosis.explanation}
          suggestions={Array.isArray(diagnosis.suggestions) ? diagnosis.suggestions.filter((s): s is string => typeof s === "string") : []}
        />
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
          <SortSelect value={sort} options={sortsFor(margin != null)} locked={lockedSorts} profileId={profileId} />
        </div>
      ) : null}

      {shown.length && contact && !contact.phone ? <PhonePrompt profileId={profileId} /> : null}

      {shown.length ? (
        <div className={LISTING_ROWS} data-testid="results">
          {shown.map((card) => (
            <ListingCard
              key={card.listing_id}
              card={card}
              track={card.listing_id != null ? tracks.get(card.listing_id) : null}
              costLine={card.listing_id != null ? costLines.get(card.listing_id) : null}
              marginLine={card.listing_id != null ? marginLines.get(card.listing_id) : null}
              marginTeaser={card.listing_id != null && marginTeasers.has(card.listing_id)}
              colorWanted={wantsColor(filters)}
            />
          ))}
        </div>
      ) : needsPreparation ? null : filter === "all" && hidden > 0 ? (
        <p data-testid="trial-hidden" className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
          {hiddenText(hidden)}{" "}
          <Link href="/app/pro?plan=pass_30" className="font-medium underline underline-offset-3">Con Particular ves todas</Link>.
        </p>
      ) : (
        <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
          {filter === "all" && quota?.reached ? `Todavía no hay publicaciones que coincidan. Tu prueba ya usó sus ${quota.limit} resultados: con Particular te avisamos de las nuevas.` : EMPTY[filter]}
        </p>
      )}

      {shown.length > 0 && filter === "all" && hidden > 0 && !more ? (
        <p data-testid="trial-hidden" className="text-center text-sm text-muted-foreground">
          {hidden === 1 ? "Y 1 más que coincide y tu prueba no muestra." : `Y ${hidden} más que coinciden y tu prueba no muestra.`}{" "}
          <Link href="/app/pro?plan=pass_30" className="font-medium underline underline-offset-3">Con Particular ves todas</Link>.
        </p>
      ) : null}

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
