-- F2: intelligence (docs/TECHNICAL_PLAN.md, sección 6).
--
-- * public.comparables(listing_id): Price Intelligence v2 with the specificity
--   cascade (sección 6.2). The worker stores its result in matches.price_ref.
-- * vehicle_catalog.timing_belt: models with a timing belt, for the
--   no_timing_belt red flag (sección 6.5).
-- * app_config: score curves, red flag thresholds and the nightly re-score.

-- ---------------------------------------------------------------------------
-- Comparables
-- ---------------------------------------------------------------------------

-- Same make and model, year ± year_tol, km ± km_tol_pct, seen in the last
-- max_age_days, no partial prices, no probable reposts, never the listing
-- itself; everything in price_usd. The cascade takes the first level with
-- n ≥ min_n:
--   1. same trim and same transmission   'trim_transmission'
--   2. same transmission                 'transmission'
--   3. the model only                    'model'
-- and falls back to 'model' (with its small n) when none gets there, so the
-- caller can say "sin comparables suficientes (n=…)". Null parameters read
-- app_config.comparables. Returns
--   {median, p25, p75, median_km, n, diff_pct, level_used}
-- with diff_pct = % below the median (positive = cheaper), or null if the
-- listing doesn't exist or has no make/model.
create function public.comparables(
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
    select coalesce(p_min_n,        (c.value->>'min_n')::integer,        5)  as min_n,
           coalesce(p_year_tol,     (c.value->>'year_tol')::integer,     1)  as year_tol,
           coalesce(p_km_tol_pct,   (c.value->>'km_tol_pct')::numeric,   25) as km_tol_pct,
           coalesce(p_max_age_days, (c.value->>'max_age_days')::integer, 30) as max_age_days
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
     cross join cfg
      join public.listings o
        on lower(o.make) = lower(t.make) and lower(o.model) = lower(t.model)
     where o.id <> t.id
       and o.price_usd > 0
       and not o.price_partial
       and o.probable_repost_of is null
       and o.last_seen_at >= now() - make_interval(days => cfg.max_age_days)
       and (t.year is null or o.year between t.year - cfg.year_tol and t.year + cfg.year_tol)
       and (t.mileage_km is null or o.mileage_km is null
            or o.mileage_km between t.mileage_km * (1 - cfg.km_tol_pct / 100)
                                and t.mileage_km * (1 + cfg.km_tol_pct / 100))
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
  'Price Intelligence v2 (sección 6.2): median/p25/p75 of comparable listings in USD with the '
  'trim+transmission → transmission → model cascade. Stored in matches.price_ref.';

-- Only the worker (service role / postgres) computes comparables.
revoke execute on function public.comparables(bigint, integer, integer, numeric, integer) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Catalog: timing belt
-- ---------------------------------------------------------------------------

alter table public.vehicle_catalog add column timing_belt boolean;
comment on column public.vehicle_catalog.timing_belt is
  'The model''s usual engines use a timing belt (true), a chain (false) or unknown (null). '
  'Only true raises the no_timing_belt red flag (sección 6.5).';

-- Same list as seed.sql (which runs after migrations on `supabase db reset`).
update public.vehicle_catalog c set timing_belt = v.belt
  from (values
    ('Volkswagen', 'Gol', true), ('Volkswagen', 'Gol Trend', true), ('Volkswagen', 'Suran', true),
    ('Volkswagen', 'Fox', true), ('Volkswagen', 'Saveiro', true), ('Volkswagen', 'Up', true),
    ('Ford', 'Fiesta', true), ('Ford', 'Ka', true), ('Ford', 'Focus', true), ('Ford', 'EcoSport', true),
    ('Chevrolet', 'Corsa', true), ('Chevrolet', 'Classic', true), ('Chevrolet', 'Agile', true),
    ('Chevrolet', 'Prisma', true), ('Chevrolet', 'Onix', true), ('Chevrolet', 'Spin', true),
    ('Renault', 'Clio', true), ('Renault', 'Sandero', true), ('Renault', 'Stepway', true),
    ('Renault', 'Logan', true), ('Renault', 'Kangoo', true), ('Renault', 'Duster', true),
    ('Fiat', 'Palio', true), ('Fiat', 'Siena', true), ('Fiat', 'Uno', true), ('Fiat', 'Punto', true),
    ('Peugeot', '206', true), ('Peugeot', '207', true), ('Peugeot', '208', true),
    ('Peugeot', 'Partner', true), ('Citroën', 'C3', true), ('Citroën', 'Berlingo', true),
    ('Toyota', 'Corolla', false), ('Toyota', 'Etios', false), ('Toyota', 'Yaris', false),
    ('Toyota', 'Hilux', false), ('Toyota', 'SW4', false), ('Honda', 'Civic', false),
    ('Honda', 'Fit', false), ('Honda', 'City', false), ('Honda', 'HR-V', false)
  ) as v (make, model, belt)
 where c.make = v.make and c.model = v.model and c.trim is null;

-- ---------------------------------------------------------------------------
-- app_config (Apéndice A)
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  -- sección 6.3: the curve of each score component.
  ('score_curves', '{
     "price":        {"base": 0.5, "pct_per_unit": 20},
     "match":        {"unknown_penalty": 0.15},
     "km":           {"base": 0.5, "slope": 1.25},
     "trim":         {"preferred": 1, "unknown": 0.5, "other": 0.2, "no_preference": 1},
     "recency":      {"half_life_hours": 24},
     "completeness": {"min_description_chars": 150, "min_images": 3},
     "guards":       {"suspicious_pct": 50, "partial_pct": 65}
   }'),
  -- sección 6.5
  ('red_flags', '{"much_cheaper_pct": 25, "anticipo_pct": 50, "min_km_per_year": 5000, "min_description_chars": 150}'),
  -- sección 6.1: nightly re-score of the matches of the last `days`, at `hour` (ART).
  ('rescore', '{"days": 14, "hour": "04:00"}')
on conflict (key) do nothing;
