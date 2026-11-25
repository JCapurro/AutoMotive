-- Trim blando (docs/TRIM_BLANDO.md). Juan, 2026-11-24: option A.
--
-- A search that names a version without demanding it (filters.trims, no trim_strict) alerts no car of another
-- version: the worker caps its level at `match` while app_config.trim_soft_cap.enabled is true (it is false here:
-- inert). The car stays in the list, but after the versions asked for: the worker writes
-- matches.score_breakdown.trim_cap = true and search_results, for the default order (p_sort = 'score'), puts
-- those after the rest. The card says «Otra versión» from the same mark.
--
-- search_results is 20261130120000's with one more leading order key. Without the mark (the switch off, every
-- row of today) the key is 0 for all and the order is exactly the one before.
set local lock_timeout = '5s';

insert into public.app_config(key, value)
values ('trim_soft_cap', jsonb_build_object('enabled', false))
on conflict (key) do nothing;

create or replace function public.search_results(
  p_profile_id bigint, p_filter text default 'all', p_sort text default 'score',
  p_limit integer default 50, p_offset integer default 0
) returns setof public.match_cards language sql stable security invoker set search_path = '' as $$
  with access as (select public.my_plan_snapshot() v), cap as (
    select case when (v->>'enforced')::boolean
      then coalesce((v->'limits'->>'max_visible_results')::int, 2147483647)
      else 2147483647 end n from access
  ), margin_access as (
    select p_sort = 'margin' and public.my_plan_feature('dealer_margin') ok
  ), margins as (
    select k.match_id, k.low from public.my_margin_sort_keys(p_profile_id) k where (select ok from margin_access)
  )
  select c.* from public.match_cards c
  left join margins mg on mg.match_id = c.match_id
  left join public.matches mt on mt.id = c.match_id
  where c.search_profile_id = p_profile_id and case p_filter
    when 'new' then c.listing_status = 'active' and c.status = 'new'
    when 'opportunities' then c.listing_status = 'active' and c.level = 'high' and c.status <> 'discarded'
    when 'saved' then c.saved when 'discarded' then c.status = 'discarded'
    when 'contacted' then c.status = 'contacted'
    when 'visit_scheduled' then c.status = 'visit_scheduled'
    when 'purchased' then c.status = 'purchased'
    else c.listing_status = 'active' and c.status <> 'discarded' end
  order by case when p_sort = 'score' and mt.score_breakdown ->> 'trim_cap' = 'true' then 1 else 0 end,
    case when p_sort = 'score' then c.score end desc nulls last,
    case when (select ok from margin_access) then mg.low end desc nulls last,
    case when p_sort = 'price' then c.price_usd end asc nulls last,
    case when p_sort = 'km' then c.mileage_km end asc nulls last,
    coalesce(c.published_at, c.first_seen_at) desc nulls last, c.listing_id desc
  limit least(greatest(coalesce(p_limit, 50), 0), greatest((select n from cap) - greatest(coalesce(p_offset, 0), 0), 0))
  offset greatest(coalesce(p_offset, 0), 0)
$$;

notify pgrst, 'reload schema';
