-- PAR-02 (resto) · Duplicados entre publicaciones y hash de fotos
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PAR-02; diseño
-- docs/superpowers/specs/2026-11-02-par02-resto-design.md, decisiones 2, 5, 8 y 9).
--
-- Nothing a user sees changes until the worker writes pairs, and no score
-- moves: no user RLS, no function, no SCORING_VERSION.
-- * listing_duplicates: a pair of listings that look like the same car, one
--   row each way (decision 2). kind: duplicate_photos | cross_source_photos |
--   cross_source_data; shown = false is the shadow mode (stored and counted,
--   never shown). Written only by the worker (pipeline/risk_duplicates.py).
-- * photo_hash_runs: the daily download budget of the photo hash (decision 5),
--   the same ledger pattern as description_llm_runs. Off by default.
-- * app_config.risk: the new keys (photo_hash_count, phash_max_distance,
--   photo_hash, cross_source, signals), each only when missing, so
--   checklist_enabled, links and anything tuned in /admin/config stay.
-- * app_config.red_flags.order: the email's priority of red flags (decision 8),
--   only when missing.
-- The web of main reads none of this: it works with or without the migration.

set local lock_timeout = '5s';

-- Inside DO: the Supabase CLI applies a file outside a transaction block, where a
-- bare LOCK TABLE fails. Applied in a transaction (production), it holds until commit.
do $$ begin
  lock table public.app_config in share row exclusive mode;
end $$;

create table public.listing_duplicates (
  listing_id     bigint not null references public.listings(id) on delete cascade,
  other_id       bigint not null references public.listings(id) on delete cascade,
  kind           text not null check (kind in ('duplicate_photos', 'cross_source_photos', 'cross_source_data')),
  shown          boolean not null,
  photo_distance smallint check (photo_distance between 0 and 64),
  evidence       jsonb not null default '{}'::jsonb,
  detected_at    timestamptz not null default now(),
  primary key (listing_id, other_id),
  check (listing_id <> other_id)
);

create index listing_duplicates_other_id_idx on public.listing_duplicates (other_id);

comment on table public.listing_duplicates is
  'PAR-02: two listings that look like the same car (worker: pipeline/risk_duplicates.py), one row each way. '
  'shown = false is shadow mode: stored and measured, never shown.';

-- No policy: only the service role (the worker) reads and writes it.
alter table public.listing_duplicates enable row level security;
revoke all on public.listing_duplicates from public, anon, authenticated;
grant all on public.listing_duplicates to service_role;

create table public.photo_hash_runs (
  id               bigint generated always as identity primary key,
  listing_id       bigint references public.listings(id) on delete set null,
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  images_requested smallint not null check (images_requested between 0 and 10),
  images_hashed    smallint,
  error            text
);

create index photo_hash_runs_started_at_idx on public.photo_hash_runs (started_at);

comment on table public.photo_hash_runs is
  'PAR-02: each download of a listing''s first photos for the photo hash; the rolling 24 h sum of '
  'images_requested is capped by app_config.risk.photo_hash.daily_image_cap (worker: pipeline/photo_hash.py).';

alter table public.photo_hash_runs enable row level security;
revoke all on public.photo_hash_runs from public, anon, authenticated;
grant all on public.photo_hash_runs to service_role;

-- The new risk keys, each one only when missing (a value tuned in /admin/config stays).
update public.app_config c
   set value = jsonb_build_object(
         'photo_hash_count', 3,
         'phash_max_distance', 6,
         'photo_hash', jsonb_build_object(
           'enabled', false, 'daily_image_cap', 600, 'max_attempts', 2, 'max_bytes', 2000000,
           'timeout_seconds', 10, 'per_host_interval_seconds', 1, 'common_min_sellers', 3,
           'skip_sources', jsonb_build_array('facebook', 'instagram')),
         'cross_source', jsonb_build_object(
           'km_tol_pct', 3, 'price_tol_pct', 5, 'data_min_km', 10000, 'data_max_dist_km', 50),
         'signals', jsonb_build_object(
           'private_many_listings', 'on', 'cross_source_photos', 'on',
           'cross_source_data', 'shadow', 'duplicate_photos', 'on')
       ) || c.value
 where c.key = 'risk'
   and jsonb_typeof(c.value) = 'object';

insert into public.app_config(key, value) values
  ('risk', '{"checklist_enabled": true, "links": {"dnrpa": null, "patentes": [], "infracciones": [], "vtv": null, "form_08": null},
    "photo_hash_count": 3, "phash_max_distance": 6,
    "photo_hash": {"enabled": false, "daily_image_cap": 600, "max_attempts": 2, "max_bytes": 2000000,
                   "timeout_seconds": 10, "per_host_interval_seconds": 1, "common_min_sellers": 3,
                   "skip_sources": ["facebook", "instagram"]},
    "cross_source": {"km_tol_pct": 3, "price_tol_pct": 5, "data_min_km": 10000, "data_max_dist_km": 50},
    "signals": {"private_many_listings": "on", "cross_source_photos": "on", "cross_source_data": "shadow", "duplicate_photos": "on"}}')
on conflict (key) do nothing;

update public.app_config
   set value = value || jsonb_build_object('order', jsonb_build_array(
         'duplicate_photos', 'much_cheaper', 'partial_price_suspect', 'private_many_listings',
         'cross_source_duplicate', 'no_owners', 'service_unavailable', 'no_service', 'timing_pending',
         'no_timing_belt', 'short_description', 'damage_mentioned', 'commercial_use', 'vtv_pending',
         'low_km_for_age', 'repost', 'price_mismatch', 'year_mismatch', 'km_mismatch'))
 where key = 'red_flags'
   and jsonb_typeof(value) = 'object'
   and not (value ? 'order');
