-- Hold writers until the seed and observation triggers commit together. Without
-- this lock, a concurrent search or first-good transition could be missed.
set local lock_timeout = '5s';
lock table public.search_profiles, public.matches in share row exclusive mode;

-- Immutable observations. A match's generated_at survives re-scoring, so it
-- cannot prove when a search first received a good result. Start measuring now;
-- never reconstruct historical first-value observations from mutable matches.
create table public.admin_metric_observation (
  singleton boolean primary key default true check (singleton),
  first_value_tracking_since timestamptz not null default statement_timestamp()
);
insert into public.admin_metric_observation(singleton) values (true);
alter table public.admin_metric_observation enable row level security;
create policy "observation cutoff: read" on public.admin_metric_observation
  for select to authenticated using (true);
revoke all on public.admin_metric_observation from public, anon, authenticated;
grant select on public.admin_metric_observation to authenticated;
grant all on public.admin_metric_observation to service_role;

create table public.admin_search_observations (
  -- Deliberately no FK to search_profiles: deleting a search must not erase
  -- its creation or first-value history. Account deletion still removes PII.
  search_profile_id bigint primary key,
  user_id uuid not null references public.profiles(id) on delete cascade,
  search_created_at timestamptz not null,
  first_good_at timestamptz
);
create index admin_search_observations_user_created_idx
  on public.admin_search_observations(user_id,search_created_at);
alter table public.admin_search_observations enable row level security;
create policy "search observations: read own" on public.admin_search_observations
  for select to authenticated using (user_id=(select auth.uid()));
create policy "search observations: register own source" on public.admin_search_observations
  for insert to authenticated with check (
    user_id=(select auth.uid()) and first_good_at is null
    and exists(select 1 from public.search_profiles s
      where s.id=admin_search_observations.search_profile_id
        and s.user_id=admin_search_observations.user_id
        and s.created_at=admin_search_observations.search_created_at)
  );
revoke all on public.admin_search_observations from public, anon, authenticated;
grant select,insert on public.admin_search_observations to authenticated;
grant all on public.admin_search_observations to service_role;

-- Preserve known creations, with NO inferred first_good_at. Coverage is derived
-- from the trusted singleton cutoff, never a client-supplied observed-from date.
insert into public.admin_search_observations(search_profile_id,user_id,search_created_at)
  select id,user_id,created_at from public.search_profiles;

create function public.register_admin_search_observation() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if tg_op='UPDATE' then
    if new.user_id is distinct from old.user_id then
      update public.admin_search_observations set user_id=new.user_id where search_profile_id=new.id;
    end if;
  else
    insert into public.admin_search_observations(search_profile_id,user_id,search_created_at)
      values(new.id,new.user_id,new.created_at) on conflict(search_profile_id) do nothing;
  end if;
  return new;
end $$;
create trigger search_profiles_admin_observation after insert on public.search_profiles
  for each row execute function public.register_admin_search_observation();
create trigger search_profiles_admin_observation_owner after update of user_id on public.search_profiles
  for each row execute function public.register_admin_search_observation();

create function public.observe_admin_first_good() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if new.level in ('good','high') then
    if tg_op='INSERT' then
      update public.admin_search_observations set first_good_at=statement_timestamp()
        where search_profile_id=new.search_profile_id and first_good_at is null;
    elsif old.level not in ('good','high') then
      update public.admin_search_observations set first_good_at=statement_timestamp()
        where search_profile_id=new.search_profile_id and first_good_at is null;
    end if;
  end if;
  return new;
end $$;
create trigger matches_admin_first_good after insert or update of level on public.matches
  for each row execute function public.observe_admin_first_good();
revoke all on function public.register_admin_search_observation(),public.observe_admin_first_good() from public,anon,authenticated;
grant execute on function public.register_admin_search_observation() to authenticated,service_role;
grant execute on function public.observe_admin_first_good() to service_role;

-- Decision metrics are a service-only aggregate. No per-user data leaves the RPC.
create function public.admin_decision_metrics(p_start timestamptz, p_end timestamptz, p_as_of timestamptz)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare v_result jsonb;
begin
  if p_start is null or p_end is null or p_as_of is null
     or not isfinite(p_start) or not isfinite(p_end) or not isfinite(p_as_of)
     or p_end <= p_start or p_end - p_start > interval '90 days' or p_as_of < p_end
     or p_as_of > now() + interval '1 minute'
     or (p_start at time zone 'America/Argentina/Buenos_Aires')::time <> time '00:00'
     or (p_end at time zone 'America/Argentina/Buenos_Aires')::time <> time '00:00' then
    raise exception 'invalid_metrics_range' using errcode = '22023';
  end if;

  with
  windows as (
    select 'current' as name, p_start as starts, p_end as ends
    union all select 'previous', p_start - (p_end - p_start), p_start
  ),
  users as materialized (
    select p.id, p.created_at from public.profiles p where p.role <> 'admin'
  ),
  tracking as (select first_value_tracking_since as since from public.admin_metric_observation where singleton),
  search_events as (
    select (e.props->>'profile_id')::bigint as id,e.user_id,min(e.created_at) as created_at
    from public.events e join users u on u.id=e.user_id
    where e.name='search_profile_created' and e.props->>'profile_id' ~ '^[0-9]{1,18}$'
    group by (e.props->>'profile_id')::bigint,e.user_id
  ),
  creations as (
    select o.search_profile_id as id,o.user_id,o.search_created_at as created_at,0 as priority
      from public.admin_search_observations o join users u on u.id=o.user_id
    union all select s.id,s.user_id,s.created_at,1 from public.search_profiles s join users u on u.id=s.user_id
    union all select e.id,e.user_id,e.created_at,2 from search_events e
  ),
  searches as materialized (
    select c.id,c.user_id,c.created_at,coalesce(s.enabled,false) as enabled,
      o.first_good_at as first_value_at,
      o.search_profile_id is not null and c.created_at >= t.since as observed
    from (select distinct on (id) id,user_id,created_at from creations order by id,priority,created_at) c
    cross join tracking t left join public.admin_search_observations o on o.search_profile_id=c.id
    left join public.search_profiles s on s.id=c.id
    where c.created_at < p_as_of
  ),
  human_events as materialized (
    select e.user_id, e.created_at from public.events e join users u on u.id=e.user_id
    where e.created_at >= p_start - (p_end-p_start) and e.created_at < p_end
      -- Only explicit human actions. Delivery, billing callbacks and pixel opens
      -- are not activity; receiving alert_sent never makes an account active.
      and e.name in ('search_profile_created','search_profile_updated','search_profile_deleted','search_profile_paused','search_profile_resumed',
        'listing_detail_viewed','listing_outbound_clicked','listing_saved','listing_discarded',
        'listing_status_changed','alert_clicked','channels_updated','notification_frequency_updated',
        'pro_cta_clicked','waitlist_joined','purchase_requested','checkout_started',
        'purchase_influence_answered','seller_questions_copied','seller_questions_shared',
        'lifecycle_email_clicked','email_feedback','bonus_trial_started')
  ),
  payments as materialized (
    select p.* from public.commercial_payments p join users u on u.id=p.user_id
    where p.paid_at < p_as_of
  ),
  first_payments as (select user_id, min(paid_at) as paid_at from payments group by user_id),
  window_metrics as (
    select w.name, jsonb_build_object(
      'signups', (select count(*) from users u where u.created_at >= w.starts and u.created_at < w.ends),
      'activationEligible', (select count(*) from users u where u.created_at >= w.starts
        and u.created_at < w.ends and u.created_at + interval '24 hours' <= w.ends),
      'activatedWithin24h', (select count(*) from users u where u.created_at >= w.starts
        and u.created_at < w.ends and u.created_at + interval '24 hours' <= w.ends
        and exists(select 1 from searches s where s.user_id=u.id and s.created_at >= u.created_at
          and s.created_at <= u.created_at + interval '24 hours' and s.created_at < w.ends)
        or u.created_at >= w.starts and u.created_at < w.ends and u.created_at + interval '24 hours' <= w.ends
          and exists(select 1 from public.events e where e.user_id=u.id and e.name='search_profile_created'
            and e.created_at >= u.created_at and e.created_at <= u.created_at+interval '24 hours' and e.created_at < w.ends)),
      'activeUsers', (select count(distinct e.user_id) from human_events e where e.created_at >= w.starts and e.created_at < w.ends),
      'searchesCreated', (select count(*) from searches s where s.created_at >= w.starts and s.created_at < w.ends),
      'firstValueEligible', (select count(*) from searches s where s.created_at >= w.starts and s.created_at < w.ends
        and s.created_at + interval '24 hours' <= w.ends and s.observed),
      'firstValueUnobserved', (select count(*) from searches s where s.created_at >= w.starts and s.created_at < w.ends
        and s.created_at + interval '24 hours' <= w.ends and not s.observed),
      'firstValueWithin24h', (select count(*) from searches s where s.created_at >= w.starts and s.created_at < w.ends
        and s.created_at + interval '24 hours' <= w.ends and s.observed
        and s.first_value_at >= s.created_at and s.first_value_at <= s.created_at+interval '24 hours' and s.first_value_at < w.ends),
      'firstValueMedianHours', (select percentile_cont(0.5) within group
        (order by extract(epoch from (s.first_value_at-s.created_at))/3600.0)
        from searches s where s.created_at >= w.starts and s.created_at < w.ends
          and s.created_at + interval '24 hours' <= w.ends and s.observed
          and s.first_value_at >= s.created_at and s.first_value_at <= s.created_at+interval '24 hours' and s.first_value_at < w.ends),
      -- A later refund never rewrites historical gross revenue.
      'grossRevenue', (select coalesce(sum(p.amount),0) from payments p where p.paid_at >= w.starts and p.paid_at < w.ends),
      'refunds', (select coalesce(sum(p.amount),0) from payments p where p.refunded_at >= w.starts and p.refunded_at < w.ends),
      'particularSales', (select count(*) from payments p where p.offer='pass_30' and p.paid_at >= w.starts and p.paid_at < w.ends),
      'agencyPayments', (select count(*) from payments p where p.offer='pro_monthly' and p.paid_at >= w.starts and p.paid_at < w.ends),
      'firstPayingUsers', (select count(*) from first_payments p where p.paid_at >= w.starts and p.paid_at < w.ends)
    ) as metrics from windows w
  ),
  days as (select d as starts from generate_series(p_start, p_end-interval '1 day', interval '1 day') d),
  daily as (
    select jsonb_agg(jsonb_build_object(
      'day', to_char(d.starts at time zone 'America/Argentina/Buenos_Aires','YYYY-MM-DD'),
      'signups', (select count(*) from users u where u.created_at >= d.starts and u.created_at < d.starts+interval '1 day'),
      'activeUsers', (select count(distinct e.user_id) from human_events e where e.created_at >= d.starts and e.created_at < d.starts+interval '1 day'),
      'searchesCreated', (select count(*) from searches s where s.created_at >= d.starts and s.created_at < d.starts+interval '1 day'),
      'grossRevenue', (select coalesce(sum(p.amount),0) from payments p where p.paid_at >= d.starts and p.paid_at < d.starts+interval '1 day'),
      'refunds', (select coalesce(sum(p.amount),0) from payments p where p.refunded_at >= d.starts and p.refunded_at < d.starts+interval '1 day')
    ) order by d.starts) as series from days d
  ),
  current_agency as (
    -- Deduplicate overlapping periods per account; retain the most recent
    -- effective paid period. This is paid access, not an authorized subscription.
    select distinct on (p.user_id) p.user_id, p.amount, p.period_start, p.period_end
    from payments p where p.offer='pro_monthly' and p.period_start <= p_as_of and p.period_end > p_as_of
      and (p.refunded_at is null or p.refunded_at > p_as_of)
    order by p.user_id, p.period_start desc, p.paid_at desc, p.id desc
  ),
  checkouts as materialized (
    select c.* from public.billing_checkouts c join users u on u.id=c.user_id where c.created_at < p_as_of
  )
  select jsonb_build_object('asOf',p_as_of,'start',p_start,'end',p_end,'previousStart',p_start-(p_end-p_start),
    'firstValueTrackingSince',(select since from tracking),
    'current',(select metrics from window_metrics where name='current'),
    'previous',(select metrics from window_metrics where name='previous'),
    'daily',(select series from daily),
    'currentState',jsonb_build_object(
      'enabledSearches',(select count(*) from searches s where s.enabled),
      'searchesWithoutValue24h',(select count(*) from searches s where s.enabled
        and s.created_at + interval '24 hours' <= p_as_of
        and not exists(select 1 from public.matches m where m.search_profile_id=s.id and m.level in ('good','high')
          and m.generated_at >= s.created_at and m.generated_at < p_as_of)),
      'pendingNotifications',(select count(*) from public.notifications n join users u on u.id=n.user_id
        where n.created_at < p_as_of and n.status in ('queued','digest')),
      'failedNotifications',(select count(*) from public.notifications n join users u on u.id=n.user_id
        where n.created_at < p_as_of and n.status='failed'),
      'pendingCheckouts',(select count(*) from checkouts c where c.status in ('creating','pending')),
      'checkoutSyncErrors',(select count(*) from checkouts c where c.sync_error is not null),
      'agencyMonthlyEquivalent',(select coalesce(sum(p.amount * 2592000 / extract(epoch from (p.period_end-p.period_start))),0) from current_agency p),
      -- One open checkout per user is enforced by billing_one_open_checkout.
      -- Require an actual provider resource and authorized recurring offer.
      'authorizedRecurringMrr',(select coalesce(sum(c.amount),0) from checkouts c
        where c.offer='pro_monthly' and c.status='authorized' and c.provider_id is not null)
    )) into v_result;
  return v_result;
end $$;

revoke all on function public.admin_decision_metrics(timestamptz,timestamptz,timestamptz) from public, anon, authenticated;
grant execute on function public.admin_decision_metrics(timestamptz,timestamptz,timestamptz) to service_role;
