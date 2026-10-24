-- Comparables fase 2 (docs/TECHNICAL_PLAN.md, sección 6.2): Mercado Libre's
-- sold cars stop counting too.
--
-- Fase 1 (20261105120000) drops a listing once a later complete read of a
-- target covering it no longer saw it. Its evidence was
-- crawl_targets.last_run_at, which on the sources without publication dates
-- is a read of the target's whole stock. On Mercado Libre it is not: a run
-- reads what was published in a window ("Publicados hoy"), so an older ad is
-- never looked for again, and a car sold after it was stored kept setting the
-- price reference for 30 days. Mercado Libre is the biggest part of the pool
-- (3.657 of 10.000 listings seen in 30 days, on 24/10/2026).
--
-- The worker now reads the whole stock of each Mercado Libre target every
-- couple of days (pipeline/crawl.py → MercadoLibreScraper.full_read) and
-- writes:
-- * crawl_targets.last_full_read_at: when the target's last read of its whole
--   stock started. On the other sources it moves with last_run_at (finish_target,
--   full_read); this migration copies last_run_at into it. It is the evidence
--   now, instead of last_run_at.
-- * listings.last_full_seen_at: when such a read last saw the listing. It is
--   not last_seen_at: that one keeps saying when a run stored the listing, so
--   the 30 days of max_age_days and everything else that reads it stay as
--   they were. A full read only vouches for what it saw, it adds nothing to
--   the pool.
--
-- A listing is unconfirmed when a covering target's last_full_read_at came
-- more than confirm_grace_hours after the later of its last_seen_at and
-- last_full_seen_at. 'mercadolibre' joins confirm_sources: until its targets
-- finish a full read, last_full_read_at is null and nothing changes.

alter table public.crawl_targets add column last_full_read_at timestamptz;
alter table public.listings add column last_full_seen_at timestamptz;

comment on column public.crawl_targets.last_full_read_at is
  'Comparables fase 2: when the last read of the target''s whole stock started (Mercado Libre: '
  'MercadoLibreScraper.full_read; other sources: every complete run). The evidence of listing_unconfirmed.';
comment on column public.listings.last_full_seen_at is
  'Comparables fase 2: when a read of a target''s whole stock last saw the listing (Mercado Libre).';

-- The evidence fase 1 had, so that nothing comes back to the pool at deploy.
-- Without the updated_at trigger: an inactive target's updated_at says since
-- when it is inactive (targets.REACTIVATION_IDLE_SECONDS).
alter table public.crawl_targets disable trigger crawl_targets_set_updated_at;
update public.crawl_targets
   set last_full_read_at = last_run_at
 where source not in ('mercadolibre', 'facebook') and last_run_at is not null;
alter table public.crawl_targets enable trigger crawl_targets_set_updated_at;

-- ---------------------------------------------------------------------------
-- listing_unconfirmed: same signature, last_full_read_at as the evidence
-- ---------------------------------------------------------------------------

-- p_last_seen_at is the later of the listing's last_seen_at and
-- last_full_seen_at (comparable_listings).
create or replace function public.listing_unconfirmed(
  p_source          text,
  p_make            text,
  p_model           text,
  p_year            integer,
  p_mileage_km      integer,
  p_last_seen_at    timestamptz,
  p_confirm_sources jsonb,
  p_grace           interval
) returns setof bigint
language sql
stable
as $$
  select ct.id
    from public.crawl_targets ct
   where coalesce(p_confirm_sources, '[]'::jsonb) ? p_source
     and ct.source = p_source
     and ct.body_type is null
     and ct.last_full_read_at > p_last_seen_at + coalesce(p_grace, interval '36 hours')
     and ((ct.make is null and ct.model is null and ct.query->>'inventory' = 'true')
          or (lower(ct.make) = lower(p_make) and lower(ct.model) = lower(p_model)
              and (ct.query->>'year_min' is null
                   or p_year >= (ct.query->>'year_min')::numeric - coalesce((ct.query->>'year_band')::numeric, 0))
              and (ct.query->>'year_max' is null
                   or p_year <= (ct.query->>'year_max')::numeric + coalesce((ct.query->>'year_band')::numeric, 0))
              and (ct.query->>'km_max' is null or p_mileage_km <= (ct.query->>'km_max')::numeric)))
$$;

comment on function public.listing_unconfirmed(text, text, text, integer, integer, timestamptz, jsonb, interval) is
  'Comparables fases 1 y 2: the crawl targets whose last read of their whole stock covered the listing more '
  'than p_grace after it was last seen, for a source in p_confirm_sources. Non-empty = it no longer counts.';

-- ---------------------------------------------------------------------------
-- comparable_listings: the same pool, seen = the later of the two
-- ---------------------------------------------------------------------------

create or replace function public.comparable_listings(
  p_listing_id   bigint,
  p_year_tol     integer default null,
  p_km_tol_pct   numeric default null,
  p_max_age_days integer default null
) returns setof public.listings
language sql
stable
as $$
  -- Materialized: read once per call, not once per comparable.
  with cfg as materialized (
    select coalesce(p_year_tol,     (c.value->>'year_tol')::integer,     1)  as year_tol,
           coalesce(p_km_tol_pct,   (c.value->>'km_tol_pct')::numeric,   25) as km_tol_pct,
           coalesce(p_max_age_days, (c.value->>'max_age_days')::integer, 30) as max_age_days,
           (c.value->>'gone_max_age_days')::integer                        as gone_days,
           coalesce(c.value->'confirm_sources', '[]'::jsonb)                 as confirm_sources,
           coalesce((c.value->>'confirm_grace_hours')::numeric, 36) * interval '1 hour' as grace
      from (select 1) as one
      left join public.app_config c on c.key = 'comparables'
  )
  select o.*
    from public.listings t
   cross join cfg
    join public.listings o
      on lower(o.make) = lower(t.make) and lower(o.model) = lower(t.model)
   where t.id = p_listing_id and t.make is not null and t.model is not null
     and o.id <> t.id
     and o.price_usd > 0
     and not o.price_partial
     and o.last_seen_at >= now() - make_interval(days => cfg.max_age_days)
     and (t.year is null or o.year between t.year - cfg.year_tol and t.year + cfg.year_tol)
     and (t.mileage_km is null or o.mileage_km is null
          or o.mileage_km between t.mileage_km * (1 - cfg.km_tol_pct / 100)
                              and t.mileage_km * (1 + cfg.km_tol_pct / 100))
     and (o.status = 'active' or cfg.gone_days is null
          or o.last_seen_at >= now() - make_interval(days => cfg.gone_days))
     -- The source test first, and not a bare NOT EXISTS: the planner would turn
     -- that into an anti join that reads crawl_targets for every comparable
     -- (3x slower in prod on 22/10/2026); this way only confirm_sources pay.
     and not (cfg.confirm_sources ? o.source
              and exists (select 1 from public.listing_unconfirmed(
                            o.source, o.make, o.model, o.year, o.mileage_km,
                            greatest(o.last_seen_at, o.last_full_seen_at), cfg.confirm_sources, cfg.grace)))
     and o.probable_repost_of is distinct from t.id
     -- A repost (find_repost_of points at the root) is the same car as its
     -- original: it counts only while the original does not.
     and (o.probable_repost_of is null or not exists (
           select 1
             from public.listings x
            where x.id = o.probable_repost_of
              and x.price_usd > 0
              and not x.price_partial
              and x.last_seen_at >= now() - make_interval(days => cfg.max_age_days)
              and (x.status = 'active' or cfg.gone_days is null
                   or x.last_seen_at >= now() - make_interval(days => cfg.gone_days))
              and not (cfg.confirm_sources ? x.source
                       and exists (select 1 from public.listing_unconfirmed(
                                     x.source, x.make, x.model, x.year, x.mileage_km,
                                     greatest(x.last_seen_at, x.last_full_seen_at),
                                     cfg.confirm_sources, cfg.grace)))))
$$;

-- ---------------------------------------------------------------------------
-- Config: Mercado Libre joins confirm_sources
-- ---------------------------------------------------------------------------

-- Only where the key is set: without it nothing is confirmed (the rollback,
-- value - 'confirm_sources'), and this must not turn it back on.
update public.app_config
   set value = jsonb_set(value, '{confirm_sources}', (value->'confirm_sources') || '["mercadolibre"]'::jsonb)
 where key = 'comparables'
   and jsonb_typeof(value->'confirm_sources') = 'array'
   and not (value->'confirm_sources') ? 'mercadolibre';
