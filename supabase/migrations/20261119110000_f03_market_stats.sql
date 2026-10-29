-- F-03 fase 0 (docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md,
-- docs/BACKLOG_PRODUCTO_2026-10.md): a zone per listing and weekly market
-- stats, with no UI and no gating, to start piling up weeks of data.
--
-- * listing_zones: the geographic facts of a listing's coordinates (Georef
--   province, department, locality, precision), written by the worker
--   (pipeline/market_zones.sync_zones). The region is not stored: it comes from
--   app_config.market_zones when the stats are computed, so editing the map
--   rewrites nothing. A side table, not a column of listings: that is the hot
--   table, and ingest rewrites its columns.
-- * market_stats: one row per ISO week (Monday to Sunday, Argentina time),
--   group (make + model, or body type), 2-year band and zone (each region and
--   'todas'). Computed in Python (pipeline/market_stats.py); repeating a week
--   replaces its rows (market_stats_unique, nulls not distinct).
-- * market_stats_runs: the job's runs (dry_run | write); errors also go to
--   pipeline_errors with stage 'market_stats'.
--
-- The job is born off (app_config.market_stats.mode = 'off', write_enabled
-- false); Juan turns it on from /admin/config. Nobody but an admin reads the
-- stats, and nobody reads listing_zones: future consumers get security
-- definer functions. Nothing here touches comparables() or older migrations.

-- ---------------------------------------------------------------------------
-- listing_zones
-- ---------------------------------------------------------------------------

create table public.listing_zones (
  listing_id  bigint primary key references public.listings (id) on delete cascade,
  province_id text,
  department  text,
  locality_id text,
  dist_km     numeric,
  precision   text not null check (precision in ('locality', 'province', 'source_default')),
  lat         double precision not null,
  lon         double precision not null,
  derived_at  timestamptz not null default now()
);

comment on table public.listing_zones is
  'F-03: where a listing is (Georef province INDEC code, department, locality) from the coordinates it had '
  'when derived (lat, lon). Worker only; the region is resolved with app_config.market_zones.';

-- ---------------------------------------------------------------------------
-- market_stats_runs
-- ---------------------------------------------------------------------------

create table public.market_stats_runs (
  id                bigint generated always as identity primary key,
  week_start        date not null,
  mode              text not null check (mode in ('dry_run', 'write')),
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  status            text not null default 'running' check (status in ('running', 'ok', 'failed')),
  rows_computed     integer,
  rows_written      integer,
  listings_read     integer,
  no_zone_by_source jsonb,
  params            jsonb,
  error             text
);
create index market_stats_runs_week_idx on public.market_stats_runs (week_start);

comment on table public.market_stats_runs is
  'F-03: each run of the weekly market_stats job (worker: pipeline/market_stats.py).';

-- ---------------------------------------------------------------------------
-- market_stats
-- ---------------------------------------------------------------------------

create table public.market_stats (
  week_start             date not null,
  group_kind             text not null check (group_kind in ('model', 'body_type')),
  make                   text,
  model                  text,
  body_type              text,
  year_from              integer,
  zone                   text not null,
  active_count           integer not null default 0,
  active_confirmed_count integer not null default 0,
  new_count              integer not null default 0,
  gone_count             integer not null default 0,
  price_n                integer not null default 0,
  median_price_usd       numeric,
  p25_price_usd          numeric,
  p75_price_usd          numeric,
  days_n                 integer not null default 0,
  median_days_to_gone    numeric,
  p25_days_to_gone       numeric,
  p75_days_to_gone       numeric,
  days_source            text,
  zone_map_version       integer,
  as_of                  timestamptz,
  computed_at            timestamptz not null default now(),
  run_id                 bigint references public.market_stats_runs (id) on delete set null,
  basis                  text not null default 'weekly',
  constraint market_stats_unique
    unique nulls not distinct (week_start, group_kind, make, model, body_type, year_from, zone)
);
create index market_stats_week_kind_zone_idx on public.market_stats (week_start, group_kind, zone);
create index market_stats_make_model_idx on public.market_stats (make, model);

comment on table public.market_stats is
  'F-03: weekly market of published listings per group, year band and zone. Days are until a listing '
  'stopped being published (confirm_sources only), never a sale. Kept retention.market_stats_weeks.';

-- ---------------------------------------------------------------------------
-- Access: the worker (service_role); admins read the stats
-- ---------------------------------------------------------------------------

alter table public.listing_zones enable row level security;
alter table public.market_stats_runs enable row level security;
alter table public.market_stats enable row level security;

revoke all on public.listing_zones, public.market_stats_runs, public.market_stats from public, anon, authenticated;
-- Select only so that RLS answers (no rows) instead of a permission error; no
-- policy on listing_zones, so nobody reads it.
grant select on public.listing_zones, public.market_stats_runs, public.market_stats to authenticated;
grant all on public.listing_zones, public.market_stats_runs, public.market_stats to service_role;

create policy "market_stats: admin read" on public.market_stats for select to authenticated
  using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "market_stats_runs: admin read" on public.market_stats_runs for select to authenticated
  using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

-- ---------------------------------------------------------------------------
-- Config (editable in /admin/config)
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values ('market_stats', '{
  "mode": "off",
  "write_enabled": false,
  "min_n": {"price": 8, "days": 5},
  "year_band": 2,
  "recompute_weeks": 2,
  "confirm_since": {"mercadolibre": "2026-10-24"},
  "schedule": {"weekday": 1, "hour": "06:00"}
}'::jsonb)
on conflict (key) do nothing;

-- The 8 regions Juan approved (normalization/zone.py DEFAULT_ZONE_MAP; a test
-- keeps both equal). Rules in order, the first that matches wins.
insert into public.app_config (key, value) values ('market_zones', $zones${
  "version": 1,
  "regions": {
    "amba": "AMBA",
    "buenos_aires_resto": "Resto de Buenos Aires",
    "cordoba": "Córdoba",
    "litoral": "Litoral",
    "nea": "NEA",
    "cuyo": "Cuyo",
    "noa": "NOA",
    "patagonia": "Patagonia"
  },
  "rules": [
    {"region": "amba", "province": "02"},
    {"region": "amba", "province": "06", "departments": [
      "Almirante Brown", "Avellaneda", "Berazategui", "Esteban Echeverría", "Ezeiza",
      "Florencio Varela", "General San Martín", "Hurlingham", "Ituzaingó", "José C. Paz",
      "La Matanza", "Lanús", "Lomas de Zamora", "Malvinas Argentinas", "Merlo", "Moreno",
      "Morón", "Quilmes", "San Fernando", "San Isidro", "San Miguel", "Tigre",
      "Tres de Febrero", "Vicente López"]},
    {"region": "buenos_aires_resto", "province": "06"},
    {"region": "cordoba", "province": "14"},
    {"region": "litoral", "province": "82"},
    {"region": "litoral", "province": "30"},
    {"region": "nea", "province": "18"},
    {"region": "nea", "province": "54"},
    {"region": "nea", "province": "22"},
    {"region": "nea", "province": "34"},
    {"region": "cuyo", "province": "50"},
    {"region": "cuyo", "province": "70"},
    {"region": "cuyo", "province": "74"},
    {"region": "noa", "province": "66"},
    {"region": "noa", "province": "90"},
    {"region": "noa", "province": "38"},
    {"region": "noa", "province": "86"},
    {"region": "noa", "province": "10"},
    {"region": "noa", "province": "46"},
    {"region": "patagonia", "province": "58"},
    {"region": "patagonia", "province": "62"},
    {"region": "patagonia", "province": "26"},
    {"region": "patagonia", "province": "78"},
    {"region": "patagonia", "province": "94"},
    {"region": "patagonia", "province": "42"}
  ]
}$zones$::jsonb)
on conflict (key) do nothing;

update public.app_config
   set value = value || '{"market_stats_weeks": 26}'::jsonb
 where key = 'retention' and not value ? 'market_stats_weeks';

notify pgrst, 'reload schema';
