-- F1: publication-centered ingestion (docs/TECHNICAL_PLAN.md, secciones 5.1–5.7).
--
-- * Scraping moves from one run per alert to one run per crawl target, so the
--   F0 per-profile cadence column goes away.
-- * Listings resolve make/model through vehicle_catalog and keep the catalog's
--   spelling; comparables look them up case-insensitively.
-- * fetch_detail() has its own queue: a per-source rate limit and a stamp of the
--   last detail check (enrichment and the watchlist refresher share it).

alter table public.search_profiles drop column last_scraped_at;

-- Minimum seconds between two detail pages of the same source (sección 5.5).
alter table public.sources
  add column detail_interval_seconds integer not null default 10
    check (detail_interval_seconds >= 0);

alter table public.listings add column detail_checked_at timestamptz;

comment on column public.listings.enriched_at is
  'First successful fetch_detail() (sección 5.5). Only listings with a match are enriched.';
comment on column public.listings.detail_checked_at is
  'Last fetch_detail() attempt, by enrichment or the watchlist refresher (sección 5.6).';

drop index public.listings_make_model_year_idx;
create index listings_make_model_year_idx on public.listings (lower(make), lower(model), year);
create index listings_last_seen_at_idx on public.listings (last_seen_at desc) where status = 'active';
create index listings_enrich_queue_idx on public.listings (first_seen_at desc)
  where enriched_at is null and status = 'active';
create index listing_snapshots_change_kind_idx on public.listing_snapshots (change_kind, observed_at desc);

-- autocosmos' selectors are alive again (checked 2026-09-27): it joins REGISTRY.
update public.sources set enabled = true where id = 'autocosmos';

update public.sources set detail_interval_seconds = v.seconds
  from (values ('mercadolibre', 8), ('facebook', 30), ('v6', 5), ('kavak', 5), ('autocosmos', 5))
       as v (id, seconds)
 where sources.id = v.id;

insert into public.app_config (key, value) values
  -- sección 5.4: same fingerprint within window_days and price within price_tol_pct.
  ('repost', '{"window_days": 60, "price_tol_pct": 10}'),
  -- sección 5.5: how many listings one enrichment pass takes per source.
  ('enrichment', '{"batch_per_source": 20, "max_age_days": 30}')
on conflict (key) do nothing;
