-- F-02 paso 1 · Clave, conteo y métrica de vendedor
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem F-02; diseño
-- docs/superpowers/specs/2026-10-30-f02-vendedor-design.md; plan
-- docs/superpowers/plans/2026-10-30-f02-vendedor.md).
--
-- Nothing a user sees changes and no score moves: no RLS for users, no
-- function, no SCORING_VERSION.
-- * listings.seller_key: the seller name normalized (worker/normalization/seller.py),
--   written by the ingest repo from the merged seller_name. Not a KEY_ATTR.
-- * listings.seller_listing_count: how many distinct cars the same seller key
--   published in the same source in the last window_days and still has active
--   (worker/pipeline/seller_classification.py, at startup, at the anchor slot
--   and from the CLI). Gone listings keep their last value.
-- * seller_classification_runs: each run of that job; service role only.
-- * app_config.seller_classification: enabled (no effect until step 2),
--   min_listings 6 and window_days 30, editable in /admin/config.
-- * admin_seller_coverage: per source, how many active listings lack a seller
--   type, name or key, and how many are over the threshold (/admin/sources).

alter table public.listings
  add column seller_key text,
  add column seller_listing_count integer;

-- Without concurrently: the migration runs in a transaction. Partial, so it
-- only holds the active listings that have a key.
create index listings_seller_key_idx on public.listings (source, seller_key)
  where status = 'active' and seller_key is not null;

comment on column public.listings.seller_key is
  'F-02: seller_name normalized by the worker (normalization/seller.py); null when generic or missing.';
comment on column public.listings.seller_listing_count is
  'F-02: distinct cars of the same (source, seller_key) published in the last window_days and still active, '
  'as of the last seller classification run. Null without a key.';

create table public.seller_classification_runs (
  id               bigint generated always as identity primary key,
  trigger          text not null check (trigger in ('startup', 'nightly', 'cli')),
  mode             text not null check (mode in ('dry_run', 'write')),
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  status           text not null default 'running' check (status in ('running', 'ok', 'failed')),
  rows_read        integer,
  rows_written     integer,
  inferred_changed integer,
  params           jsonb,
  error            text
);

comment on table public.seller_classification_runs is
  'F-02: each run of the seller classification job (worker: pipeline/seller_classification.py).';

-- No policy: only the service role (the worker and the admin pages) reads it.
alter table public.seller_classification_runs enable row level security;
revoke all on public.seller_classification_runs from public, anon, authenticated;
grant all on public.seller_classification_runs to service_role;

insert into public.app_config (key, value)
values ('seller_classification', '{"enabled": true, "min_listings": 6, "window_days": 30}')
on conflict (key) do nothing;

-- min_listings as the worker reads it (intelligence/config.py
-- seller_classification): an integer from 2 to 100, else 6. The cast only
-- runs on a number of at most 3 digits, so a bad value never raises.
create view public.admin_seller_coverage with (security_invoker = true) as
with cfg as (
  select coalesce((
    select case when jsonb_typeof(c.value -> 'min_listings') = 'number'
                     and (c.value ->> 'min_listings') ~ '^[0-9]{1,3}$'
                then case when (c.value ->> 'min_listings')::int between 2 and 100
                          then (c.value ->> 'min_listings')::int end
           end
      from public.app_config c
     where c.key = 'seller_classification' and jsonb_typeof(c.value) = 'object'), 6) as min_listings
)
select l.source,
       count(*)                                                                   as active,
       count(*) filter (where l.seller_type is null)                              as seller_type_null,
       round(100.0 * count(*) filter (where l.seller_type is null) / count(*), 1) as seller_type_null_pct,
       count(*) filter (where nullif(btrim(l.seller_name), '') is null)           as seller_name_null,
       round(100.0 * count(*) filter (where nullif(btrim(l.seller_name), '') is null) / count(*), 1)
                                                                                  as seller_name_null_pct,
       count(*) filter (where l.seller_key is null)                               as seller_key_null,
       round(100.0 * count(*) filter (where l.seller_key is null) / count(*), 1)  as seller_key_null_pct,
       count(*) filter (where l.seller_listing_count >= cfg.min_listings)         as over_threshold,
       cfg.min_listings
  from public.listings l
 cross join cfg
 where l.status = 'active'
 group by l.source, cfg.min_listings;

revoke all on public.admin_seller_coverage from public, anon, authenticated;
grant select on public.admin_seller_coverage to service_role;

notify pgrst, 'reload schema';
