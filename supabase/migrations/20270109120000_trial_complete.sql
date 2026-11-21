-- Prueba gratis «40 + N» (docs/PRUEBA_COMPLETA.md).
--
-- The trial shows a random sample of what was already published (up to the
-- reserve's backfill_max) and then the next new_max new matches; when the
-- last of those arrives, one email (trial_complete) and one pop-up tell the
-- person the trial is complete.
--
-- Everything hangs from app_config.trial_reserve, which this migration does
-- not touch. Three optional fields, read only with the reserve on:
--   new_max       whole number >= 0: the cap on new results per account;
--   random_stock  true: the first run's stock is admitted as a random sample;
--   notice_since  ISO timestamp: trial_complete goes only to trials started since.
-- Without them (the row as it is today) every behaviour is today's. A broken
-- value is off, like backfill_max: no cap, no sample, no email.
set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- The switch
-- ---------------------------------------------------------------------------

-- The cap on new results, or null: the reserve off, or new_max missing, not
-- a number or negative. With a cap the trial is in "new mode".
create function public.trial_reserve_new_max() returns integer
language plpgsql stable security definer set search_path = '' as $$
declare v jsonb;
begin
  if public.trial_reserve_backfill_max() is null then
    return null;
  end if;
  select value into v from public.app_config where key = 'trial_reserve';
  if jsonb_typeof(v->'new_max') is distinct from 'number' or (v->>'new_max')::numeric < 0 then
    return null;
  end if;
  return floor((v->>'new_max')::numeric)::integer;
exception when others then
  return null;
end $$;

-- The first run's stock as a random sample: the reserve on and random_stock true itself.
create function public.trial_reserve_random_stock() returns boolean
language plpgsql stable security definer set search_path = '' as $$
begin
  return public.trial_reserve_backfill_max() is not null
     and coalesce((select value->'random_stock' = 'true'::jsonb from public.app_config
                    where key = 'trial_reserve'), false);
exception when others then
  return false;
end $$;

-- Since when trial_complete goes out: null (nobody) without new mode or with
-- a notice_since that isn't a timestamp.
create function public.trial_reserve_notice_since() returns timestamptz
language plpgsql stable security definer set search_path = '' as $$
begin
  if public.trial_reserve_new_max() is null then
    return null;
  end if;
  return (select (value->>'notice_since')::timestamptz from public.app_config where key = 'trial_reserve');
exception when others then
  return null;
end $$;

revoke all on function public.trial_reserve_new_max(), public.trial_reserve_random_stock(),
  public.trial_reserve_notice_since() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- What is stock (one definition for both admissions)
-- ---------------------------------------------------------------------------

-- The alerts' age limit (recommended_max_age_days, the worker's _is_recent); 15 when unreadable.
create function public.trial_stock_age_days() returns integer
language plpgsql stable security definer set search_path = '' as $$
begin
  return coalesce((select (value #>> '{}')::integer from public.app_config where key = 'recommended_max_age_days'), 15);
exception when others then
  return 15;
end $$;

-- 20261207120000's rule: what the worker stored as backfill, what the system
-- saw before the search existed, or what was published longer ago than the age limit.
create function public.trial_is_stock(p_match_backfill boolean, p_first_seen timestamptz,
                                      p_published timestamptz, p_search_created timestamptz,
                                      p_days integer) returns boolean
language sql stable set search_path = '' as $$
  select coalesce(p_match_backfill, true)
      or coalesce(p_first_seen < p_search_created, true)
      or coalesce(coalesce(p_published, p_first_seen) < now() - make_interval(days => p_days), false)
$$;

revoke all on function public.trial_stock_age_days(),
  public.trial_is_stock(boolean, timestamptz, timestamptz, timestamptz, integer) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Admission
-- ---------------------------------------------------------------------------

-- 20261207120000's, plus two rules that only apply with the new fields:
--   - new_max: a new result is not admitted once the account has new_max of them;
--   - random_stock: stock of a search pending its first run or a re-run waits
--     for the run's end, where admit_free_stock_sample picks it at random.
-- Stock that arrives when the search is not pending is admitted first-come,
-- and a new match is never deferred. It never removes an admitted result.
create or replace function public.admit_free_result() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_user uuid; v_created timestamptz; v_pending boolean; v_limit integer; v_max integer; v_new_max integer;
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
  if not v_backfill then
    v_new_max := public.trial_reserve_new_max();
    if v_new_max is not null and (select count(*) from public.free_trial_results
                                   where user_id = v_user and is_backfill = false) >= v_new_max then
      return new;
    end if;
  end if;
  insert into public.free_trial_results(user_id, listing_id, is_backfill)
  values (v_user, new.listing_id, v_backfill)
  on conflict do nothing;
  return new;
end $$;
revoke all on function public.admit_free_result() from public, anon, authenticated;

-- random_stock: when a run ends (mark_bootstrapped sets bootstrapped_at and
-- clears rematch_requested_at), a random sample of that search's stock with
-- an active listing, not admitted yet, up to the room left:
-- least(backfill_max - stock admitted, limit - total admitted). A re-run fills
-- only the room left. Same per-account lock as admit_free_result.
create function public.admit_free_stock_sample() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_limit integer; v_max integer; v_room integer; v_days integer;
begin
  v_max := public.trial_reserve_backfill_max();
  if v_max is null or not public.trial_reserve_random_stock() then return new; end if;
  v_limit := public.free_result_limit(new.user_id);
  if v_limit is null then return new; end if;
  perform 1 from public.profiles where id = new.user_id for update;
  select least(v_max - count(*) filter (where is_backfill is distinct from false), v_limit - count(*))
    into v_room
    from public.free_trial_results where user_id = new.user_id;
  if coalesce(v_room, 0) <= 0 then return new; end if;
  v_days := public.trial_stock_age_days();
  insert into public.free_trial_results(user_id, listing_id, is_backfill)
  select new.user_id, c.listing_id, true
    from (select distinct m.listing_id
            from public.matches m
            join public.listings l on l.id = m.listing_id
           where m.search_profile_id = new.id
             and l.status = 'active'
             and public.trial_is_stock(m.is_backfill, l.first_seen_at, l.published_at, new.created_at, v_days)
             and not exists (select 1 from public.free_trial_results r
                              where r.user_id = new.user_id and r.listing_id = m.listing_id)) c
   order by random()
   limit v_room
  on conflict do nothing;
  return new;
end $$;
revoke all on function public.admit_free_stock_sample() from public, anon, authenticated;

create trigger search_profiles_admit_free_stock_sample
after update of bootstrapped_at, rematch_requested_at on public.search_profiles
for each row
when (new.bootstrapped_at is not null and new.rematch_requested_at is null
      and (old.bootstrapped_at is null or old.rematch_requested_at is not null))
execute function public.admit_free_stock_sample();

-- ---------------------------------------------------------------------------
-- What the web reads
-- ---------------------------------------------------------------------------

-- 20261207120000's, plus the new results admitted and their cap (null with
-- no cap or no trial quota).
create or replace function public.my_plan_limits() returns jsonb
language sql stable security definer set search_path = '' as $$
  select public.plan_limits_for((select auth.uid())) || jsonb_build_object(
    'free_results_used', (select count(*) from public.free_trial_results where user_id=(select auth.uid())),
    'free_results_limit', public.free_result_limit((select auth.uid())),
    'free_backfill_used', (select count(*) from public.free_trial_results
                            where user_id=(select auth.uid()) and is_backfill is distinct from false),
    'free_backfill_max', case when public.free_result_limit((select auth.uid())) is not null
                           then public.trial_reserve_backfill_max() end,
    'free_new_used', (select count(*) from public.free_trial_results
                       where user_id=(select auth.uid()) and is_backfill = false),
    'free_new_max', case when public.free_result_limit((select auth.uid())) is not null
                      then public.trial_reserve_new_max() end)
$$;

-- When the account's new_max-th new result was admitted: null without a cap,
-- with a cap of 0 (no new result ever completes it) or before it got there.
create function public.trial_completed_at(p_user uuid) returns timestamptz
language plpgsql stable security definer set search_path = '' as $$
declare v_new_max integer;
begin
  v_new_max := public.trial_reserve_new_max();
  if v_new_max is null or v_new_max <= 0 then
    return null;
  end if;
  return (select r.admitted_at from public.free_trial_results r
           where r.user_id = p_user and r.is_backfill = false
           order by r.admitted_at, r.listing_id
          offset v_new_max - 1 limit 1);
end $$;
revoke all on function public.trial_completed_at(uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- trial_complete: one email when the trial completes
-- ---------------------------------------------------------------------------

alter table public.lifecycle_emails drop constraint lifecycle_emails_kind_check;
alter table public.lifecycle_emails add constraint lifecycle_emails_kind_check
  check (kind in ('trial_no_matches', 'trial_ended', 'pass_expiring', 'pass_expires_today',
                  'count_after_expiry', 'search_activated',
                  'search_abandoned', 'search_not_started', 'search_feedback',
                  'bonus_trial_offer', 'bonus_trial_ending', 'bonus_trial_ended',
                  'trial_complete'));

-- Off until Juan turns it on in /admin/config.
update public.app_config
   set value = jsonb_set(value, '{kinds}', coalesce(value->'kinds', '{}') || '{"trial_complete": false}')
 where key = 'lifecycle_emails';

alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_cars;
alter function public.lifecycle_email_eligible(bigint) rename to lifecycle_email_eligible_bonus;

-- Still worth sending: the account takes emails, still has its trial quota
-- and the trial is still running (an ended trial gets trial_ended instead).
create function public.trial_complete_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.lifecycle_contact_ok(p_user)
     and public.free_result_limit(p_user) is not null
     and public.plan_limits_for(p_user)->>'state' = 'trial'
$$;

create function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select case when e.kind = 'trial_complete' then public.trial_complete_eligible(e.user_id)
              else public.lifecycle_email_eligible_bonus(p_id) end
    from public.lifecycle_emails e where e.id = p_id
$$;

-- trial_complete: once per account, 60 minutes after trial_completed_at, in
-- new mode, for trials started since notice_since and still running. The
-- search is picked as trial_ended picks it: the one that shows the most.
-- payload: model, new (the cap), shown (what the trial shows of that search)
-- and hidden (active matches it hides, as my_search_hidden_results counts them).
--
-- The welcome (search_activated) in new mode: what the trial has left is new
-- cars, so trial_left is new_max minus the new results admitted, and
-- trial_new carries the cap for the template. Legacy mode: unchanged.
create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  r public.lifecycle_emails;
  v_new_max integer;
  v_since timestamptz;
begin
  if p_kind <> 'trial_complete' then
    for r in select * from public.claim_lifecycle_emails_cars(p_kind, p_window, p_limit) loop
      if r.kind = 'search_activated' and r.payload ? 'trial_limit' then
        v_new_max := public.trial_reserve_new_max();
        if v_new_max is not null then
          update public.lifecycle_emails e
             set payload = e.payload || jsonb_build_object('trial_new', v_new_max, 'trial_left', greatest(v_new_max - (
                   select count(*) from public.free_trial_results
                    where user_id = r.user_id and is_backfill = false), 0))
           where e.id = r.id
          returning * into r;
        end if;
      end if;
      return next r;
    end loop;
    return;
  end if;

  v_new_max := public.trial_reserve_new_max();
  v_since := public.trial_reserve_notice_since();
  -- Off unless the kind is explicitly on: the worker checks it too, but a
  -- missing key must never send this one (lifecycle_kind_on defaults to on).
  if v_new_max is null or v_new_max <= 0 or v_since is null
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
    select d.user_id, d.due_at, s.id as search_id, s.model, s.shown_n, s.hidden_n
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
         jsonb_build_object('model', model, 'new', v_new_max,
                            'shown', coalesce(shown_n, 0), 'hidden', coalesce(hidden_n, 0)),
         case when search_id is not null then '/app/searches/' || search_id else '/app' end
    from picked
  on conflict (user_id, kind, event_key) do nothing
  returning *;
end $$;

revoke all on function public.claim_lifecycle_emails_cars(text, interval, integer),
  public.lifecycle_email_eligible_bonus(bigint), public.trial_complete_eligible(uuid),
  public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer)
  to service_role;

notify pgrst, 'reload schema';
