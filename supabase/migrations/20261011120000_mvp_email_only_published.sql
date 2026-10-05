-- Email-only MVP: preserve explicit email opt-outs and historical notifications.
alter table public.profiles alter column default_channels set default '{email}'::text[];
alter table public.search_profiles alter column channels set default '{email}'::text[];
update public.profiles set default_channels = array_remove(array_remove(default_channels, 'web'), 'telegram');
update public.search_profiles set channels = array_remove(array_remove(channels, 'web'), 'telegram');
update public.notifications set status = 'skipped', error = 'channel_removed_from_mvp'
where channel in ('web', 'telegram') and status in ('queued', 'digest');

create or replace function public.search_results(
  p_profile_id bigint, p_filter text default 'all', p_sort text default 'score',
  p_limit integer default 50, p_offset integer default 0
) returns setof public.match_cards language sql stable security invoker set search_path = '' as $$
  with access as (select public.my_plan_snapshot() v), cap as (
    select case when (v->>'enforced')::boolean
      then coalesce((v->'limits'->>'max_visible_results')::int, 2147483647)
      else 2147483647 end n from access
  )
  select c.* from public.match_cards c
  where c.search_profile_id = p_profile_id and case p_filter
    when 'new' then c.status = 'new'
    when 'opportunities' then c.level = 'high' and c.status <> 'discarded'
    when 'saved' then c.saved when 'discarded' then c.status = 'discarded'
    else c.status <> 'discarded' end
  order by case when p_sort = 'score' then c.score end desc nulls last,
    case when p_sort = 'price' then c.price_usd end asc nulls last,
    case when p_sort = 'km' then c.mileage_km end asc nulls last,
    c.published_at desc nulls last, c.listing_id desc
  limit least(greatest(coalesce(p_limit, 50), 0), greatest((select n from cap) - greatest(coalesce(p_offset, 0), 0), 0))
  offset greatest(coalesce(p_offset, 0), 0)
$$;
