-- Precios absurdos fuera de la referencia de precio (auditoría de anticipos,
-- 2026-11-13).
--
-- comparables() took every price comparable_listings() returned. A dealer that
-- publishes down payments as prices can then be the reference itself: a 2024
-- Polo Track at $3.499.999 got a median of USD 3.236 because 7 of its 11
-- comparables were that dealer's anticipos, so the 65% guard (scoring.py)
-- compared an anticipo against anticipos and let it through. Fillers like
-- «USD 1.111» pulled medians down the same way.
--
-- Now a comparable below floor_of_p75 × the p75 of the whole pool (model
-- level, before the cascade) is left out of every level. The p75 and not the
-- median: the median is already an anticipo when they are most of the pool;
-- the p75 holds while they are under three quarters of it. 0.35 mirrors the
-- 65% guard: a price that far below is not a total. Tunable in
-- app_config.comparables.floor_of_p75 (0 turns it off).
--
-- Same signature, keys and grants as 20261125120000_f02_price_ref_by_seller.sql;
-- only the pool changes. No SCORING_VERSION bump: the nightly rescore refills
-- matches.price_ref. comparable_pool() (the listing page's list) is untouched.
-- Rollback: re-apply the comparables() body of
-- 20261125120000_f02_price_ref_by_seller.sql.

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
    select coalesce(p_min_n, (c.value->>'min_n')::integer, 5) as min_n,
           coalesce((c.value->>'floor_of_p75')::numeric, 0.35) as floor_of_p75
      from (select 1) as one
      left join public.app_config c on c.key = 'comparables'
  ),
  target as (
    select l.* from public.listings l
     where l.id = p_listing_id and l.make is not null and l.model is not null
  ),
  raw as (
    select o.price_usd, o.mileage_km,
           lower(o.trim) = lower(t.trim) and o.transmission = t.transmission as same_trim_transmission,
           o.transmission = t.transmission                                    as same_transmission,
           coalesce(o.seller_type = 'dealer' or o.dealer_inferred, false)     as is_dealer,
           coalesce(o.seller_type = 'private' and not o.dealer_inferred, false) as is_private
      from target t
     cross join public.comparable_listings(p_listing_id, p_year_tol, p_km_tol_pct, p_max_age_days) o
  ),
  price_floor as (
    select cfg.floor_of_p75 * percentile_cont(0.75) within group (order by raw.price_usd) as min_usd
      from raw cross join cfg
     group by cfg.floor_of_p75
  ),
  pool as (
    select raw.* from raw
      left join price_floor on true
     where price_floor.min_usd is null or raw.price_usd >= price_floor.min_usd
  ),
  levels as (
    select v.rank, v.level_used,
           count(p.price_usd)                                              as n,
           percentile_cont(0.5)  within group (order by p.price_usd)       as median,
           percentile_cont(0.25) within group (order by p.price_usd)       as p25,
           percentile_cont(0.75) within group (order by p.price_usd)       as p75,
           percentile_cont(0.5)  within group (order by p.mileage_km)      as median_km,
           count(p.price_usd) filter (where p.is_dealer)                   as dealer_n,
           percentile_cont(0.5)  within group (order by p.price_usd) filter (where p.is_dealer)  as dealer_median,
           count(p.price_usd) filter (where p.is_private)                  as private_n,
           percentile_cont(0.5)  within group (order by p.price_usd) filter (where p.is_private) as private_median
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
           'level_used', lv.level_used,
           'dealer_median',  round(lv.dealer_median::numeric, 2),
           'dealer_n',       lv.dealer_n,
           'private_median', round(lv.private_median::numeric, 2),
           'private_n',      lv.private_n)
    from levels lv
   cross join cfg
   cross join target t
   where lv.n >= cfg.min_n or lv.rank = 3
   order by lv.rank
   limit 1
$$;

comment on function public.comparables(bigint, integer, integer, numeric, integer) is
  'Price Intelligence v2 (sección 6.2): median/p25/p75 of comparable_listings() in USD with the '
  'trim+transmission → transmission → model cascade, plus dealer/private n and median at the chosen level '
  '(F-02 paso 3; dealer = seller_type dealer or dealer_inferred). Comparables below '
  'app_config.comparables.floor_of_p75 (default 0.35) × the pool''s p75 are left out. Stored in matches.price_ref.';
