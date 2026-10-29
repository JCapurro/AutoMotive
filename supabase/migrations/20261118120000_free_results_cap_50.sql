-- One cumulative quota per account. Keeping all matches lets a paid upgrade
-- unlock them immediately. A listing admitted once never consumes another slot.
set local lock_timeout = '5s';
lock table public.search_profiles, public.matches in share row exclusive mode;
update public.app_config set value = jsonb_set(
  jsonb_set(value, '{free,max_visible_results}', '50'), '{free,max_total_results}', '50')
where key = 'plan_limits';

create table public.free_trial_results (
  user_id uuid not null references public.profiles(id) on delete cascade,
  -- No listing FK: purging an old ad must never replenish the lifetime quota.
  listing_id bigint not null,
  admitted_at timestamptz not null default now(),
  primary key (user_id, listing_id)
);
alter table public.free_trial_results enable row level security;
revoke all on public.free_trial_results from anon, authenticated;
grant select on public.free_trial_results to authenticated;
grant all on public.free_trial_results to service_role;
create policy "free trial results: own usage" on public.free_trial_results
  for select to authenticated using (user_id = (select auth.uid()));

create function public.free_result_limit(p_user uuid) returns integer
language sql stable security definer set search_path = '' as $$
  select case when (a.v->>'enforced')::boolean and a.v->>'plan' = 'free'
    then coalesce((a.v->'limits'->>'max_total_results')::integer, 50) end
  from (select public.plan_limits_for(p_user) v) a
$$;
revoke all on function public.free_result_limit(uuid) from public, anon, authenticated;
grant execute on function public.free_result_limit(uuid) to service_role;

create function public.free_result_allowed(p_user uuid, p_listing bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.free_result_limit(p_user) is null or exists (
    select 1 from public.free_trial_results r where r.user_id = p_user and r.listing_id = p_listing)
$$;
revoke all on function public.free_result_allowed(uuid,bigint) from public, anon, authenticated;
grant execute on function public.free_result_allowed(uuid,bigint) to service_role;

create function public.my_free_result_allowed(p_listing bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and public.free_result_allowed((select auth.uid()), p_listing)
$$;
revoke all on function public.my_free_result_allowed(bigint) from public, anon;
grant execute on function public.my_free_result_allowed(bigint) to authenticated;

create function public.admit_free_result() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_user uuid; v_limit integer;
begin
  select sp.user_id into v_user from public.search_profiles sp where sp.id = new.search_profile_id;
  v_limit := public.free_result_limit(v_user);
  if v_limit is null then return new; end if;
  -- Serialize admissions across every search belonging to this account.
  perform 1 from public.profiles where id = v_user for update;
  if exists (select 1 from public.listings where id = new.listing_id and status = 'active')
    and (select count(*) from public.free_trial_results where user_id = v_user) < v_limit then
    insert into public.free_trial_results(user_id,listing_id) values(v_user,new.listing_id)
      on conflict do nothing;
  end if;
  return new;
end $$;
revoke all on function public.admit_free_result() from public, anon, authenticated;
create trigger matches_admit_free_result after insert or update on public.matches
for each row execute function public.admit_free_result();

-- Existing free accounts begin with at most 50 distinct historical matches;
-- prioritize saved results, then score. The ledger survives search deletion.
insert into public.free_trial_results(user_id,listing_id)
select user_id, listing_id from (
  select d.*, row_number() over(partition by user_id order by saved desc, score desc, listing_id) n
  from (
    select sp.user_id,m.listing_id,max(m.score) score,bool_or(coalesce(i.saved,false)) saved
    from public.matches m join public.search_profiles sp on sp.id=m.search_profile_id
    left join public.user_listing_interactions i on i.user_id=sp.user_id and i.listing_id=m.listing_id
    where public.free_result_limit(sp.user_id) is not null
    group by sp.user_id,m.listing_id
  ) d
) ranked where n <= public.free_result_limit(user_id)
on conflict do nothing;

-- Restrictive policy also covers match_cards, counts, dashboard and alternative
-- filters/orders: requesting another page cannot reveal a different set of 50.
create policy "matches: free cumulative quota" on public.matches as restrictive
  for select to authenticated using (public.my_free_result_allowed(listing_id));

create or replace function public.my_plan_limits() returns jsonb
language sql stable security definer set search_path = '' as $$
  select public.plan_limits_for((select auth.uid())) || jsonb_build_object(
    'free_results_used', (select count(*) from public.free_trial_results where user_id=(select auth.uid())),
    'free_results_limit', public.free_result_limit((select auth.uid())))
$$;

create or replace function public.notification_access_active(p_user uuid, p_search bigint, p_listing bigint)
returns boolean language sql stable security definer set search_path = '' as $$
  select public.commercial_access_active(p_user)
    and (p_listing is null or public.free_result_allowed(p_user,p_listing)) and (
    p_search is null or public.search_access_active(p_search) or exists (
      select 1 from public.user_listing_interactions i where i.user_id=p_user
        and i.listing_id=p_listing and (i.saved or i.status in ('interested','contacted','visit_scheduled'))))
$$;

-- Digest generation uses the worker's privileged connection. Filter the payload
-- on insert AND on the delivery function's payload update (covers queued mail).
create function public.guard_free_result_digest() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_items jsonb;
begin
  if new.kind = 'digest' and public.free_result_limit(new.user_id) is not null then
    select coalesce(jsonb_agg(it.item order by it.ord),'[]'::jsonb) into v_items
    from jsonb_array_elements(coalesce(new.payload->'items','[]'::jsonb)) with ordinality it(item,ord)
    where public.free_result_allowed(new.user_id,(it.item->>'listing_id')::bigint);
    new.payload := new.payload || jsonb_build_object('items',v_items,'degraded',
      (select count(*) from jsonb_array_elements(v_items) it where coalesce(it->>'degraded','') not in ('','false','0')));
    if jsonb_array_length(v_items)=0 then new.status:='skipped'; new.error:='free_result_quota'; end if;
  end if;
  return new;
end $$;
revoke all on function public.guard_free_result_digest() from public, anon, authenticated;
create trigger notifications_free_result_digest before insert or update of payload on public.notifications
for each row execute function public.guard_free_result_digest();

-- Check both availability and the quota immediately before sending queued mail.
create or replace function public.prepare_notification_delivery(p_id bigint) returns boolean
language plpgsql security definer set search_path = '' as $$
declare n public.notifications; v_items jsonb;
begin
  select * into n from public.notifications where id=p_id and status='queued' for update;
  if n.id is null then return false; end if;
  if not public.notification_access_active(n.user_id,n.search_profile_id,n.listing_id) then
    update public.notifications set status='skipped',error='plan_access_expired' where id=p_id;
    return false;
  end if;
  if (n.kind in ('new_match','opportunity') and n.search_profile_id is not null
      and not public.search_access_active(n.search_profile_id))
    or (n.kind='digest' and n.payload->>'commercial_plan' is distinct from public.plan_limits_for(n.user_id)->>'plan') then
    update public.notifications set status='skipped',error='plan_changed' where id=p_id;
    return false;
  end if;
  if n.kind in ('new_match','opportunity','price_drop') and not exists (
    select 1 from public.listings l where l.id=n.listing_id and l.status='active'
  ) then
    update public.notifications set status='skipped',error='listing_unavailable' where id=p_id;
    return false;
  end if;
  if n.kind='digest' then
    select coalesce(jsonb_agg(it.item order by it.ord),'[]'::jsonb) into v_items
    from jsonb_array_elements(coalesce(n.payload->'items','[]'::jsonb)) with ordinality it(item,ord)
    where public.free_result_allowed(n.user_id,(it.item->>'listing_id')::bigint)
      and (it.item->>'section'='gone' or exists (
        select 1 from public.listings l where l.id=(it.item->>'listing_id')::bigint and l.status='active'));
    if jsonb_array_length(v_items)=0 then
      update public.notifications set status='skipped',error='listing_unavailable' where id=p_id;
      return false;
    end if;
    update public.notifications set payload=payload || jsonb_build_object('items',v_items,'degraded',
      (select count(*) from jsonb_array_elements(v_items) it where coalesce(it->>'degraded','') not in ('','false','0')))
    where id=p_id;
  end if;
  if n.kind in ('new_match','opportunity') and public.effective_search_frequency(n.user_id,'immediate')='daily' then
    update public.notifications set status='digest' where id=p_id;
    return false;
  end if;
  return true;
end $$;

notify pgrst, 'reload schema';
