-- Fase 2 de planes, 2.5 (docs/MAILS_DE_PLAN.md): after access ends, count the
-- new listings that match the searches it paused, and email the count 7, 14
-- and 21 days later ("Aparecieron {N} autos nuevos para tu búsqueda de {modelo}").
--
-- Who: trials that never bought and Particular passes, ended and not renewed.
-- Juan approved (14/10/2026) crawling those searches' models once a day for
-- those 3 weeks when no active search crawls them already (pipeline/crawl.py).
--
-- The count lives in expired_search_matches, never in matches: the web shows
-- none of it and nothing is notified. A pass bought after the email records
-- reactivated_from_count_email.

-- ---------------------------------------------------------------------------
-- The count
-- ---------------------------------------------------------------------------

create table public.expired_search_matches (
  search_profile_id bigint not null references public.search_profiles(id) on delete cascade,
  listing_id        bigint not null references public.listings(id) on delete cascade,
  -- The access end it counts for (count_after_expiry_end): an email counts
  -- the rows of the account's current end only.
  access_ended_at   timestamptz not null,
  level             public.match_level not null,
  created_at        timestamptz not null default now(),
  primary key (search_profile_id, listing_id)
);
create index expired_search_matches_listing_id_idx on public.expired_search_matches (listing_id);
create index expired_search_matches_ended_idx on public.expired_search_matches (access_ended_at);
comment on table public.expired_search_matches is
  'Listings that matched a search after its access ended, scored by the worker like a match (2.5, '
  'docs/MAILS_DE_PLAN.md). Only counted for the email: never shown, never notified. Pruned 60 days after the end.';

alter table public.expired_search_matches enable row level security;
revoke all on public.expired_search_matches from public, anon, authenticated, service_role;
grant select, insert, update, delete on public.expired_search_matches to service_role;

-- ---------------------------------------------------------------------------
-- Who is counted
-- ---------------------------------------------------------------------------

-- Whether app_config.lifecycle_emails leaves a kind on, read like the worker's
-- settings(): only an explicit false (or "false") turns it off. Turning the
-- kind off also stops the extra crawling.
create function public.lifecycle_kind_on(p_kind text) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select lower(trim(coalesce(c.value->>'enabled', ''))) <> 'false'
       and lower(trim(coalesce(c.value->'kinds'->>p_kind, ''))) <> 'false'
      from public.app_config c where c.key = 'lifecycle_emails'), true)
$$;

-- A checkout in progress: cash tickets accredit late, but a pending checkout
-- older than 72 h is abandoned and stops blocking. 2.2's rule, now shared.
create function public.checkout_in_progress(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.billing_checkouts bc where bc.user_id = p_user
           and (bc.status in ('creating', 'authorized', 'paused')
             or (bc.status = 'pending' and bc.created_at > now() - interval '72 hours')
             or (bc.sync_error is not null and bc.status not in ('failed', 'cancelled', 'paid'))))
$$;

-- 20261020's 2.2 eligibility, with the shared checkout rule (same behavior).
create or replace function public.trial_ended_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'free'
       and p.free_trial_started_at is not null
       -- 'expired' implies plan_limits.enforced, the trial over and nothing paid now.
       and public.plan_limits_for(p.id)->>'state' = 'expired'
       and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
       and not public.checkout_in_progress(p.id)
       -- No point inviting to buy while checkout is closed.
       and coalesce((select (c.value->>'enabled')::boolean from public.app_config c
                      where c.key = 'commercial_pilot'), false)
      from public.profiles p where p.id = p_user), false)
$$;

-- The access end 2.5 counts from, or null. A trial that never bought (a
-- refunded payment still counts as buying, like 2.2) or a Particular pass
-- (or the trial that followed it), ended and not renewed, for an account that
-- takes plan emails while checkout is open. Agencia is not in the plans
-- document's audience.
create function public.count_after_expiry_end(p_user uuid) returns timestamptz
language sql stable security definer set search_path = '' as $$
  select case
           when p.plan = 'pass' then greatest(p.plan_expires_at, p.free_trial_started_at + interval '72 hours')
           when p.plan = 'free' and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
             then p.free_trial_started_at + interval '72 hours'
         end
    from public.profiles p
   where p.id = p_user
     and public.lifecycle_contact_ok(p.id)
     and not public.commercial_access_active(p.id)
     and coalesce((select (c.value->>'enabled')::boolean from public.app_config c
                    where c.key = 'commercial_pilot'), false)
$$;

-- The searches 2.5 counts now: the ones that end paused (search_paused_by_plan
-- since then), during 22 days, while the kind is on. The worker crawls and
-- scores for them (pipeline/crawl.py, pipeline/scheduler.py).
create function public.count_after_expiry_searches()
returns table (search_profile_id bigint, user_id uuid, ended_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select sp.id, sp.user_id, a.ended_at
    from public.profiles p
    cross join lateral (select public.count_after_expiry_end(p.id) as ended_at) a
    join public.search_profiles sp on sp.user_id = p.id and not sp.enabled
   where public.lifecycle_kind_on('count_after_expiry')
     -- Cheap first: a pass or a trial that ended in the last 22 days.
     and ((p.plan = 'pass' and p.plan_expires_at > now() - interval '22 days')
          or p.free_trial_started_at > now() - interval '22 days' - interval '72 hours')
     and a.ended_at > now() - interval '22 days'
     and exists (select 1 from public.events e
                  where e.user_id = p.id and e.name = 'search_paused_by_plan'
                    and e.props->>'search_profile_id' = sp.id::text
                    and e.created_at >= a.ended_at)
$$;

-- 2.5 when claiming and again at send time: the email is about the account's
-- current end (the event key starts with it), within the 3 weeks plus a day
-- for retries, and no checkout is in progress.
create function public.count_after_expiry_eligible(p_user uuid, p_event text) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select extract(epoch from a.ended_at)::bigint::text = split_part(p_event, ':', 1)
       and a.ended_at > now() - interval '23 days'
       and not public.checkout_in_progress(p_user)
      from (select public.count_after_expiry_end(p_user) as ended_at) a), false)
$$;

create or replace function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select case e.kind
             when 'trial_no_matches' then public.trial_no_matches_eligible(e.user_id)
             when 'trial_ended' then public.trial_ended_eligible(e.user_id)
             when 'pass_expiring' then public.pass_expiry_eligible(e.user_id, e.kind, e.event_key)
             when 'pass_expires_today' then public.pass_expiry_eligible(e.user_id, e.kind, e.event_key)
             when 'count_after_expiry' then public.count_after_expiry_eligible(e.user_id, e.event_key)
             else false end
      from public.lifecycle_emails e where e.id = p_id), false)
$$;

-- ---------------------------------------------------------------------------
-- Claim: 20261022's, plus count_after_expiry
-- ---------------------------------------------------------------------------

create or replace function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
begin
  if p_window is null or coalesce(p_limit, 0) <= 0 then
    return;
  end if;
  if p_kind = 'trial_no_matches' then
    return query
    with due as materialized (
      select p.id as user_id, p.free_trial_started_at + interval '24 hours' as due_at
        from public.profiles p
       where p.plan = 'free'
         and p.free_trial_started_at + interval '24 hours' <= now()
         and p.free_trial_started_at + interval '24 hours' > now() - p_window
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = p.id and e.kind = p_kind)
    ), picked as (
      select d.user_id, d.due_at, s.id as search_id, s.model
        from due d
        cross join lateral (
          select sp.id, coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''),
                                 sp.name) as model
            from public.search_profiles sp
           where sp.user_id = d.user_id and sp.enabled
           order by sp.id limit 1) s
       where public.trial_no_matches_eligible(d.user_id)
       order by d.due_at, d.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
    select user_id, p_kind, 'trial', search_id, jsonb_build_object('model', model),
           '/app/searches/' || search_id || '/edit'
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  elsif p_kind = 'trial_ended' then
    return query
    with due as materialized (
      select p.id as user_id, p.free_trial_started_at + interval '72 hours' as ended_at
        from public.profiles p
       where p.plan = 'free'
         and p.free_trial_started_at + interval '72 hours' <= now()
         and p.free_trial_started_at + interval '72 hours' > now() - p_window
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = p.id and e.kind = p_kind)
    ), picked as (
      -- The trial's search that found the most; "below comparables" is what
      -- the system already marks as an opportunity (level high).
      select d.user_id, d.ended_at, s.id as search_id, s.model, s.found_n, s.below_n
        from due d
        left join lateral (
          select sp.id,
                 coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''),
                          sp.name) as model,
                 count(m.id) as found_n,
                 count(m.id) filter (where m.level = 'high') as below_n
            from public.search_profiles sp
            left join public.matches m on m.search_profile_id = sp.id and m.generated_at <= d.ended_at
           where sp.user_id = d.user_id
           group by sp.id
           order by count(m.id) desc, sp.id desc limit 1) s on true
       where public.trial_ended_eligible(d.user_id)
       order by d.ended_at, d.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
    select user_id, p_kind, 'trial', search_id,
           jsonb_build_object('model', model, 'found', coalesce(found_n, 0), 'below', coalesce(below_n, 0)),
           '/app/pro?plan=pass_30'
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  elsif p_kind in ('pass_expiring', 'pass_expires_today') then
    return query
    with due as materialized (
      select p.id as user_id, p.plan_expires_at as ends_at,
             extract(epoch from p.plan_expires_at)::bigint::text as event_key
        from public.profiles p
       where p.plan = 'pass'
         and p.plan_expires_at > now() - interval '1 day'
         and p.plan_expires_at < now() + interval '6 days'
    ), picked as (
      -- What the pass found since it started; "below comparables" is level high.
      select d.user_id, d.ends_at, d.event_key, s.found_n, s.below_n
        from due d
        cross join lateral (
          select count(m.id) as found_n, count(m.id) filter (where m.level = 'high') as below_n
            from public.matches m
            join public.search_profiles sp on sp.id = m.search_profile_id
           where sp.user_id = d.user_id and m.generated_at >= public.pass_started_at(d.user_id)) s
       where public.pass_expiry_eligible(d.user_id, p_kind, d.event_key)
         and not exists (select 1 from public.lifecycle_emails e
                          where e.user_id = d.user_id and e.kind = p_kind and e.event_key = d.event_key)
       order by d.ends_at, d.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, payload, target)
    select user_id, p_kind, event_key,
           jsonb_build_object('found', found_n, 'below', below_n, 'ends_at', ends_at, 'ended', ends_at <= now()),
           '/app/pro?plan=pass_30'
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  elsif p_kind = 'count_after_expiry' then
    -- 2.5: on day 7, 14 and 21 after the end (each stage has its own day and
    -- event key "<end epoch>:<stage>"), about the counted search that found the
    -- most. No rows counted, no email: the lateral join yields nothing.
    return query
    with ends as materialized (
      select distinct c.user_id, c.ended_at from public.count_after_expiry_searches() c
    ), due as (
      select e.user_id, e.ended_at, s.stage,
             extract(epoch from e.ended_at)::bigint::text || ':' || s.stage as event_key
        from ends e
        cross join (values (7), (14), (21)) as s (stage)
       where e.ended_at + make_interval(days => s.stage) <= now()
         and now() < e.ended_at + make_interval(days => s.stage + 1)
    ), picked as (
      select d.user_id, d.ended_at, d.stage, d.event_key, x.search_id, x.model, x.found_n, x.below_n
        from due d
        cross join lateral (
          select sp.id as search_id,
                 coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''),
                          sp.name) as model,
                 count(*) as found_n,
                 count(*) filter (where m.level = 'high') as below_n
            from public.expired_search_matches m
            join public.search_profiles sp on sp.id = m.search_profile_id
           where sp.user_id = d.user_id and m.access_ended_at = d.ended_at
           group by sp.id
           order by count(*) desc, count(*) filter (where m.level = 'high') desc, sp.id
           limit 1) x
       where public.count_after_expiry_eligible(d.user_id, d.event_key)
         and not exists (select 1 from public.lifecycle_emails e
                          where e.user_id = d.user_id and e.kind = p_kind and e.event_key = d.event_key)
       order by d.ended_at, d.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
    select user_id, p_kind, event_key, search_id,
           jsonb_build_object('model', model, 'found', found_n, 'below', below_n, 'stage', stage,
                              'ended_at', ended_at),
           '/app/pro?plan=pass_30'
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- reactivated_from_count_email: 20261021's reactivation, plus the event
-- ---------------------------------------------------------------------------

-- Both payment paths call this for a pass bought after access ended, so it is
-- also where a purchase that followed a count email is recorded: the account's
-- latest sent count email, if it went out in the last 30 days and no purchase
-- claimed it yet. Neither part raises: the payment always goes through.
create or replace function public.reactivate_paused_searches(p_user uuid) returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_room integer;
  v_count integer := 0;
begin
  begin
    select coalesce((a.v->'limits'->>'max_profiles')::integer, 0) - coalesce((a.v->>'active_searches')::integer, 0)
      into v_room from (select public.plan_limits_for(p_user) v) a;
    if coalesce(v_room, 0) > 0 then
      with paused as (
        select sp.id
          from public.search_profiles sp
          join public.events e on e.user_id = sp.user_id and e.name = 'search_paused_by_plan'
                              and e.props->>'search_profile_id' = sp.id::text
         where sp.user_id = p_user and not sp.enabled
         group by sp.id
         order by max(e.created_at) desc, sp.id desc
         limit v_room
      )
      update public.search_profiles sp set enabled = true from paused where sp.id = paused.id;
      get diagnostics v_count = row_count;
      if v_count > 0 then
        insert into public.events (user_id, name, props)
        values (p_user, 'searches_reactivated', jsonb_build_object('count', v_count));
      end if;
    end if;
  exception when others then
    raise warning 'reactivate_paused_searches: % (user %)', sqlerrm, p_user;
    v_count := 0;
  end;
  begin
    insert into public.events (user_id, name, props)
    select p_user, 'reactivated_from_count_email',
           jsonb_build_object('email_id', e.id, 'stage', e.payload->'stage', 'clicked', e.clicked_at is not null,
                              'days_after_email', extract(day from now() - e.sent_at)::integer)
      from (select * from public.lifecycle_emails le
             where le.user_id = p_user and le.kind = 'count_after_expiry' and le.status = 'sent'
             order by le.sent_at desc limit 1) e
     where e.sent_at > now() - interval '30 days'
       and not exists (select 1 from public.events r
                        where r.user_id = p_user and r.name = 'reactivated_from_count_email'
                          and r.props->>'email_id' = e.id::text);
  exception when others then
    raise warning 'reactivated_from_count_email: % (user %)', sqlerrm, p_user;
  end;
  return v_count;
end $$;

revoke all on function public.lifecycle_kind_on(text), public.checkout_in_progress(uuid),
  public.count_after_expiry_end(uuid), public.count_after_expiry_searches(),
  public.count_after_expiry_eligible(uuid, text) from public, anon, authenticated;

-- Juan approved 2.5 and the daily crawl (14/10/2026): the kind on.
update public.app_config
   set value = jsonb_set(value, '{kinds,count_after_expiry}', 'true')
 where key = 'lifecycle_emails' and jsonb_typeof(value->'kinds') = 'object';

notify pgrst, 'reload schema';
