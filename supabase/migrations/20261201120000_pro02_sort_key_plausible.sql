-- PRO-02, revisión 5: the «Mayor margen estimado» order skips implausible
-- prices (docs/superpowers/specs/2026-11-02-pro02-margen-design.md §13).
--
-- A margin_ref whose asking_usd is outside plausible_ratio x dealer_median is
-- hidden by the web (web/lib/margin-view.ts plausiblePrice) and by the worker
-- (worker/intelligence/margin.py plausible), and the worker recomputes it to
-- null, but only for matches of active listings of searches with access
-- (rescore_queue). The others keep the old ref: without this, in «Guardados»
-- or «Comprados» ordered by margin one below 0.4x (a very high margin) would
-- go first without a line.
--
-- my_margin_sort_keys now returns low = null (last, with few_dealers and the
-- matches without margin) unless the ref is one the web shows (asMarginRef):
-- no status key or status "ok" (a JSON null status is not ok, as in the web
-- and the worker's plausible()); gross_margin_usd.min and .max, dealer_median
-- and dealer_n finite JSON numbers; asking_usd a finite number; and
--   min x dealer_median - 0.01 <= asking_usd <= max x dealer_median + 0.01
-- with the ref's own plausible_ratio when it is valid (0 < min < 1 < max, the
-- worker's parse_ratio), else {min: 0.4, max: 3} (margin.PLAUSIBLE_RATIO).
-- The bounds are compared in double precision, as JS and Python do: in exact
-- numeric a price exactly at a bound to the cent can pass while the web's
-- float comparison rejects it (3 x 23542.57 + 0.01 is 70627.71999999999 in
-- float8, so 70627.72 is outside). A number beyond float8's range is not
-- finite (JSON.parse gives Infinity) and one too small for it is 0, so no
-- cast can fail.
-- app_config.dealer_margin.plausible_ratio is deliberately not read here: the
-- web and the worker's plausible() never read it for a stored ref (a ref from
-- before the guard is judged by the default), so a laxer config would put
-- first a margin the web hides. A ref computed after the guard carries the
-- config's bounds as its own.
--
-- Same signature, security definer, owner and feature checks and grants as
-- 20261130120000_pro02_margin.sql; search_results is unchanged.
--
-- Rollback: re-apply 20261130120000_pro02_margin.sql's my_margin_sort_keys.

create or replace function public.my_margin_sort_keys(p_profile_id bigint)
returns table (match_id bigint, low numeric)
language sql stable security definer set search_path = '' as $$
  -- j: the ref's numbers, null when not a JSON number (CASE, so a string is
  -- never cast) or beyond float8's range (not finite in JS); n: the ones
  -- compared, in float8 (0 below its range, as JSON.parse); b: the bounds,
  -- its own when valid, else the default.
  select m.id,
         case when j.status_ok and j.low is not null and j.high is not null and j.dealer_n is not null
               and n.median > 0
               and b.lo * n.median - 0.01::float8 <= n.asking and n.asking <= b.hi * n.median + 0.01::float8
              then j.low end
    from public.matches m
    join public.search_profiles sp on sp.id = m.search_profile_id
    cross join lateral (
      select not (m.margin_ref ? 'status') or m.margin_ref->'status' = '"ok"'::jsonb status_ok,
             case when jsonb_typeof(m.margin_ref->'gross_margin_usd'->'min') = 'number' then (
               case when abs((m.margin_ref->'gross_margin_usd'->'min')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'gross_margin_usd'->'min')::numeric end) end low,
             case when jsonb_typeof(m.margin_ref->'gross_margin_usd'->'max') = 'number' then (
               case when abs((m.margin_ref->'gross_margin_usd'->'max')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'gross_margin_usd'->'max')::numeric end) end high,
             case when jsonb_typeof(m.margin_ref->'dealer_n') = 'number' then (
               case when abs((m.margin_ref->'dealer_n')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'dealer_n')::numeric end) end dealer_n,
             case when jsonb_typeof(m.margin_ref->'asking_usd') = 'number' then (
               case when abs((m.margin_ref->'asking_usd')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'asking_usd')::numeric end) end asking,
             case when jsonb_typeof(m.margin_ref->'dealer_median') = 'number' then (
               case when abs((m.margin_ref->'dealer_median')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'dealer_median')::numeric end) end median,
             case when jsonb_typeof(m.margin_ref->'plausible_ratio'->'min') = 'number' then (
               case when abs((m.margin_ref->'plausible_ratio'->'min')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'plausible_ratio'->'min')::numeric end) end own_min,
             case when jsonb_typeof(m.margin_ref->'plausible_ratio'->'max') = 'number' then (
               case when abs((m.margin_ref->'plausible_ratio'->'max')::numeric) <= 1.7976931348623157e308 then (m.margin_ref->'plausible_ratio'->'max')::numeric end) end own_max
    ) j
    cross join lateral (
      select case when abs(j.asking) < 1e-300 then 0::float8 else j.asking::float8 end asking,
             case when abs(j.median) < 1e-300 then 0::float8 else j.median::float8 end median,
             case when abs(j.own_min) < 1e-300 then 0::float8 else j.own_min::float8 end own_min,
             case when abs(j.own_max) < 1e-300 then 0::float8 else j.own_max::float8 end own_max
    ) n
    cross join lateral (
      select case when own then n.own_min else 0.4::float8 end lo, case when own then n.own_max else 3::float8 end hi
        from (select coalesce(n.own_min > 0 and n.own_min < 1 and n.own_max > 1, false) own) o
    ) b
   where m.search_profile_id = p_profile_id and m.margin_ref is not null
     and sp.user_id = (select auth.uid())
     and (select public.my_plan_feature('dealer_margin'))
$$;

revoke all on function public.my_margin_sort_keys(bigint) from public, anon;
grant execute on function public.my_margin_sort_keys(bigint) to authenticated;

notify pgrst, 'reload schema';
