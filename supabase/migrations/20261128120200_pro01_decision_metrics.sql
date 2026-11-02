-- PRO-01 · contact_message_copied counts as activity in admin_decision_metrics
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PRO-01; diseño
-- docs/superpowers/specs/2026-10-31-pro01-contacto-design.md, decisión 21).
--
-- The function as defined in 20261122120100_par02_decision_metrics_checklist.sql
-- (its latest definition), with one change: 'contact_message_copied' (copying
-- or opening the ready-to-send message in the user's email) joins the closed
-- list of human_events. seller_filter_set stays out: it always comes with
-- search_profile_created or search_profile_updated, which already count. Same
-- signature, security invoker, empty search_path and grants.

-- Decision metrics are a service-only aggregate. No per-user data leaves the RPC.
create or replace function public.admin_decision_metrics(p_start timestamptz, p_end timestamptz, p_as_of timestamptz)
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
        'purchase_influence_answered','seller_questions_copied','seller_questions_shared','risk_checklist_copied',
        'contact_message_copied',
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
