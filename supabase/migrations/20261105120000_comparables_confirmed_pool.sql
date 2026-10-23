-- Comparables fase 1 (docs/TECHNICAL_PLAN.md, sección 6.2): a listing that a
-- later complete read no longer saw stops counting as a comparable.
--
-- comparables() only asked for last_seen_at within 30 days, so a car sold or
-- withdrawn kept setting the price reference for up to a month: 2,6% of the
-- pool of the matched listings on 22/10/2026. crawl_targets.last_run_at only
-- moves after a complete run (pipeline/crawl.py → targets.finish_target), and
-- the sources without publication dates read their whole stock within the
-- target's query on every run. So when a target that covers a listing ran
-- more than confirm_grace_hours after the listing was last seen, a complete
-- read looked for it and no longer saw it: the listing is unconfirmed and
-- leaves the pool.
--
-- * Only the sources in app_config.comparables.confirm_sources, whose reads
--   are complete (phase 0, 22/10/2026: kavak cuts at 30 cards, autocosmos
--   returns a truncated "ok" run on a 4xx, usadossantafe's catalog load
--   drops a third of the stock now and then). Without the key, and for any
--   other source (Mercado Libre, Facebook, v6...), the pool stays as it was.
-- * A crawler that stops leaves everything as it was: no later run, no evidence.
-- * A covering target: same source, no body type, and an inventory target or
--   one of the listing's make and model whose query covers its year (± the
--   query's year_band) and km. A null year or km is not covered by a bound.
-- * 'gone' listings keep counting (Juan's decision, 0f348a8): the unset
--   gone_max_age_days can limit them later (0 = never, N = N days after last seen).
-- * A repost counts once its original stops counting, never in the pool of
--   its own original.
--
-- Shape, measured on 22/10/2026 (Postgres 17): a SQL function is only inlined
-- if it has no SET and no SECURITY DEFINER, and a boolean one with an EXISTS
-- never is; a security definer pool called by comparables() was re-planned on
-- every call (4-5x slower). So listing_unconfirmed and comparable_listings are
-- inlinable set-returning functions, comparables() inlines comparable_listings,
-- and comparable_pool is the security definer door for the web: the same pool
-- for the worker's score and the listing page's "autos parecidos".

-- ---------------------------------------------------------------------------
-- listing_unconfirmed: the evidence against one listing
-- ---------------------------------------------------------------------------

-- The ids of the crawl targets whose last complete run covered this listing
-- and came more than p_grace after it was last seen; none when its source is
-- not in p_confirm_sources (app_config.comparables: confirm_sources and
-- confirm_grace_hours). Columns and plain values instead of the row and the
-- config: they would be rebuilt or parsed for every comparable. No SET and
-- qualified names, so the planner inlines it.
create function public.listing_unconfirmed(
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
     and ct.last_run_at > p_last_seen_at + coalesce(p_grace, interval '36 hours')
     and ((ct.make is null and ct.model is null and ct.query->>'inventory' = 'true')
          or (lower(ct.make) = lower(p_make) and lower(ct.model) = lower(p_model)
              and (ct.query->>'year_min' is null
                   or p_year >= (ct.query->>'year_min')::numeric - coalesce((ct.query->>'year_band')::numeric, 0))
              and (ct.query->>'year_max' is null
                   or p_year <= (ct.query->>'year_max')::numeric + coalesce((ct.query->>'year_band')::numeric, 0))
              and (ct.query->>'km_max' is null or p_mileage_km <= (ct.query->>'km_max')::numeric)))
$$;

comment on function public.listing_unconfirmed(text, text, text, integer, integer, timestamptz, jsonb, interval) is
  'Comparables fase 1: the crawl targets whose last complete run covered the listing more than '
  'p_grace after it was last seen, for a source in p_confirm_sources. Non-empty = it no longer counts.';

-- ---------------------------------------------------------------------------
-- comparable_listings: the pool
-- ---------------------------------------------------------------------------

-- Same make and model, year ± year_tol, km ± km_tol_pct, seen in the last
-- max_age_days, no partial prices, never the listing itself, and the rules
-- above. Null parameters read app_config.comparables. Inlinable: comparables()
-- plans it once per query.
create function public.comparable_listings(
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
              and exists (select 1 from public.listing_unconfirmed(o.source, o.make, o.model, o.year, o.mileage_km,
                                                                   o.last_seen_at, cfg.confirm_sources, cfg.grace)))
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
                       and exists (select 1 from public.listing_unconfirmed(x.source, x.make, x.model, x.year,
                                                                            x.mileage_km, x.last_seen_at,
                                                                            cfg.confirm_sources, cfg.grace)))))
$$;

comment on function public.comparable_listings(bigint, integer, numeric, integer) is
  'Comparables (sección 6.2): the pool of comparable listings of a listing, shared by comparables() '
  'and comparable_pool(). Internal: inlined by comparables().';

-- The door for the web (the listing page's "autos parecidos"): the same pool
-- with the caller unable to read crawl_targets or app_config. listings is
-- already readable by authenticated in full ("listings: authenticated read").
create function public.comparable_pool(
  p_listing_id   bigint,
  p_year_tol     integer default null,
  p_km_tol_pct   numeric default null,
  p_max_age_days integer default null
) returns setof public.listings
language sql
stable
security definer
set search_path = ''
as $$
  select * from public.comparable_listings(p_listing_id, p_year_tol, p_km_tol_pct, p_max_age_days)
$$;

comment on function public.comparable_pool(bigint, integer, numeric, integer) is
  'Comparables (sección 6.2): the listings comparables() compares a listing with, for the web.';

-- ---------------------------------------------------------------------------
-- comparables: same signature and result, over comparable_listings
-- ---------------------------------------------------------------------------

create or replace function public.comparables(
  p_listing_id   bigint,
  p_min_n        integer default null,
  p_year_tol     integer default null,
  p_km_tol_pct   numeric default null,
  p_max_age_days integer default null
) returns jsonb
language sql
stable
set search_path = ''
as $$
  with cfg as (
    select coalesce(p_min_n, (c.value->>'min_n')::integer, 5) as min_n
      from (select 1) as one
      left join public.app_config c on c.key = 'comparables'
  ),
  target as (
    select l.* from public.listings l
     where l.id = p_listing_id and l.make is not null and l.model is not null
  ),
  pool as (
    select o.price_usd, o.mileage_km,
           lower(o.trim) = lower(t.trim) and o.transmission = t.transmission as same_trim_transmission,
           o.transmission = t.transmission                                    as same_transmission
      from target t
     cross join public.comparable_listings(p_listing_id, p_year_tol, p_km_tol_pct, p_max_age_days) o
  ),
  levels as (
    select v.rank, v.level_used,
           count(p.price_usd)                                              as n,
           percentile_cont(0.5)  within group (order by p.price_usd)       as median,
           percentile_cont(0.25) within group (order by p.price_usd)       as p25,
           percentile_cont(0.75) within group (order by p.price_usd)       as p75,
           percentile_cont(0.5)  within group (order by p.mileage_km)      as median_km
      from (values (1, 'trim_transmission'), (2, 'transmission'), (3, 'model')) as v (rank, level_used)
      left join pool p
        on case v.rank when 1 then p.same_trim_transmission
                       when 2 then p.same_transmission
                       else true end
     group by v.rank, v.level_used
  )
  select jsonb_build_object(
           'median',     round(lv.median::numeric, 2),
           'p25',        round(lv.p25::numeric, 2),
           'p75',        round(lv.p75::numeric, 2),
           'median_km',  round(lv.median_km::numeric),
           'n',          lv.n,
           'diff_pct',   case when lv.median > 0 and t.price_usd > 0
                              then round((1 - t.price_usd / lv.median::numeric) * 100, 2) end,
           'level_used', lv.level_used)
    from levels lv
   cross join cfg
   cross join target t
   where lv.n >= cfg.min_n or lv.rank = 3
   order by lv.rank
   limit 1
$$;

comment on function public.comparables(bigint, integer, integer, numeric, integer) is
  'Price Intelligence v2 (sección 6.2): median/p25/p75 of comparable_listings() in USD with the '
  'trim+transmission → transmission → model cascade. Stored in matches.price_ref.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

-- comparables keeps its revoke (create or replace keeps privileges). Inlining
-- needs EXECUTE for whoever calls comparables(): the worker (service role).
revoke all on function public.listing_unconfirmed(text, text, text, integer, integer, timestamptz, jsonb, interval),
                       public.comparable_listings(bigint, integer, numeric, integer)
  from public, anon, authenticated;
grant execute on function public.listing_unconfirmed(text, text, text, integer, integer, timestamptz, jsonb, interval),
                          public.comparable_listings(bigint, integer, numeric, integer)
  to service_role;
revoke all on function public.comparable_pool(bigint, integer, numeric, integer) from public, anon;
grant execute on function public.comparable_pool(bigint, integer, numeric, integer) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Config: the initial confirm_sources (phase 0, 22/10/2026) and the grace
-- ---------------------------------------------------------------------------

-- A new database gets the whole row; an existing one keeps its values and
-- gains the two keys. Without confirm_sources nothing is confirmed (rollback:
-- value - 'confirm_sources').
insert into public.app_config (key, value) values
  ('comparables', '{"min_n": 5, "year_tol": 1, "km_tol_pct": 25, "max_age_days": 30, "confirm_grace_hours": 36,
                    "confirm_sources": ["autocity", "carone", "deruedas", "gruporandazzo", "mardelusados", "rosariogarage"]}')
on conflict (key) do update
  set value = public.app_config.value
              || jsonb_build_object('confirm_grace_hours', excluded.value->'confirm_grace_hours',
                                    'confirm_sources',     excluded.value->'confirm_sources');
