import { Bookmark } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { LISTING_ROWS, ListingCard } from "@/components/app/listing-card";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { type InteractionStatus, type Level } from "@/lib/copy";
import { daysSince, dayMonth, money, pct } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Guardados" };

// Followed statuses: the worker's watchlist refresher checks these too (sección 5.6).
const FOLLOWED: InteractionStatus[] = ["interested", "contacted", "visit_scheduled"];

type Snapshot = { observed_at: string; price: number | null; currency: string | null; price_usd: number | null; change_kind: string };

/**
 * §30 Watchlist: saved listings (and the ones being followed), with what
 * Ese Auto noticed since: price drops, changes, "ya no está", days online.
 */
export default async function SavedPage() {
  await requireUser();
  const supabase = await createClient();
  const { data: interactions } = await supabase
    .from("user_listing_interactions")
    .select("listing_id, status, saved, updated_at")
    .or(`saved.eq.true,status.in.(${FOLLOWED.join(",")})`)
    .order("updated_at", { ascending: false });
  const ids = (interactions ?? []).map((i) => i.listing_id);
  const cfg = await webConfig();

  if (!ids.length) {
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

  const [{ data: listings }, { data: snapshots }, { data: matches }] = await Promise.all([
    supabase
      .from("listings")
      .select("id, title, make, model, trim, year, price, currency, price_usd, mileage_km, location_text, published_at, first_seen_at, images, status, probable_repost_of")
      .in("id", ids),
    supabase
      .from("listing_snapshots")
      .select("listing_id, observed_at, price, currency, price_usd, change_kind")
      .in("listing_id", ids)
      .order("observed_at"),
    supabase.from("matches").select("listing_id, score, level, search_profiles(name)").in("listing_id", ids).order("score", { ascending: false }),
  ]);

  const byId = new Map((listings ?? []).map((l) => [l.id, l]));
  const history = new Map<number, Snapshot[]>();
  for (const s of snapshots ?? []) history.set(s.listing_id, [...(history.get(s.listing_id) ?? []), s]);
  const bestMatch = new Map<number, { score: number; level: Level; profile: string | null }>();
  for (const m of matches ?? []) {
    if (!bestMatch.has(m.listing_id)) bestMatch.set(m.listing_id, { score: m.score, level: m.level, profile: m.search_profiles?.name ?? null });
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="type-heading text-[30px] leading-tight">Guardados</h1>
        <p className="text-sm text-muted-foreground">
          Las publicaciones que guardaste o seguís. Las revisamos todos los días.
        </p>
      </div>
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
              }}
              footer={
                events.length ? (
                  <ul className="mt-1.5 space-y-0.5 border-t pt-1.5 text-xs" data-testid="watch-events">
                    {events.map((e) => (
                      <li key={e.text} className={e.tone}>
                        {e.text}
                      </li>
                    ))}
                  </ul>
                ) : null
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
      text: `Lleva ${days} días ${listing.published_at ? "publicada" : "desde que la detectamos"}`,
      tone: days >= staleDays ? "text-warn" : "text-muted-foreground",
    });
  }
  return out;
}
