-- Prueba gratis de 50 publicaciones (docs/PRUEBA_COMPLETA.md).
--
-- Juan, 2026-11-21: the trial is told as «50 publicaciones» and ends at its
-- limit (plan_limits.free.max_total_results) or at its 3 days, whichever comes
-- first. There is no separate cap on new results any more: up to backfill_max
-- of the 50 are the random sample of what was already published, and the rest
-- is for new matches. The trial is "complete" when the account's quota is full;
-- only then trial_complete goes out.
--
-- 20270109120000 stays as it is (it is in production). This one takes new_max
-- out: trial_reserve_new_max() goes, and every function that called it is
-- replaced. "Notice mode" is now the reserve on and a notice_since that parses
-- as a timestamp.
--
-- Inert on a row without notice_since (production's {"enabled": true,
-- "backfill_max": 30}): admit_free_result and my_plan_limits are then exactly
-- 20261207120000's, trial_complete claims nothing and the welcome is untouched.
set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- The switch
-- ---------------------------------------------------------------------------

-- Since when trial_complete goes out and the welcome speaks of the 50: null
-- (nobody) with the reserve off or a notice_since that isn't a timestamp.
create or replace function public.trial_reserve_notice_since() returns timestamptz
language plpgsql stable security definer set search_path = '' as $$
begin
  if public.trial_reserve_backfill_max() is null then
    return null;
  end if;
  return (select (value->>'notice_since')::timestamptz from public.app_config where key = 'trial_reserve');
exception when others then
  return null;
end $$;
revoke all on function public.trial_reserve_notice_since() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Admission
-- ---------------------------------------------------------------------------

-- 20261207120000's, plus random_stock: stock of a search pending its first run
-- or a re-run waits for the run's end, where admit_free_stock_sample picks it
-- at random. A new match is admitted while the account has room, as before
-- the reserve. It never removes an admitted result.
create or replace function public.admit_free_result() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_user uuid; v_created timestamptz; v_pending boolean; v_limit integer; v_max integer;
  v_active boolean; v_published timestamptz; v_seen timestamptz; v_backfill boolean;
begin
  select sp.user_id, sp.created_at, sp.bootstrapped_at is null or sp.rematch_requested_at is not null
    into v_user, v_created, v_pending
    from public.search_profiles sp where sp.id = new.search_profile_id;
  v_limit := public.free_result_limit(v_user);
  if v_limit is null then return new; end if;
  -- Serialize admissions across every search belonging to this account.
  perform 1 from public.profiles where id = v_user for update;
  select l.status = 'active', l.published_at, l.first_seen_at
    into v_active, v_published, v_seen
    from public.listings l where l.id = new.listing_id;
  if not coalesce(v_active, false)
     or (select count(*) from public.free_trial_results where user_id = v_user) >= v_limit then
    return new;
  end if;
  v_backfill := public.trial_is_stock(new.is_backfill, v_seen, v_published, v_created, public.trial_stock_age_days());
  v_max := public.trial_reserve_backfill_max();
  if v_max is not null and v_backfill then
    if (select count(*) from public.free_trial_results
         where user_id = v_user and is_backfill is distinct from false) >= v_max then
      return new;
    end if;
    if coalesce(v_pending, false) and public.trial_reserve_random_stock() then
      return new;
    end if;
  end if;
  insert into public.free_trial_results(user_id, listing_id, is_backfill)
  values (v_user, new.listing_id, v_backfill)
  on conflict do nothing;
  return new;
end $$;
revoke all on function public.admit_free_result() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- What the web reads
-- ---------------------------------------------------------------------------

-- Back to 20261207120000's: no free_new_used / free_new_max.
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

-- When the account's limit-th result was admitted: null without a trial
-- quota or before the quota fills.
create or replace function public.trial_completed_at(p_user uuid) returns timestamptz
language plpgsql stable security definer set search_path = '' as $$
declare v_limit integer;
begin
  v_limit := public.free_result_limit(p_user);
  if v_limit is null or v_limit <= 0 then
    return null;
  end if;
  return (select r.admitted_at from public.free_trial_results r
           where r.user_id = p_user
           order by r.admitted_at, r.listing_id
          offset v_limit - 1 limit 1);
end $$;
revoke all on function public.trial_completed_at(uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- trial_complete and the welcome
-- ---------------------------------------------------------------------------

-- trial_complete: once per account, 60 minutes after trial_completed_at, in
-- notice mode, for trials started since notice_since and still running. The
-- search is picked as trial_ended picks it: the one that shows the most.
-- payload: model, total (the account's limit), shown (what the trial shows of
-- that search) and hidden (active matches it hides).
--
-- The welcome (search_activated) in notice mode: a payload with trial_limit
-- gets trial_notice: true, and trial_left stays as the legacy claim computed
-- it. Outside notice mode the row passes through untouched.
create or replace function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  r public.lifecycle_emails;
  v_since timestamptz;
begin
  v_since := public.trial_reserve_notice_since();
  if p_kind <> 'trial_complete' then
    for r in select * from public.claim_lifecycle_emails_cars(p_kind, p_window, p_limit) loop
      if r.kind = 'search_activated' and r.payload ? 'trial_limit' and v_since is not null then
        update public.lifecycle_emails e
           set payload = e.payload || jsonb_build_object('trial_notice', true)
         where e.id = r.id
        returning * into r;
      end if;
      return next r;
    end loop;
    return;
  end if;

  -- Off unless the kind is explicitly on: the worker checks it too, but a
  -- missing key must never send this one (lifecycle_kind_on defaults to on).
  if v_since is null
     or p_window is null or coalesce(p_limit, 0) <= 0
     or (select c.value #> '{kinds,trial_complete}' from public.app_config c
          where c.key = 'lifecycle_emails') is distinct from 'true'::jsonb then
    return;
  end if;
  return query
  with started as materialized (
    -- Cheap first: trials started since notice_since and within the last 72 h.
    select p.id as user_id
      from public.profiles p
     where p.free_trial_started_at >= v_since
       and p.free_trial_started_at > now() - interval '72 hours'
       and not exists (select 1 from public.lifecycle_emails e where e.user_id = p.id and e.kind = p_kind)
  ), due as (
    select s.user_id, c.done_at + interval '60 minutes' as due_at
      from started s
      cross join lateral (select public.trial_completed_at(s.user_id) as done_at) c
     where c.done_at + interval '60 minutes' <= now()
       and c.done_at + interval '60 minutes' > now() - p_window
  ), picked as (
    select d.user_id, d.due_at, public.free_result_limit(d.user_id) as total,
           s.id as search_id, s.model, s.shown_n, s.hidden_n
      from due d
      left join lateral (
        select sp.id,
               coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''), sp.name) as model,
               count(m.id) filter (where public.free_result_allowed(d.user_id, m.listing_id)) as shown_n,
               count(m.id) filter (where l.status = 'active' and not public.free_result_allowed(d.user_id, m.listing_id)) as hidden_n
          from public.search_profiles sp
          left join public.matches m on m.search_profile_id = sp.id
          left join public.listings l on l.id = m.listing_id
         where sp.user_id = d.user_id
         group by sp.id
         order by 3 desc, 4 desc, count(m.id) desc, sp.id
         limit 1) s on true
     where public.trial_complete_eligible(d.user_id)
     order by d.due_at, d.user_id
     limit p_limit
  )
  insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
  select user_id, p_kind, 'complete', search_id,
         jsonb_build_object('model', model, 'total', total,
                            'shown', coalesce(shown_n, 0), 'hidden', coalesce(hidden_n, 0)),
         case when search_id is not null then '/app/searches/' || search_id else '/app' end
    from picked
  on conflict (user_id, kind, event_key) do nothing
  returning *;
end $$;

revoke all on function public.claim_lifecycle_emails(text, interval, integer) from public, anon, authenticated;
grant execute on function public.claim_lifecycle_emails(text, interval, integer) to service_role;

-- Nothing calls it any more.
drop function public.trial_reserve_new_max();

notify pgrst, 'reload schema';
