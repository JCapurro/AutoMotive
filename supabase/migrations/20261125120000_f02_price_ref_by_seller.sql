-- F-02 paso 3 · medianas por tipo de vendedor en price_ref
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem F-02; diseño
-- docs/superpowers/specs/2026-10-30-f02-vendedor-design.md; plan
-- docs/superpowers/plans/2026-10-30-f02-vendedor.md).
--
-- comparables() keeps its signature, its seven keys and every value they had
-- (median, p25, p75, median_km, n, diff_pct, level_used), and adds four over
-- the same pool at the same cascade level:
-- * dealer_n, dealer_median: comparables whose seller is a dealer, said by the
--   source (seller_type = 'dealer') or inferred (dealer_inferred, step 2,
--   migration 20261124120000), even when the listing says 'private';
-- * private_n, private_median: seller_type = 'private' and not inferred.
-- A comparable with no seller type and not inferred is in neither, so
-- dealer_n + private_n <= n. A count is 0 on an empty group and its median
-- null. Nothing in the score reads them (PRO-02 will, with its own minimum).
--
-- No SCORING_VERSION bump: the nightly rescore (14 days) fills them in; older
-- matches keep the seven keys. Requires step 2 (dealer_inferred). Rollback:
-- re-apply the comparables() body of 20261105120000_comparables_confirmed_pool.sql.
--
-- create or replace keeps the grants (revoked from public, anon and
-- authenticated; the service role executes it) and comparable_listings() stays
-- inlined in the pool.

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
           o.transmission = t.transmission                                    as same_transmission,
           coalesce(o.seller_type = 'dealer' or o.dealer_inferred, false)     as is_dealer,
           coalesce(o.seller_type = 'private' and not o.dealer_inferred, false) as is_private
      from target t
     cross join public.comparable_listings(p_listing_id, p_year_tol, p_km_tol_pct, p_max_age_days) o
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
  '(F-02 paso 3; dealer = seller_type dealer or dealer_inferred). Stored in matches.price_ref.';
