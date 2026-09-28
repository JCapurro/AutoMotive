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
  place?: [string, number, number];
  publishedDaysAgo?: number;
  description?: string;
  prices?: [number, number][]; // [daysAgo, price] history before the current price
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
        last_seen_at, fingerprint)
     values ('mercadolibre', $1, $2, $3, $4, 'Ford', 'Fiesta', 'Titanium', $5, $6, 'USD', $6, $7, $8, 'nafta',
             $9, $10, $11, 'private', now() - make_interval(days => $12), now() - make_interval(days => $12),
             now(), $1)
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
