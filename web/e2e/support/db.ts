import { Pool } from "pg";

import { DATABASE_URL, E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./env";

let pool: Pool | null = null;

/** Direct Postgres access for fixtures and assertions (the local stack only). */
export function db(): Pool {
  const host = new URL(DATABASE_URL).hostname;
  if (!["127.0.0.1", "localhost", "::1"].includes(host)) {
    throw new Error(`e2e fixtures only run against a local database, not ${host}`);
  }
  pool ??= new Pool({ connectionString: DATABASE_URL, max: 3 });
  return pool;
}

export async function closeDb(): Promise<void> {
  await pool?.end();
  pool = null;
}

export async function query<T extends Record<string, unknown> = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const { rows } = await db().query(sql, params);
  return rows as T[];
}

/**
 * Drops what earlier runs left: e2e users (and everything they own) and test
 * listings — the e2e ones and the worker tests' leftovers, all on example.test.
 * Real scraped listings are never touched.
 */
export async function resetE2E(): Promise<void> {
  await query(`delete from auth.users where email like $1`, [`%@${E2E_EMAIL_DOMAIN}`]);
  // The free search's per-IP brakes: every local request shares one bucket.
  await query(`delete from public.auth_throttle`);
  await query(`delete from public.listings where external_id like $1 or url like 'https://example.test/%'`, [
    `${E2E_LISTING_PREFIX}%`,
  ]);
}

type Seed = {
  key: string;
  year: number;
  km: number;
  price: number;
  transmission?: "manual" | "automatic";
  bodyType?: string | null; // listings.body_type, a docs/CARROCERIA.md code; null = unknown
  place?: [string, number, number];
  publishedDaysAgo?: number;
  description?: string;
  prices?: [number, number][]; // [daysAgo, price] history before the current price
  source?: string; // mercadolibre by default
  seenDaysAgo?: number; // last_seen_at, today by default
  status?: "active" | "gone";
};

const OLIVOS: [string, number, number] = ["Olivos", -34.5102, -58.4922];
const VICENTE_LOPEZ: [string, number, number] = ["Vicente López", -34.5299, -58.4742];
const MARTINEZ: [string, number, number] = ["Martínez", -34.4865, -58.5007];

export const LONG_DESCRIPTION =
  "Ford Fiesta Titanium impecable, único dueño, services oficiales al día en concesionario, " +
  "distribución cambiada a los 100.000 km, cubiertas nuevas y VTV al día. Titular, papeles al día, " +
  "acepto revisión mecánica.";

/**
 * Ford Fiesta Titanium listings around AMBA: the market the e2e search sees.
 * The four under USD 11.500 plus "target" are what its backfill should hold;
 * the rest are comparables that fail its filters (price, year, transmission).
 */
const MARKET: Seed[] = [
  {
    key: "target",
    year: 2017,
    km: 112_000,
    price: 10_300,
    place: VICENTE_LOPEZ,
    publishedDaysAgo: 20,
    description: "Fiesta Titanium 2017, muy buen estado.",
    prices: [
      [20, 11_800],
      [10, 11_300],
    ],
  },
  { key: "c1", year: 2017, km: 118_000, price: 11_200 },
  { key: "c2", year: 2016, km: 125_000, price: 10_900 },
  { key: "c3", year: 2018, km: 110_000, price: 12_100 },
  { key: "c4", year: 2017, km: 130_000, price: 10_800, place: MARTINEZ },
  { key: "c5", year: 2017, km: 122_000, price: 11_600 },
  { key: "c6", year: 2018, km: 98_000, price: 12_400 },
  { key: "c7", year: 2016, km: 115_000, price: 11_000 },
  { key: "automatic", year: 2017, km: 90_000, price: 10_500, transmission: "automatic" },
  { key: "old", year: 2012, km: 160_000, price: 6_900 },
];

/** Listings the search should backfill (hard filters: 2016–2018, ≤ USD 11.500, ≤ 150.000 km, manual, AMBA). */
export const EXPECTED_BACKFILL = ["target", "c1", "c2", "c4", "c7"];

async function insertListing(externalId: string, s: Seed): Promise<number> {
  const [place, lat, lon] = s.place ?? OLIVOS;
  const days = s.publishedDaysAgo ?? 3;
  const [row] = await query<{ id: number }>(
    `insert into public.listings
       (source, external_id, url, title, description, make, model, trim, year, price, currency, price_usd,
        mileage_km, transmission, fuel, location_text, lat, lon, seller_type, published_at, first_seen_at,
        last_seen_at, fingerprint, body_type, status)
     values ($14, $1, $2, $3, $4, 'Ford', 'Fiesta', 'Titanium', $5, $6, 'USD', $6, $7, $8, 'nafta',
             $9, $10, $11, 'private', now() - make_interval(days => $12), now() - make_interval(days => $12),
             now() - make_interval(days => $15), $1, $13, $16)
     returning id`,
    [
      externalId,
      `https://example.test/${externalId}`,
      `Ford Fiesta Titanium ${s.year}`,
      s.description ?? LONG_DESCRIPTION,
      s.year,
      s.price,
      s.km,
      s.transmission ?? "manual",
      place,
      lat,
      lon,
      days,
      s.bodyType ?? null,
      s.source ?? "mercadolibre",
      s.seenDaysAgo ?? 0,
      s.status ?? "active",
    ],
  );
  const history = [...(s.prices ?? []), [0, s.price] as [number, number]];
  for (const [i, [ago, price]] of history.entries()) {
    await query(
      `insert into public.listing_snapshots (listing_id, observed_at, price, currency, price_usd, fx_rate, mileage_km,
                                             attrs_hash, change_kind)
       values ($1, now() - make_interval(days => $2) , $3, 'USD', $3, 1000, $4, $5, $6)`,
      [row.id, ago, price, s.km, `h${i}`, i === 0 ? "new" : "price"],
    );
  }
  return row.id;
}

/**
 * Seeds the market and today's USD/ARS quote (the worker would otherwise
 * fetch it from dolarapi.com). Returns listing ids by key.
 */
export async function seedMarket(): Promise<Record<string, number>> {
  await query(
    `insert into public.fx_rates (date, kind, rate, source)
     values ((now() at time zone 'America/Argentina/Buenos_Aires')::date, 'blue', 1000, 'e2e')
     on conflict (date, kind) do nothing`,
  );
  const ids: Record<string, number> = {};
  for (const s of MARKET) ids[s.key] = await insertListing(`${E2E_LISTING_PREFIX}${s.key}`, s);
  return ids;
}

/**
 * The crawl tick's first pass for a search, without scraping: every enabled
 * source lists the search in a target (its inventory target, if it has one)
 * and reports a finished run, which ends the results page's preparation.
 */
export async function finishFirstCollection(profileId: number, make: string, model: string): Promise<void> {
  const sources = await query<{ id: string }>(`select id from public.sources where enabled`);
  for (const { id: source } of sources) {
    const [target] = await query<{ id: number }>(
      `with inventory as (
         update public.crawl_targets set query = jsonb_set(query, '{profile_ids}', coalesce(query->'profile_ids', '[]') || to_jsonb($2::bigint))
          where source = $1 and make is null and model is null and query->>'inventory' = 'true' and active
          returning id
       ), vehicle as (
         insert into public.crawl_targets (source, make, model, query)
         select $1, $3, $4, jsonb_build_object('profile_ids', jsonb_build_array($2::bigint))
          where not exists (select 1 from inventory)
         on conflict on constraint crawl_targets_unique do update
           set active = true,
               query = jsonb_set(crawl_targets.query, '{profile_ids}', coalesce(crawl_targets.query->'profile_ids', '[]') || to_jsonb($2::bigint))
         returning id
       )
       select id from inventory union all select id from vehicle`,
      [source, profileId, make, model],
    );
    await query(
      `insert into public.collector_runs (source, target_id, finished_at, status, found, new, updated)
       values ($1, $2, now(), 'ok', 0, 0, 0)`,
      [source, target.id],
    );
  }
}

/**
 * Two more comparables for the listing page's "autos parecidos" (comparables
 * fase 1, migration 20261105120000), at both ends of the price range so the
 * list shows them whenever they are in the pool:
 *   * an Autocity one last seen 3 days ago, which Autocity's complete read an
 *     hour ago no longer saw: out of the pool;
 *   * a Mercado Libre one that is gone: it still counts (0f348a8).
 * Above the search's cap or gone, neither is backfilled.
 */
export async function seedConfirmationComparables(run: string): Promise<void> {
  await insertListing(`${E2E_LISTING_PREFIX}unconfirmed-${run}`, {
    key: "unconfirmed",
    year: 2017,
    km: 100_000,
    price: 13_579, // the dearest Fiesta Titanium
    source: "autocity",
    publishedDaysAgo: 10,
    seenDaysAgo: 3,
  });
  await insertListing(`${E2E_LISTING_PREFIX}gone-${run}`, {
    key: "gone",
    year: 2017,
    km: 100_000,
    price: 8_765, // the cheapest
    publishedDaysAgo: 10,
    seenDaysAgo: 2,
    status: "gone",
  });
  await query(
    `insert into public.crawl_targets (source, make, model, query, last_run_at, first_run_done)
     values ('autocity', null, null, '{"inventory": true}', now() - interval '1 hour', true)
     on conflict on constraint crawl_targets_unique do update
       set last_run_at = excluded.last_run_at, query = crawl_targets.query || '{"inventory": true}'`,
  );
}

/**
 * X-01 (tracking.spec.ts): one active and one gone Fiesta, matched by a fresh
 * search of the given user, so the follow-up can be set on both. Returns the
 * search and listing ids.
 */
export async function seedTracking(email: string, run: string): Promise<{ profileId: number; active: number; gone: number }> {
  const active = await insertListing(`${E2E_LISTING_PREFIX}tracking-active-${run}`, {
    key: "tracking-active",
    year: 2017,
    km: 101_000,
    price: 10_100,
    place: VICENTE_LOPEZ,
  });
  const gone = await insertListing(`${E2E_LISTING_PREFIX}tracking-gone-${run}`, {
    key: "tracking-gone",
    year: 2016,
    km: 121_000,
    price: 9_700,
    seenDaysAgo: 2,
    status: "gone",
  });
  const [profile] = await query<{ id: number }>(
    `insert into public.search_profiles (user_id, name, filters, notification_frequency, bootstrapped_at)
     select id, 'Fiesta seguimiento', '{"make": "Ford", "model": "Fiesta"}', 'daily', now()
       from public.profiles where email = $1
     returning id`,
    [email],
  );
  for (const [listing, score] of [[active, 74], [gone, 61]]) {
    await query(
      `insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, red_flags, scoring_version)
       values ($1, $2, $3, 'good', '{}', '{}', '[]', 'e2e')`,
      [profile.id, listing, score],
    );
  }
  return { profileId: profile.id, active, gone };
}

/** A listing that "just appeared": a clear opportunity for the e2e search. */
export async function insertFreshDeal(run: string): Promise<number> {
  return insertListing(`${E2E_LISTING_PREFIX}deal-${run}`, {
    key: "deal",
    year: 2017,
    km: 105_000,
    price: 9_900,
    publishedDaysAgo: 0,
  });
}
