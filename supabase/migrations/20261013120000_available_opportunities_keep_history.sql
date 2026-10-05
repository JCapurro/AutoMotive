-- Only active ads are actionable; ended ads and their price snapshots remain
-- historical market evidence. Keep saved/discarded history accessible.
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
    when 'new' then c.listing_status = 'active' and c.status = 'new'
    when 'opportunities' then c.listing_status = 'active' and c.level = 'high' and c.status <> 'discarded'
    when 'saved' then c.saved when 'discarded' then c.status = 'discarded'
    else c.listing_status = 'active' and c.status <> 'discarded' end
  order by case when p_sort = 'score' then c.score end desc nulls last,
    case when p_sort = 'price' then c.price_usd end asc nulls last,
    case when p_sort = 'km' then c.mileage_km end asc nulls last,
    coalesce(c.published_at, c.first_seen_at) desc nulls last, c.listing_id desc
  limit least(greatest(coalesce(p_limit, 50), 0), greatest((select n from cap) - greatest(coalesce(p_offset, 0), 0), 0))
  offset greatest(coalesce(p_offset, 0), 0)
$$;

create or replace function public.search_result_counts(p_profile_id bigint)
returns table (new_count integer, opportunities_count integer, all_count integer,
               saved_count integer, discarded_count integer)
language sql stable security invoker set search_path = '' as $$
  select (count(*) filter (where c.listing_status = 'active' and c.status = 'new'))::integer,
         (count(*) filter (where c.listing_status = 'active' and c.level = 'high' and c.status <> 'discarded'))::integer,
         (count(*) filter (where c.listing_status = 'active' and c.status <> 'discarded'))::integer,
         (count(*) filter (where c.saved))::integer,
         (count(*) filter (where c.status = 'discarded'))::integer
    from public.match_cards c
   where c.search_profile_id = p_profile_id
$$;

create or replace function public.dashboard_summary()
returns table (
  profile_id bigint, name text, enabled boolean, filters jsonb,
  notification_frequency public.notify_frequency, pending boolean,
  new_this_week integer, opportunities_this_week integer, total integer, unseen integer
)
language sql stable security invoker set search_path = '' as $$
  select sp.id, sp.name, sp.enabled, sp.filters, sp.notification_frequency,
         sp.bootstrapped_at is null or sp.rematch_requested_at is not null,
         (count(*) filter (where c.status <> 'discarded' and c.generated_at >= now() - interval '7 days'))::integer,
         (count(*) filter (where c.status <> 'discarded' and c.generated_at >= now() - interval '7 days'
                             and c.level = 'high'))::integer,
         (count(*) filter (where c.status <> 'discarded'))::integer,
         (count(*) filter (where c.status = 'new'))::integer
    from public.search_profiles sp
    left join public.match_cards c on c.search_profile_id = sp.id and c.listing_status = 'active'
   where sp.user_id = (select auth.uid())
   group by sp.id
   order by sp.enabled desc, sp.created_at desc
$$;

-- Preserve ended ads indefinitely, including their cascading snapshots/matches.
-- Retention still removes untouched stale active inventory under the same rules.
create or replace function public.purge_stale_listings(p_days integer default null)
returns integer language plpgsql security invoker set search_path = '' as $$
declare
  v_days integer := coalesce(
    p_days,
    (select (value ->> 'listing_days')::integer from public.app_config where key = 'retention'),
    180);
  v_deleted integer;
begin
  if v_days < 30 then
    raise exception 'retention below 30 days (%): refusing', v_days;
  end if;
  with doomed as (
    select l.id from public.listings l
     where l.status = 'active' and l.last_seen_at < now() - make_interval(days => v_days)
       and not exists (select 1 from public.user_listing_interactions i where i.listing_id = l.id)
       and not exists (select 1 from public.notifications n where n.listing_id = l.id)
       and not exists (select 1 from public.owned_vehicles o where o.listing_id = l.id)
  ), deleted as (
    delete from public.listings l using doomed d where l.id = d.id returning 1
  )
  select count(*) into v_deleted from deleted;
  return v_deleted;
end;
$$;

-- Check availability at dispatch as well: an ad may end after it was queued.
-- Existing access checks and worker-only grants are preserved by OR REPLACE.
create or replace function public.prepare_notification_delivery(p_id bigint) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  n public.notifications;
  v_items jsonb;
begin
  select * into n from public.notifications where id = p_id and status = 'queued' for update;
  if n.id is null then return false; end if;
  if not public.notification_access_active(n.user_id, n.search_profile_id, n.listing_id) then
    update public.notifications set status = 'skipped', error = 'plan_access_expired' where id = p_id;
    return false;
  end if;
  if (n.kind in ('new_match','opportunity') and n.search_profile_id is not null
      and not public.search_access_active(n.search_profile_id))
    or (n.kind = 'digest' and n.payload->>'commercial_plan' is distinct from public.plan_limits_for(n.user_id)->>'plan') then
    update public.notifications set status = 'skipped', error = 'plan_changed' where id = p_id;
    return false;
  end if;
  if n.kind in ('new_match','opportunity','price_drop') and not exists (
    select 1 from public.listings l where l.id = n.listing_id and l.status = 'active'
  ) then
    update public.notifications set status = 'skipped', error = 'listing_unavailable' where id = p_id;
    return false;
  end if;
  if n.kind = 'digest' then
    select coalesce(jsonb_agg(it.item order by it.ord), '[]'::jsonb) into v_items
      from jsonb_array_elements(coalesce(n.payload->'items', '[]'::jsonb)) with ordinality it(item, ord)
     where it.item->>'section' = 'gone' or exists (
       select 1 from public.listings l
        where l.id = (it.item->>'listing_id')::bigint and l.status = 'active'
     );
    if jsonb_array_length(v_items) = 0 then
      update public.notifications set status = 'skipped', error = 'listing_unavailable' where id = p_id;
      return false;
    end if;
    update public.notifications
       set payload = payload || jsonb_build_object('items', v_items, 'degraded',
         (select count(*) from jsonb_array_elements(v_items) it
           where coalesce(it->>'degraded', '') not in ('', 'false', '0')))
     where id = p_id;
  end if;
  if n.kind in ('new_match', 'opportunity') and public.effective_search_frequency(n.user_id, 'immediate') = 'daily' then
    update public.notifications set status = 'digest' where id = p_id;
    return false;
  end if;
  return true;
end;
$$;

notify pgrst, 'reload schema';
