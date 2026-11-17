"""Every SQL the bot runs. Reads the platform's tables; writes only its own
(prospects, prospect_messages, prospect_events) and only when not --dry-run."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from prospector import sellers


def load_env(path: Path | None) -> None:
    """KEY=value lines into os.environ, never overriding what is set. Prints nothing."""
    if not path or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and not os.environ.get(key.strip()):
            os.environ[key.strip()] = value


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Falta DATABASE_URL (en el entorno o en el .env que pasás con --env-file).")
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True, connect_timeout=20)
    conn.execute("set statement_timeout = '120s'")
    return conn


BASE_SQL = """
with s as (
  select source, seller_name from public.listings
   where status = 'active' and coalesce(btrim(seller_name), '') <> ''
   group by 1, 2 having count(*) between %(min)s and %(max)s
)
select l.id, l.source, l.seller_name, l.make, l.model, l.trim, l.year, l.price, l.currency, l.price_usd,
       l.mileage_km, l.seller_type, l.dealer_inferred, l.price_partial, l.title, l.description, l.url, l.location_text,
       l.first_seen_at, l.published_at, l.last_seen_at,
       l.lat, l.lon, z.province_id, z.department, z.precision
  from public.listings l
  join s using (source, seller_name)
  left join public.listing_zones z on z.listing_id = l.id
 where l.status = 'active'
"""


def base_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    from prospector.facts import with_zone
    return with_zone(conn.execute(BASE_SQL, {"min": sellers.MIN_LISTINGS, "max": sellers.MAX_LISTINGS}).fetchall())


def config(conn: psycopg.Connection, key: str) -> Any:
    row = conn.execute("select value from public.app_config where key = %s", (key,)).fetchone()
    return row["value"] if row else None


def paid_phones(conn: psycopg.Connection) -> frozenset[str]:
    """Phones of accounts with a paid plan in force: clients are never prospects."""
    from prospector.phones import normalize
    rows = conn.execute(
        "select phone from public.profiles where plan <> 'free' and phone is not null "
        "and (plan_expires_at is null or plan_expires_at > now())").fetchall()
    return frozenset(n for n in (normalize(r["phone"]) for r in rows) if n)


# Fresh listings from private sellers: the pool of hooks. The comparables are
# the worker's own (public.comparables, the same pool and cascade a match uses).
HOOK_POOL_SQL = """
select l.id, l.source, l.make, l.model, l.trim, l.year, l.price, l.currency, l.price_usd, l.mileage_km,
       l.url, l.title, l.location_text, l.first_seen_at, l.seller_type, l.dealer_inferred, l.description,
       l.images, l.last_seen_at, l.price_published, l.price_published_currency,
       l.lat, l.lon, z.province_id, z.department, z.precision,
       public.comparables(l.id) as ref
  from public.listings l
  left join public.listing_zones z on z.listing_id = l.id
 where l.status = 'active'
   and l.first_seen_at > now() - make_interval(hours => %(hours)s)
   and l.seller_type = 'private' and not coalesce(l.dealer_inferred, false)
   and not coalesce(l.price_partial, false) and l.probable_repost_of is null
   and l.price_usd is not null and l.year is not null
   and (l.make, l.model) in (select * from unnest(%(makes)s::text[], %(models)s::text[]))
"""


def hook_pool(conn: psycopg.Connection, models: Iterable[tuple[str, str]], hours: int) -> list[dict[str, Any]]:
    from prospector.facts import with_zone
    pairs = sorted(set(models))
    if not pairs:
        return []
    return with_zone(conn.execute(HOOK_POOL_SQL, {"hours": hours, "makes": [m for m, _ in pairs],
                                                  "models": [m for _, m in pairs]}).fetchall())


# The price position of a prospect's car among the comparables published in
# its zone: the worker's pool (comparable_pool) narrowed to the province, or to
# CABA + GBA for the AMBA.
#
# listing_zones is not kept for every listing (it stopped on 09/11/2026), so the
# zone comes from the coordinates here, with the worker's derive_zone.
POOL_SQL = """
select c.id, c.price_usd, c.lat, c.lon, c.location_text, c.source, z.province_id, z.department, z.precision
  from public.comparable_pool(%(id)s) c
  left join public.listing_zones z on z.listing_id = c.id
 where c.price_usd is not null
"""


def comparable_pool(conn: psycopg.Connection, listing_id: int) -> list[dict[str, Any]]:
    from prospector.facts import with_zone
    return with_zone(conn.execute(POOL_SQL, {"id": listing_id}).fetchall())


# Aggregated demand: how many active searches in Ese Auto ask for a model
# within RADIUS km of the prospect. A count only, never who.
DEMAND_SQL = """
select count(*) as n from public.search_profiles sp
 where sp.enabled and lower(sp.filters->>'make') = lower(%(make)s) and lower(sp.filters->>'model') = lower(%(model)s)
   and sp.origin_lat is not null
   and 6371 * 2 * asin(sqrt(power(sin(radians(sp.origin_lat - %(lat)s) / 2), 2)
       + cos(radians(%(lat)s)) * cos(radians(sp.origin_lat)) * power(sin(radians(sp.origin_lon - %(lon)s) / 2), 2)))
       <= %(radius)s
"""


def demand(conn: psycopg.Connection, make: str, model: str, lat: float, lon: float, radius_km: float) -> int:
    row = conn.execute(DEMAND_SQL, {"make": make, "model": model, "lat": lat, "lon": lon, "radius": radius_km}).fetchone()
    return int(row["n"]) if row else 0


def stopped_listings(conn: psycopg.Connection, keys: list[tuple[str, str]], days: int) -> int:
    """Listings of the seller that stopped being published in the last `days` days."""
    if not keys:
        return 0
    row = conn.execute(
        """select count(*) as n from public.listings
            where status <> 'active' and last_seen_at > now() - make_interval(days => %(days)s)
              and (source, seller_name) in (select * from unnest(%(s)s::text[], %(n)s::text[]))""",
        {"days": days, "s": [s for s, _ in keys], "n": [n for _, n in keys]}).fetchone()
    return int(row["n"]) if row else 0


# ----------------------------------------------------------------------------
# The bot's own tables (migration 20261225120000_prospecting.sql)
# ----------------------------------------------------------------------------

def tables_exist(conn: psycopg.Connection) -> bool:
    row = conn.execute("select to_regclass('public.prospects') is not null as ok").fetchone()
    return bool(row and row["ok"])


def accepts_ml_button(conn: psycopg.Connection) -> bool:
    """Whether prospects.phone_source takes 'boton_ml' (migration 20261226120000)."""
    row = conn.execute(
        """select coalesce(bool_or(pg_get_constraintdef(c.oid) like '%%boton_ml%%'), false) as ok
             from pg_constraint c where c.conrelid = 'public.prospects'::regclass and c.contype = 'c'""").fetchone()
    return bool(row and row["ok"])


def known_prospects(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return conn.execute(
        "select id, seller_keys, status, phone, phone_checked_at, step_sent, next_due_on, kind, display_name "
        "from public.prospects").fetchall()


def used_hooks(conn: psycopg.Connection, prospect_id: int) -> list[int]:
    rows = conn.execute("select hook_listing_id from public.prospect_messages "
                        "where prospect_id = %s and hook_listing_id is not null", (prospect_id,)).fetchall()
    return [r["hook_listing_id"] for r in rows]


# Messages before this day only carried the car, and many answers were «no entiendo»:
# they are not examples of what works (Juan, 16/11/2026).
EXAMPLES_SINCE = "2026-11-17"


def replied_examples(conn: psycopg.Connection, limit: int = 6) -> list[dict[str, Any]]:
    """The last messages that got an answer, as examples for the writer."""
    return conn.execute(
        """select m.final_text as text, m.hook_type, p.kind
             from public.prospect_messages m join public.prospects p on p.id = m.prospect_id
            where m.status = 'sent' and p.replied_at is not null and m.sent_at <= p.replied_at
              and m.sent_at >= %s::date
            order by p.replied_at desc limit %s""", (EXAMPLES_SINCE, limit)).fetchall()


def expire_stale(conn: psycopg.Connection, keep_days: int) -> int:
    """Ready messages nobody sent in `keep_days` days: their facts are old."""
    with conn.transaction():
        rows = conn.execute(
            """update public.prospect_messages set status = 'expired', updated_at = now()
                where status = 'ready' and batch_date < (now() at time zone 'America/Argentina/Buenos_Aires')::date
                      - %s returning prospect_id, step""", (keep_days,)).fetchall()
    return len(rows)


def pending_counts(conn: psycopg.Connection) -> dict[str, int]:
    rows = conn.execute("select step, count(*) as n from public.prospect_messages where status = 'ready' group by 1").fetchall()
    return {r["step"]: int(r["n"]) for r in rows}


def due_prospects(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Prospects whose next message is due today and has not been written yet."""
    return conn.execute(
        """select p.* from public.prospects p
            where p.status in ('contacted', 'followed_up') and p.next_due_on is not null
              and p.next_due_on <= (now() at time zone 'America/Argentina/Buenos_Aires')::date
              and not exists (select 1 from public.prospect_messages m
                               where m.prospect_id = p.id and m.status = 'ready')""").fetchall()


def upsert_prospect(conn: psycopg.Connection, p: dict[str, Any]) -> int:
    row = conn.execute(
        """insert into public.prospects (prospect_key, seller_keys, kind, display_name, first_name, sources,
                                         province_id, region, locality, phone, phone_source, phone_evidence,
                                         phone_checked_at, status, listing_count)
           values (%(prospect_key)s, %(seller_keys)s, %(kind)s, %(display_name)s, %(first_name)s, %(sources)s,
                   %(province_id)s, %(region)s, %(locality)s, %(phone)s, %(phone_source)s, %(phone_evidence)s,
                   now(), %(status)s, %(listing_count)s)
           on conflict (prospect_key) do update set
             seller_keys = excluded.seller_keys, kind = excluded.kind, display_name = excluded.display_name,
             first_name = excluded.first_name, sources = excluded.sources, province_id = excluded.province_id,
             region = excluded.region, locality = excluded.locality,
             phone = coalesce(public.prospects.phone, excluded.phone),
             phone_source = coalesce(public.prospects.phone_source, excluded.phone_source),
             phone_evidence = coalesce(public.prospects.phone_evidence, excluded.phone_evidence),
             phone_checked_at = now(), listing_count = excluded.listing_count,
             status = case when public.prospects.status in ('new', 'no_contact') then excluded.status
                           else public.prospects.status end,
             updated_at = now()
           returning id""", p).fetchone()
    return int(row["id"])


def insert_message(conn: psycopg.Connection, m: dict[str, Any]) -> int:
    payload = dict(m)
    for key in ("facts", "variants", "review"):
        payload[key] = Jsonb(payload[key])
    row = conn.execute(
        """insert into public.prospect_messages (prospect_id, step, batch_date, status, facts, variants,
                                                 chosen_index, final_text, hook_type, hook_listing_id,
                                                 hook_url, review, model)
           values (%(prospect_id)s, %(step)s, %(batch_date)s, %(status)s, %(facts)s, %(variants)s,
                   %(chosen_index)s, %(final_text)s, %(hook_type)s, %(hook_listing_id)s, %(hook_url)s,
                   %(review)s, %(model)s)
           returning id""", payload).fetchone()
    return int(row["id"])


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
