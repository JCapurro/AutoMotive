/**
 * PAR-03: a listing's price drops since we first saw it, as
 * public.listing_price_tracks() counts them (the one definition of a drop,
 * shared with the worker's emails). Pure helpers: the card line, the listing
 * page's summary and its note about what we can't see.
 */
import { PRICE_TRACK } from "@/lib/copy";
import { dayMonth, money, number, pct } from "@/lib/format";
import type { Database } from "@/types/database";

export type PriceTrack = Database["public"]["Functions"]["listing_price_tracks"]["Returns"][number];

/** Days between the publication and our first snapshot before the page says we started later. */
export const TRACK_GAP_DAYS = 2;

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

/** At least one drop counted and a last price under the first one. */
export function hasNetDrop(track: PriceTrack | null | undefined): track is PriceTrack {
  return Boolean(track && track.drops > 0 && track.cum_pct != null && Number(track.cum_pct) > 0);
}

/** Pesos only when the listing was always in ARS; a currency change is told in dollars. */
function inPesos(track: PriceTrack): boolean {
  return track.first_currency === "ARS" && track.last_currency === "ARS";
}

function amount(track: PriceTrack): { amount: string; usd: string | null } | null {
  const usd = track.cum_usd != null && Number(track.cum_usd) > 0 ? money(Number(track.cum_usd), "USD") : null;
  if (inPesos(track)) {
    const ars = Number(track.first_price) - Number(track.last_price);
    return ars > 0 ? { amount: `$ ${number(ars)}`, usd } : null;
  }
  return usd ? { amount: usd, usd: null } : null;
}

/** "Bajó 2 veces desde que la vimos: -USD 1.500 (-6,3%)."; null without a net drop. */
export function trackLine(track: PriceTrack | null | undefined): string | null {
  if (!hasNetDrop(track)) return null;
  const a = amount(track);
  if (!a) return null;
  return fill(PRICE_TRACK.line, {
    n: track.drops,
    times: PRICE_TRACK.times[track.drops === 1 ? 0 : 1],
    amount: a.amount,
    pct: pct(Number(track.cum_pct), 1),
    about: a.usd ? fill(PRICE_TRACK.aboutUsd, { usd: a.usd }) : "",
  });
}

/**
 * The listing page: "2 bajas · -USD 1.500 (-6,3%) desde el 20/09"; null
 * without a net drop. Always in dollars (cum_usd), pesos included: the
 * approved copy has only the USD form (the card tells pesos in pesos).
 */
export function summaryLine(track: PriceTrack | null | undefined): string | null {
  if (!hasNetDrop(track)) return null;
  if (track.cum_usd == null || Number(track.cum_usd) <= 0) return null;
  return fill(PRICE_TRACK.summary, {
    n: track.drops,
    drops: PRICE_TRACK.drops[track.drops === 1 ? 0 : 1],
    amount: money(Number(track.cum_usd), "USD"),
    pct: pct(Number(track.cum_pct), 1),
    date: dayMonth(track.first_at),
  });
}

/**
 * What the drops can't tell: without published_at the age counts from the
 * first detection; a listing published well before our first snapshot had
 * changes we never saw.
 */
export function trackingNote(
  listing: { published_at?: string | null },
  firstAt: string | null | undefined,
): string | null {
  if (!listing.published_at) return PRICE_TRACK.detected;
  if (!firstAt) return null;
  const gap = new Date(firstAt).getTime() - new Date(listing.published_at).getTime();
  return gap >= TRACK_GAP_DAYS * 86_400_000 ? fill(PRICE_TRACK.trackedSince, { date: dayMonth(firstAt) }) : null;
}

type Rpc = (
  fn: "listing_price_tracks",
  args: { p_listing_ids: number[] },
) => PromiseLike<{ data: PriceTrack[] | null; error: unknown }>;

/**
 * listing_price_tracks for a page's ids, by listing_id. Any error (a web
 * deployed before the migration, say) leaves the map empty: no drop line, no
 * broken page.
 */
export async function fetchPriceTracks(rpc: Rpc, ids: number[]): Promise<Map<number, PriceTrack>> {
  const unique = [...new Set(ids)];
  if (unique.length === 0) return new Map();
  try {
    const { data, error } = await rpc("listing_price_tracks", { p_listing_ids: unique });
    if (error || !data) return new Map();
    return new Map(data.map((t) => [Number(t.listing_id), t]));
  } catch {
    return new Map();
  }
}
