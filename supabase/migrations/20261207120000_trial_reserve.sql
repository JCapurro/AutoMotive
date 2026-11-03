-- Prueba gratis, paso 1 (docs/PRUEBA_HONESTA.md).
-- 1. Reserve: with app_config.trial_reserve on, what was already published
--    takes at most backfill_max of the trial's results; the rest stays for
--    listings new during the trial. It ships off: off, admission is today's.
-- 2. Honest counts: the welcome and trial-end emails count what the trial
--    shows, and say how many matches it hides; the search page asks the same.
set local lock_timeout = '5s';

-- Whether the admitted result was stock (already published) or new. Null:
-- admitted before this column, counted as stock.
alter table public.free_trial_results add column is_backfill boolean;

insert into public.app_config(key, value)
values ('trial_reserve', jsonb_build_object('enabled', false, 'backfill_max', 30))
on conflict (key) do nothing;

-- The reserve's stock cap, or null when it's off: no row, enabled not true,
-- or backfill_max not a number from 0 (any broken value is off).
create function public.trial_reserve_backfill_max() returns integer
language plpgsql stable security definer set search_path = '' as $$
declare v jsonb;
begin
  select value into v from public.app_config where key = 'trial_reserve';
  if v is null or v->'enabled' is distinct from 'true'::jsonb
     or jsonb_typeof(v->'backfill_max') is distinct from 'number'
     or (v->>'backfill_max')::numeric < 0 then
    return null;
  end if;
  return floor((v->>'backfill_max')::numeric)::integer;
exception when others then
  return null;
end $$;
revoke all on function public.trial_reserve_backfill_max() from public, anon, authenticated;

-- Stock is what the worker stored as backfill, what the system saw before the
-- search existed, or what was published longer ago than the alerts' age limit
-- (recommended_max_age_days, the worker's _is_recent): an old listing a crawl
-- reads for the first time is stock too, never new.
create or replace function public.admit_free_result() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_user uuid; v_created timestamptz; v_limit integer; v_max integer; v_days integer;
  v_active boolean; v_since timestamptz; v_seen timestamptz; v_backfill boolean;
begin
  select sp.user_id, sp.created_at into v_user, v_created
    from public.search_profiles sp where sp.id = new.search_profile_id;
  v_limit := public.free_result_limit(v_user);
  if v_limit is null then return new; end if;
  -- Serialize admissions across every search belonging to this account.
  perform 1 from public.profiles where id = v_user for update;
  select l.status = 'active', coalesce(l.published_at, l.first_seen_at), l.first_seen_at
    into v_active, v_since, v_seen
    from public.listings l where l.id = new.listing_id;
  if not coalesce(v_active, false)
     or (select count(*) from public.free_trial_results where user_id = v_user) >= v_limit then
    return new;
  end if;
  begin
    v_days := coalesce((select (value #>> '{}')::integer from public.app_config
                         where key = 'recommended_max_age_days'), 15);
  exception when others then
    v_days := 15;
  end;
  v_backfill := coalesce(new.is_backfill, true)
             or coalesce(v_seen < v_created, true)
             or coalesce(v_since < now() - make_interval(days => v_days), false);
  v_max := public.trial_reserve_backfill_max();
  if v_max is not null and v_backfill and (
       select count(*) from public.free_trial_results
        where user_id = v_user and is_backfill is distinct from false) >= v_max then
    return new;
  end if;
  insert into public.free_trial_results(user_id, listing_id, is_backfill)
  values (v_user, new.listing_id, v_backfill)
  on conflict do nothing;
  return new;
end $$;
revoke all on function public.admit_free_result() from public, anon, authenticated;

-- The reserve for the web: stock admitted and its cap (null when off).
create or replace function public.my_plan_limits() returns jsonb
language sql stable security definer set search_path = '' as $$
  select public.plan_limits_for((select auth.uid())) || jsonb_build_object(
    'free_results_used', (select count(*) from public.free_trial_results where user_id=(select auth.uid())),
    'free_results_limit', public.free_result_limit((select auth.uid())),
    'free_backfill_used', (select count(*) from public.free_trial_results
                            where user_id=(select auth.uid()) and is_backfill is distinct from false),
    'free_backfill_max', case when public.free_result_limit((select auth.uid())) is not null
                           then public.trial_reserve_backfill_max() end)
$$;

-- Matches of one's own search that the trial hides: active listings, the
-- ones a paid plan would show. 0 without a trial quota.
create function public.my_search_hidden_results(p_profile_id bigint) returns integer
language sql stable security definer set search_path = '' as $$
  select case when public.free_result_limit((select auth.uid())) is null then 0 else (
    select count(*)::integer
      from public.matches m
      join public.search_profiles sp on sp.id = m.search_profile_id
      join public.listings l on l.id = m.listing_id
     where sp.id = p_profile_id and sp.user_id = (select auth.uid()) and l.status = 'active'
       and not exists (select 1 from public.free_trial_results r
                        where r.user_id = sp.user_id and r.listing_id = m.listing_id)) end
$$;
revoke all on function public.my_search_hidden_results(bigint) from public, anon;
grant execute on function public.my_search_hidden_results(bigint) to authenticated;

-- Welcome (search_activated) and trial end (trial_ended) count what the trial
-- shows: the search is the one with the most visible results, `found` and
-- `below` are visible, `hidden` is what it hides among active listings, and
-- the welcome says how many results the trial has left. Accounts without a
-- trial quota keep their payload as it was.
alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_missed;

create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  r public.lifecycle_emails;
  v_limit integer; v_end timestamptz;
  s record;
begin
  for r in select * from public.claim_lifecycle_emails_missed(p_kind, p_window, p_limit) loop
    if r.kind in ('search_activated', 'trial_ended') then
      v_limit := public.free_result_limit(r.user_id);
      if v_limit is not null then
        v_end := case when r.kind = 'trial_ended'
                   then (r.payload->>'ended_at')::timestamptz end;
        if r.kind = 'trial_ended' and v_end is null then
          v_end := (select free_trial_started_at + interval '72 hours' from public.profiles where id = r.user_id);
        end if;
        select sp.id,
               coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''), sp.name) as model,
               count(m.id) filter (where public.free_result_allowed(r.user_id, m.listing_id)) as found_n,
               count(m.id) filter (where m.level = 'high' and public.free_result_allowed(r.user_id, m.listing_id)) as below_n,
               count(m.id) filter (where l.status = 'active' and not public.free_result_allowed(r.user_id, m.listing_id)) as hidden_n
          into s
          from public.search_profiles sp
          left join public.matches m on m.search_profile_id = sp.id
                                    and (v_end is null or m.generated_at <= v_end)
          left join public.listings l on l.id = m.listing_id
         where sp.user_id = r.user_id and (r.kind <> 'search_activated' or sp.enabled)
         group by sp.id
         order by 3 desc, 5 desc, count(m.id) desc, sp.id
         limit 1;
        if s.id is not null then
          update public.lifecycle_emails e
             set search_profile_id = s.id,
                 target = case when r.kind = 'search_activated' then '/app/searches/' || s.id else e.target end,
                 payload = e.payload || jsonb_build_object(
                   'model', s.model, 'found', s.found_n, 'below', s.below_n, 'hidden', s.hidden_n)
           where e.id = r.id
          returning * into r;
        end if;
        if r.kind = 'search_activated' then
          update public.lifecycle_emails e
             set payload = e.payload || jsonb_build_object('trial_limit', v_limit, 'trial_left', greatest(v_limit - (
                   select count(*) from public.free_trial_results where user_id = r.user_id), 0))
           where e.id = r.id
          returning * into r;
        end if;
      end if;
    end if;
    return next r;
  end loop;
end $$;

revoke all on function public.claim_lifecycle_emails_missed(text, interval, integer),
  public.claim_lifecycle_emails(text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.claim_lifecycle_emails(text, interval, integer) to service_role;

notify pgrst, 'reload schema';
