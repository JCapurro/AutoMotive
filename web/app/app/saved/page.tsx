import { Bookmark } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { LISTING_ROWS, ListingCard } from "@/components/app/listing-card";
import { ListingStatusSelect } from "@/components/app/listing-status-select";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { costLinesFor } from "@/lib/cost-estimate-data";
import { FOLLOW_EMPTY, FOLLOW_FILTERS, FOLLOW_LABEL, type FollowFilter, type InteractionStatus, type Level } from "@/lib/copy";
import { daysSince, dayMonth, money, pct } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Guardados" };

// Followed statuses: the worker's watchlist refresher checks these too (sección 5.6).
// X-01 adds purchased here only, so a purchase stays in sight; the worker's list doesn't change.
const FOLLOWED: InteractionStatus[] = ["interested", "contacted", "visit_scheduled", "purchased"];

type Snapshot = { observed_at: string; price: number | null; currency: string | null; price_usd: number | null; change_kind: string };

/**
 * §30 Watchlist: saved listings (and the ones being followed), with what
 * Ese Auto noticed since: price drops, changes, "ya no está", days online.
 * X-01: filtered by follow-up status with ?e=, each card with its note and
 * a compact status select.
 */
export default async function SavedPage({ searchParams }: PageProps<"/app/saved">) {
  const user = await requireUser();
  const query = await searchParams;
  const filter: FollowFilter | null =
    typeof query.e === "string" && (FOLLOW_FILTERS as readonly string[]).includes(query.e) ? (query.e as FollowFilter) : null;
  const supabase = await createClient();
  const base = supabase.from("user_listing_interactions").select("listing_id, status, saved, note, updated_at");
  const { data: interactions } = await (filter
    ? base.eq("status", filter)
    : base.or(`saved.eq.true,status.in.(${FOLLOWED.join(",")})`)
  ).order("updated_at", { ascending: false });
  const ids = (interactions ?? []).map((i) => i.listing_id);
  const cfg = await webConfig();

  if (!ids.length && !filter) {
    return (
      <div className="mx-auto max-w-md space-y-3 py-12 text-center">
        <Bookmark className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <h1 className="type-heading text-2xl">Todavía no guardaste publicaciones</h1>
        <p className="text-sm text-muted-foreground">
          Guardá las que te interesan y seguimos monitoreándolas: te avisamos si bajan de precio o desaparecen.
        </p>
        <Link href="/app" className="text-sm underline">
          Ver mis búsquedas
        </Link>
      </div>
    );
  }

  const header = (
    <>
      <div className="space-y-1">
        <h1 className="type-heading text-[30px] leading-tight">Guardados</h1>
        {/* The worker's refresher skips purchased (FOLLOWED's note): don't promise a daily check for them. */}
        <p className="text-sm text-muted-foreground">
          {filter === "purchased"
            ? "Las publicaciones que marcaste como compradas. Quedan acá como registro."
            : "Las publicaciones que guardaste o seguís. Revisamos todos los días las que seguís; las compradas quedan como registro."}
        </p>
      </div>
      <nav aria-label="Filtrar por estado" data-testid="saved-filters" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {[null, ...FOLLOW_FILTERS].map((f) => (
          <Link
            key={f ?? "all"}
            href={f ? `/app/saved?e=${f}` : "/app/saved"}
            aria-current={f === filter ? "page" : undefined}
            className={cn(
              "inline-flex h-8 shrink-0 items-center rounded-full px-3 text-sm ring-1 ring-border",
              f === filter ? "bg-primary font-semibold text-primary-foreground ring-primary" : "bg-background hover:bg-muted",
            )}
          >
            {f ? FOLLOW_LABEL[f] : "Todos"}
          </Link>
        ))}
      </nav>
    </>
  );

  if (!ids.length) {
    return (
      <div className="space-y-4">
        {header}
        <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">{filter ? FOLLOW_EMPTY[filter] : null}</p>
      </div>
    );
  }

  const [{ data: listings }, { data: snapshots }, { data: matches }] = await Promise.all([
    supabase
      .from("listings")
      .select("id, title, make, model, trim, year, price, currency, price_usd, mileage_km, location_text, published_at, first_seen_at, images, status, probable_repost_of, body_type")
      .in("id", ids),
    supabase
      .from("listing_snapshots")
      .select("listing_id, observed_at, price, currency, price_usd, change_kind")
      .in("listing_id", ids)
      .order("observed_at"),
    supabase
      .from("matches")
      .select("listing_id, search_profile_id, score, level, search_profiles(name)")
      .in("listing_id", ids)
      .order("score", { ascending: false }),
  ]);

  const byId = new Map((listings ?? []).map((l) => [l.id, l]));
  const history = new Map<number, Snapshot[]>();
  for (const s of snapshots ?? []) history.set(s.listing_id, [...(history.get(s.listing_id) ?? []), s]);
  const bestMatch = new Map<number, { score: number; level: Level; profile: string | null; profileId: number }>();
  for (const m of matches ?? []) {
    if (!bestMatch.has(m.listing_id)) {
      bestMatch.set(m.listing_id, { score: m.score, level: m.level, profile: m.search_profiles?.name ?? null, profileId: m.search_profile_id });
    }
  }
  // PAR-01: the best match's search, or the account's default place for a listing without one.
  const costLines = await costLinesFor(
    supabase,
    user.id,
    ids.map((id) => ({ listing_id: id, search_profile_id: bestMatch.get(id)?.profileId ?? null })),
  );

  return (
    <div className="space-y-4">
      {header}
      <div className={LISTING_ROWS}>
        {(interactions ?? []).map((i) => {
          const l = byId.get(i.listing_id);
          if (!l) return null;
          const m = bestMatch.get(l.id);
          const events = watchEvents(l, history.get(l.id) ?? [], cfg.watchlistStaleDays);
          return (
            <ListingCard
              key={l.id}
              card={{
                ...l,
                listing_id: l.id,
                listing_status: l.status,
                level: m?.level ?? null,
                score: m?.score ?? null,
                status: i.status,
                saved: i.saved,
                profile_name: m?.profile ?? null,
                note: i.note,
              }}
              costLine={costLines.get(l.id)}
              footer={
                <>
                  {/* Above the card's stretched link, so picking a status doesn't open the detail. */}
                  <div className="relative z-10 mt-1.5 flex items-center gap-2">
                    <ListingStatusSelect key={i.status} listingId={l.id} status={i.status} profileId={m?.profileId ?? null} size="sm" />
                  </div>
                  {events.length ? (
                    <ul className="mt-1.5 space-y-0.5 border-t pt-1.5 text-xs" data-testid="watch-events">
                      {events.map((e) => (
                        <li key={e.text} className={e.tone}>
                          {e.text}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </>
              }
            />
          );
        })}
      </div>
    </div>
  );
}

/** What changed: "Bajó de precio", "Ya no está", "Cambió", "Lleva X días publicada" (§30). */
function watchEvents(
  listing: { status: string; published_at: string | null; first_seen_at: string; price: number | null; currency: string | null },
  snapshots: Snapshot[],
  staleDays: number,
): { text: string; tone: string }[] {
  const out: { text: string; tone: string }[] = [];
  if (listing.status === "gone") out.push({ text: "Ya no está disponible", tone: "font-medium text-destructive" });
  const prices = snapshots.filter((s) => s.price != null);
  if (prices.length >= 2) {
    const first = prices[0];
    const last = prices[prices.length - 1];
    const a = first.price_usd ?? first.price!;
    const b = last.price_usd ?? last.price!;
    if (b < a) {
      out.push({
        text: `Bajó de precio: ${money(first.price, first.currency)} → ${money(last.price, last.currency)} (-${pct(((a - b) / a) * 100, 1)}) el ${dayMonth(last.observed_at)}`,
        tone: "font-semibold text-ok",
      });
    } else if (b > a) {
      out.push({ text: `Subió de precio el ${dayMonth(last.observed_at)}`, tone: "text-muted-foreground" });
    }
  }
  const edits = snapshots.filter((s) => s.change_kind !== "new" && s.change_kind !== "price");
  if (edits.length) {
    out.push({ text: `La publicación cambió el ${dayMonth(edits[edits.length - 1].observed_at)}`, tone: "text-muted-foreground" });
  }
  const days = daysSince(listing.published_at ?? listing.first_seen_at);
  if (days >= 1) {
    out.push({
      text: listing.published_at ? `Lleva ${days} días publicada` : `La detectamos hace ${days} días`,
      tone: days >= staleDays ? "text-warn" : "text-muted-foreground",
    });
  }
  return out;
}
