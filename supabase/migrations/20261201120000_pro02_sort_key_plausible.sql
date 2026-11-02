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
-- matches without margin) unless the ref is one the web shows: status ok (or
-- none), asking_usd and dealer_median numbers, dealer_median > 0 and
--   min x dealer_median - 0.01 <= asking_usd <= max x dealer_median + 0.01
-- with the ref's own plausible_ratio when it is valid (0 < min < 1 < max, the
-- worker's parse_ratio), else {min: 0.4, max: 3} (margin.PLAUSIBLE_RATIO).
-- app_config.dealer_margin.plausible_ratio is deliberately not read here: the
-- web and the worker's plausible() never read it for a stored ref (a ref from
-- before the guard is judged by the default), so a laxer config would put
-- first a margin the web hides. A ref computed after the guard carries the
-- config's bounds as its own. gross_margin_usd.min that is not a number is
-- null too (the web shows no line for it).
--
-- Same signature, security definer, owner and feature checks and grants as
-- 20261130120000_pro02_margin.sql; search_results is unchanged.
--
-- Rollback: re-apply 20261130120000_pro02_margin.sql's my_margin_sort_keys.

create or replace function public.my_margin_sort_keys(p_profile_id bigint)
returns table (match_id bigint, low numeric)
language sql stable security definer set search_path = '' as $$
  -- n: the ref's numbers, null when not a JSON number (CASE, so a string is
  -- never cast); b: the bounds, its own when valid, else the default.
  select m.id,
         case when n.status_ok and n.median > 0
               and n.asking between b.lo * n.median - 0.01 and b.hi * n.median + 0.01
              then n.low end
    from public.matches m
    join public.search_profiles sp on sp.id = m.search_profile_id
    cross join lateral (
      select coalesce(m.margin_ref->>'status', 'ok') = 'ok' status_ok,
             case when jsonb_typeof(m.margin_ref->'gross_margin_usd'->'min') = 'number'
                  then (m.margin_ref->'gross_margin_usd'->>'min')::numeric end low,
             case when jsonb_typeof(m.margin_ref->'asking_usd') = 'number'
                  then (m.margin_ref->>'asking_usd')::numeric end asking,
             case when jsonb_typeof(m.margin_ref->'dealer_median') = 'number'
                  then (m.margin_ref->>'dealer_median')::numeric end median,
             case when jsonb_typeof(m.margin_ref->'plausible_ratio'->'min') = 'number'
                  then (m.margin_ref->'plausible_ratio'->>'min')::numeric end own_min,
             case when jsonb_typeof(m.margin_ref->'plausible_ratio'->'max') = 'number'
                  then (m.margin_ref->'plausible_ratio'->>'max')::numeric end own_max
    ) n
    cross join lateral (
      select case when own then n.own_min else 0.4 end lo, case when own then n.own_max else 3 end hi
        from (select coalesce(n.own_min > 0 and n.own_min < 1 and n.own_max > 1, false) own) o
    ) b
   where m.search_profile_id = p_profile_id and m.margin_ref is not null
     and sp.user_id = (select auth.uid())
     and (select public.my_plan_feature('dealer_margin'))
$$;

revoke all on function public.my_margin_sort_keys(bigint) from public, anon;
grant execute on function public.my_margin_sort_keys(bigint) to authenticated;

notify pgrst, 'reload schema';
