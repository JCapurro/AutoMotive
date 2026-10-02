-- Ese Auto, ruta B / PIL-01. Keep existing pilot enforcement until explicit rollout.
alter table public.profiles add column free_trial_started_at timestamptz;

update public.app_config set value = jsonb_build_object(
  'enforced', coalesce((value->>'enforced')::boolean, false),
  'free', jsonb_build_object('max_profiles', 1, 'max_visible_results', 50, 'immediate_alerts', false),
  'pass', jsonb_build_object('max_profiles', 3, 'immediate_alerts', true),
  'pro', jsonb_build_object('max_profiles', 10, 'immediate_alerts', true))
where key = 'plan_limits';

insert into public.app_config(key, value) values
  ('pro_offer', '{"version":"ars-launch-2026-10","pass_30":{"amount":15000,"currency":"ARS","days":30},"pro_monthly":{"amount":75000,"currency":"ARS","days":30}}'),
  ('commercial_pilot', '{"enabled":false}')
on conflict(key) do update set value = excluded.value where app_config.key = 'pro_offer';

create or replace function public.plan_limits_for(p_user uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
  with cfg as (
    select coalesce((select value from public.app_config where key = 'plan_limits'), '{}') v
  ), access as (
    select p.*, coalesce((cfg.v->>'enforced')::boolean, false) enforced,
           p.plan <> 'free' and (p.plan_expires_at is null or p.plan_expires_at > now()) paid,
           p.free_trial_started_at + interval '72 hours' trial_end
    from public.profiles p cross join cfg where p.id = p_user
  ), resolved as (
    select *, case when paid then plan::text else 'free' end effective_plan,
           case when not enforced then 'pilot' when paid then 'paid'
                when free_trial_started_at is null then 'available'
                when trial_end > now() then 'trial' else 'expired' end state
    from access
  )
  select coalesce((select jsonb_build_object(
    'plan', r.effective_plan, 'enforced', r.enforced,
    'active', r.state in ('pilot', 'paid', 'trial'), 'state', r.state,
    'trial_started_at', r.free_trial_started_at, 'trial_expires_at', r.trial_end,
    'expires_at', case when r.paid then r.plan_expires_at else r.trial_end end,
    'limits', coalesce(cfg.v->r.effective_plan, '{}'),
    'active_searches', (select count(*) from public.search_profiles sp where sp.user_id = p_user and sp.enabled))
    from resolved r cross join cfg),
    '{"plan":"free","enforced":true,"active":false,"state":"expired","limits":{"max_profiles":0}}'::jsonb)
$$;

create function public.commercial_access_active(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((public.plan_limits_for(p_user)->>'active')::boolean, false)
$$;

create function public.search_access_active(p_search bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((select sp.enabled and public.commercial_access_active(sp.user_id)
    and (not (a.v->>'enforced')::boolean or
      (select count(*) from public.search_profiles other
        where other.user_id = sp.user_id and other.enabled and other.id <= sp.id)
      <= coalesce((a.v->'limits'->>'max_profiles')::int, 2147483647))
    from public.search_profiles sp cross join lateral (select public.plan_limits_for(sp.user_id) v) a
    where sp.id = p_search), false)
$$;

create function public.effective_search_frequency(p_user uuid, p_frequency public.notify_frequency)
returns public.notify_frequency language sql stable security definer set search_path = '' as $$
  select case when (a.v->>'enforced')::boolean
    and not coalesce((a.v->'limits'->>'immediate_alerts')::boolean, false)
    then 'daily'::public.notify_frequency else p_frequency end
  from (select public.plan_limits_for(p_user) v) a
$$;

-- Serialize activation through the account row; inactive searches don't consume capacity.
create or replace function public.enforce_plan_limits() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_access jsonb; v_count int; v_max int;
begin
  if not new.enabled then return new; end if;
  -- Only trusted server code can transfer ownership; link_telegram reconciles capacity.
  if tg_op = 'UPDATE' and old.user_id <> new.user_id then return new; end if;
  if tg_op = 'UPDATE' and old.enabled and old.user_id = new.user_id then return new; end if;
  perform 1 from public.profiles where id = new.user_id for update;
  v_access := public.plan_limits_for(new.user_id);
  if not (v_access->>'enforced')::boolean then
    v_max := (v_access->'limits'->>'max_profiles')::int;
    select count(*) into v_count from public.search_profiles where user_id = new.user_id and enabled and id <> new.id;
    if v_count >= v_max then
      insert into public.events(user_id,name,props) values(new.user_id,'plan_limit_hit',
        jsonb_build_object('limit','max_profiles','plan',v_access->>'plan','max',v_max,'current',v_count,'enforced',false)); end if;
    return new; end if;
  if v_access->>'state' = 'expired' then
    raise exception 'plan_access_expired' using errcode = 'P0001';
  end if;
  v_max := coalesce((v_access->'limits'->>'max_profiles')::int, 2147483647);
  select count(*) into v_count from public.search_profiles
    where user_id = new.user_id and enabled and id <> new.id;
  if v_count >= v_max then raise exception 'plan_limit_exceeded' using errcode = 'P0001'; end if;
  if v_access->>'state' = 'available' then
    update public.profiles set free_trial_started_at = now() where id = new.user_id;
    insert into public.events(user_id, name, props)
    values(new.user_id, 'free_trial_started', jsonb_build_object('expires_at', now() + interval '72 hours'));
  end if;
  return new;
end $$;
drop trigger search_profiles_enforce_plan_limits on public.search_profiles;
create trigger search_profiles_enforce_plan_limits before insert or update of enabled, user_id
on public.search_profiles for each row execute function public.enforce_plan_limits();

-- Store the desired frequency: readers resolve Free to daily and paid plans to the preference.
create or replace function public.enforce_plan_frequency() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_limits jsonb;
begin
  if new.notification_frequency <> 'immediate'
     or (tg_op = 'UPDATE' and old.notification_frequency = 'immediate') then
    return new;
  end if;
  v_limits := public.plan_limits_for(new.user_id);
  if coalesce((v_limits -> 'limits' ->> 'immediate_alerts')::boolean, true) then
    return new;
  end if;

  insert into public.events (user_id, name, props)
  values (new.user_id, 'plan_limit_hit', jsonb_build_object(
    'limit', 'immediate_alerts', 'plan', v_limits ->> 'plan', 'search_profile_id', new.id,
    'enforced', (v_limits ->> 'enforced')::boolean));

  -- Resolve the effective cadence when reading; retain the user preference.
  return new;
end;
$$;

revoke update(user_id) on public.search_profiles from authenticated;
revoke update on public.search_profiles from authenticated;
grant update(name, filters, preferences, raw_query, origin_lat, origin_lon, radius_km,
  notification_frequency, notify_min_level, channels, enabled, rematch_requested_at)
on public.search_profiles to authenticated;

create function public.expire_commercial_access(p_user uuid default null) returns integer
language plpgsql security definer set search_path = '' as $$
declare v_count int;
begin
  with paused as (
    update public.search_profiles sp set enabled = false
    where sp.enabled and (p_user is null or sp.user_id = p_user)
      and not public.search_access_active(sp.id) returning sp.user_id, sp.id
  ) insert into public.events(user_id, name, props)
    select user_id, 'search_paused_by_plan', jsonb_build_object('search_profile_id', id) from paused;
  get diagnostics v_count = row_count;
  update public.notifications n set status = 'skipped', error = 'plan_access_expired'
    where n.status in ('queued', 'digest') and (p_user is null or n.user_id = p_user)
      and not public.commercial_access_active(n.user_id);
  return v_count;
end $$;

create or replace function public.my_plan_limits() returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if (select auth.uid()) is null then raise exception 'authentication_required' using errcode = '42501'; end if;
  perform public.expire_commercial_access((select auth.uid()));
  return public.plan_limits_for((select auth.uid()));
end $$;

create function public.my_plan_snapshot() returns jsonb
language sql stable security definer set search_path = '' as $$
  select public.plan_limits_for((select auth.uid()))
$$;
revoke all on function public.my_plan_snapshot() from public, anon;
grant execute on function public.my_plan_snapshot() to authenticated;

-- In-flight batches may finish after expiry; do not write new personalized results.
create function public.guard_match_access() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if coalesce((select (value->>'enforced')::boolean from public.app_config where key = 'plan_limits'), false)
    and not public.search_access_active(new.search_profile_id) then return null; end if;
  return new;
end $$;
create trigger matches_guard_commercial before insert or update on public.matches
for each row execute function public.guard_match_access();

create function public.notification_access_active(p_user uuid, p_search bigint, p_listing bigint)
returns boolean language sql stable security definer set search_path = '' as $$
  select public.commercial_access_active(p_user) and (
    p_search is null or public.search_access_active(p_search) or exists (
      select 1 from public.user_listing_interactions i where i.user_id = p_user
        and i.listing_id = p_listing and (i.saved or i.status in ('interested','contacted','visit_scheduled'))))
$$;

create function public.guard_notification_access() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if not public.notification_access_active(new.user_id, new.search_profile_id, new.listing_id) then return null; end if;
  if new.kind in ('new_match','opportunity') and new.search_profile_id is not null
    and not public.search_access_active(new.search_profile_id) then return null; end if;
  if new.kind = 'digest' then
    new.payload := new.payload || jsonb_build_object('commercial_plan', public.plan_limits_for(new.user_id)->>'plan'); end if;
  if new.status = 'queued' and new.kind in ('new_match', 'opportunity')
    and public.effective_search_frequency(new.user_id, 'immediate') = 'daily' then
    new.status := 'digest';
  end if;
  return new;
end $$;
create trigger notifications_guard_commercial before insert on public.notifications
for each row execute function public.guard_notification_access();

create function public.prepare_notification_delivery(p_id bigint) returns boolean
language plpgsql security definer set search_path = '' as $$
declare n public.notifications;
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
    return false; end if;
  if n.kind in ('new_match', 'opportunity') and public.effective_search_frequency(n.user_id, 'immediate') = 'daily' then
    update public.notifications set status = 'digest' where id = p_id;
    return false;
  end if;
  return true;
end $$;

-- Enforce the 50-result view across normal RPC pages, including offset requests.
create or replace function public.search_results(
  p_profile_id bigint, p_filter text default 'all', p_sort text default 'recent',
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
    c.first_seen_at desc, c.listing_id desc
  limit least(greatest(coalesce(p_limit, 50), 0), greatest((select n from cap) - greatest(coalesce(p_offset, 0), 0), 0))
  offset greatest(coalesce(p_offset, 0), 0)
$$;

-- Pilot ledger: only administrators can verify external payments. No card data.
create table public.commercial_payments (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(id) on delete cascade,
  offer text not null check(offer in ('pass_30','pro_monthly')),
  offer_version text not null, amount numeric(12,2) not null check(amount > 0),
  currency text not null check(currency = 'ARS'), provider text not null,
  reference text not null, paid_at timestamptz not null,
  period_start timestamptz not null, period_end timestamptz not null check(period_end > period_start),
  verified_by uuid references public.profiles(id) on delete set null,
  verified_at timestamptz not null default now(), note text,
  refunded_at timestamptz, refunded_by uuid references public.profiles(id) on delete set null,
  refund_reference text, unique(provider, reference)
);
alter table public.commercial_payments enable row level security;
create policy "commercial_payments: read own" on public.commercial_payments
for select to authenticated using(user_id = (select auth.uid()));
revoke all on public.commercial_payments from anon, authenticated;
grant select on public.commercial_payments to authenticated;
grant all on public.commercial_payments to service_role;
grant usage, select on sequence public.commercial_payments_id_seq to service_role;

create function public.record_commercial_payment(
  p_user uuid, p_offer text, p_provider text, p_reference text,
  p_paid_at timestamptz default now(), p_note text default null
) returns bigint language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := (select auth.uid()); v_id bigint; v_old public.commercial_payments;
  v_profile public.profiles; v_offer jsonb; v_cfg jsonb; v_start timestamptz; v_end timestamptz;
begin
  if not exists(select 1 from public.profiles where id = v_actor and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  if p_offer not in ('pass_30','pro_monthly') or p_offer is null
    or p_provider is null or length(trim(p_provider)) not between 2 and 80
    or p_reference is null or length(trim(p_reference)) not between 3 and 160
    or p_paid_at is null or p_paid_at > now() or p_paid_at < now() - interval '30 days' then
    raise exception 'invalid_payment' using errcode = '22023';
  end if;
  -- Reference lock makes duplicate callbacks/forms idempotent, even across accounts.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(trim(p_provider) || ':' || trim(p_reference), 0));
  select * into v_old from public.commercial_payments where provider = trim(p_provider) and reference = trim(p_reference);
  if v_old.id is not null then
    if v_old.user_id <> p_user or v_old.offer <> p_offer then raise exception 'payment_reference_conflict'; end if;
    return v_old.id;
  end if;
  select * into v_profile from public.profiles where id = p_user for update;
  if v_profile.id is null then raise exception 'unknown_account'; end if;
  if v_profile.plan <> 'free' and (v_profile.plan_expires_at is null or v_profile.plan_expires_at > now())
    and not (v_profile.plan = 'pro' and p_offer = 'pro_monthly' and v_profile.plan_expires_at is not null) then
    raise exception 'paid_plan_already_active';
  end if;
  select value into v_cfg from public.app_config where key = 'pro_offer';
  v_offer := v_cfg->p_offer;
  if not coalesce(v_offer->>'currency' = 'ARS' and (v_offer->>'amount')::numeric > 0
    and (v_offer->>'days')::int = 30 and length(v_cfg->>'version') > 0, false) then raise exception 'invalid_offer'; end if;
  v_start := case when v_profile.plan = 'pro' and p_offer = 'pro_monthly'
    then greatest(v_profile.plan_expires_at, p_paid_at) else p_paid_at end;
  v_end := v_start + interval '30 days';
  insert into public.commercial_payments(user_id, offer, offer_version, amount, currency, provider,
    reference, paid_at, period_start, period_end, verified_by, note)
  values(p_user, p_offer, v_cfg->>'version', (v_offer->>'amount')::numeric, 'ARS', trim(p_provider),
    trim(p_reference), p_paid_at, v_start, v_end, v_actor, left(p_note, 1000)) returning id into v_id;
  update public.profiles set plan = case when p_offer = 'pass_30' then 'pass'::public.user_plan
    else 'pro'::public.user_plan end, plan_expires_at = v_end where id = p_user;
  delete from public.pro_waitlist where user_id = p_user;
  insert into public.events(user_id, name, props) values(p_user, 'payment_confirmed',
    jsonb_build_object('payment_id', v_id, 'offer', p_offer, 'amount', v_offer->'amount', 'currency','ARS', 'verified_by',v_actor));
  return v_id;
end $$;

create or replace function public.join_waitlist(p_plan text, p_placement text default null)
returns void language plpgsql security definer set search_path = '' as $$
declare v_user uuid := (select auth.uid()); v_previous text; v_pilot boolean;
begin
  if v_user is null then raise exception 'authentication_required' using errcode = '42501'; end if;
  if p_plan is null or p_plan not in ('pass_30','pro_monthly') then raise exception 'unknown_plan' using errcode = '22023'; end if;
  perform 1 from public.profiles where id = v_user for update;
  select plan into v_previous from public.pro_waitlist where user_id = v_user;
  if v_previous = p_plan then return; end if;
  insert into public.pro_waitlist(user_id, plan, placement) values(v_user,p_plan,left(p_placement,40))
    on conflict(user_id) do update set plan = excluded.plan, placement = excluded.placement;
  select coalesce((value->>'enabled')::boolean,false) into v_pilot from public.app_config where key = 'commercial_pilot';
  insert into public.events(user_id,name,props) values(v_user,
    case when v_pilot then 'purchase_requested' else 'waitlist_joined' end,
    jsonb_build_object('plan',p_plan,'placement',left(p_placement,40),'previous_plan',v_previous));
end $$;

create function public.decline_commercial_renewal() returns void
language plpgsql security definer set search_path = '' as $$
declare v_user uuid := (select auth.uid()); v_access jsonb;
begin
  perform 1 from public.profiles where id = v_user for update;
  v_access := public.plan_limits_for(v_user);
  if v_access->>'plan' <> 'pro' or not (v_access->>'active')::boolean then raise exception 'no_agency_period'; end if;
  if not exists(select 1 from public.events where user_id = v_user and name = 'renewal_declined'
    and props->>'period_end' = v_access->>'expires_at') then
    insert into public.events(user_id,name,props) values(v_user,'renewal_declined',
      jsonb_build_object('period_end',v_access->>'expires_at'));
  end if;
end $$;
revoke all on function public.decline_commercial_renewal() from public, anon;
grant execute on function public.decline_commercial_renewal() to authenticated;

-- Assisted searches are available before activation, but not after all access expires.
create function public.guard_assisted_commercial_access() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.kind = 'parse_search' and public.plan_limits_for(new.user_id)->>'state' = 'expired' then
    raise exception 'plan_access_expired'; end if;
  return new;
end $$;
create trigger llm_jobs_guard_commercial before insert on public.llm_jobs
for each row execute function public.guard_assisted_commercial_access();
revoke all on function public.guard_assisted_commercial_access() from public, anon, authenticated;

create function public.refund_commercial_payment(p_id bigint, p_reference text) returns void
language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := (select auth.uid()); v_payment public.commercial_payments; v_access public.commercial_payments;
begin
  if not exists(select 1 from public.profiles where id = v_actor and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501'; end if;
  if p_reference is null or length(trim(p_reference)) not between 3 and 160 then raise exception 'invalid_refund_reference'; end if;
  select * into v_payment from public.commercial_payments where id = p_id for update;
  if v_payment.id is null then raise exception 'unknown_payment'; end if;
  if v_payment.refunded_at is not null then return; end if;
  perform 1 from public.profiles where id = v_payment.user_id for update;
  -- Refund prepaid periods newest first so remaining access has no future gap.
  if exists(select 1 from public.commercial_payments where user_id = v_payment.user_id
    and refunded_at is null and period_end > v_payment.period_end) then
    raise exception 'refund_newer_period_first'; end if;
  update public.commercial_payments set refunded_at = now(), refunded_by = v_actor,
    refund_reference = trim(p_reference) where id = p_id;
  select * into v_access from public.commercial_payments where user_id = v_payment.user_id
    and refunded_at is null and period_start <= now() and period_end > now() order by period_end desc limit 1;
  update public.profiles set plan = case when v_access.offer = 'pass_30' then 'pass'::public.user_plan
    when v_access.offer = 'pro_monthly' then 'pro'::public.user_plan else 'free'::public.user_plan end,
    plan_expires_at = v_access.period_end where id = v_payment.user_id;
  perform public.expire_commercial_access(v_payment.user_id);
  insert into public.events(user_id, name, props) values(v_payment.user_id, 'payment_refunded',
    jsonb_build_object('payment_id', p_id, 'amount', v_payment.amount, 'currency', 'ARS', 'verified_by', v_actor));
end $$;

create function public.enable_commercial_pilot() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := (select auth.uid()); v_started int; v_paused int;
begin
  if not exists(select 1 from public.profiles where id = v_actor and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501'; end if;
  perform 1 from public.app_config where key = 'commercial_pilot' for update;
  if coalesce((select (value->>'enabled')::boolean from public.app_config where key = 'commercial_pilot'), false) then
    return jsonb_build_object('already_enabled',true); end if;
  with started as (
    update public.profiles p set free_trial_started_at = now()
      where p.free_trial_started_at is null and p.plan = 'free'
        and exists(select 1 from public.search_profiles sp where sp.user_id = p.id and sp.enabled)
      returning p.id
  ) insert into public.events(user_id, name, props)
    select id, 'free_trial_started', jsonb_build_object('rollout',true, 'expires_at', now() + interval '72 hours') from started;
  get diagnostics v_started = row_count;
  update public.app_config set value = jsonb_set(value,'{enforced}','true') where key = 'plan_limits';
  update public.app_config set value = '{"enabled":true}' where key = 'commercial_pilot';
  v_paused := public.expire_commercial_access();
  insert into public.events(user_id, name, props) values(v_actor, 'commercial_pilot_enabled',
    jsonb_build_object('trials_started',v_started, 'searches_paused',v_paused));
  return jsonb_build_object('trials_started',v_started, 'searches_paused',v_paused);
end $$;

-- Internal helpers are worker/service only, except the view checks used by invoker RPCs.
revoke all on function public.commercial_access_active(uuid), public.search_access_active(bigint),
  public.effective_search_frequency(uuid, public.notify_frequency), public.expire_commercial_access(uuid),
  public.notification_access_active(uuid,bigint,bigint), public.guard_match_access(),
  public.guard_notification_access(), public.prepare_notification_delivery(bigint) from public, anon, authenticated;
grant execute on function public.commercial_access_active(uuid), public.search_access_active(bigint),
  public.effective_search_frequency(uuid, public.notify_frequency), public.expire_commercial_access(uuid),
  public.notification_access_active(uuid,bigint,bigint), public.prepare_notification_delivery(bigint) to service_role;
grant execute on function public.plan_limits_for(uuid) to service_role;
revoke all on function public.record_commercial_payment(uuid,text,text,text,timestamptz,text),
  public.refund_commercial_payment(bigint,text), public.enable_commercial_pilot() from public, anon;
grant execute on function public.record_commercial_payment(uuid,text,text,text,timestamptz,text),
  public.refund_commercial_payment(bigint,text), public.enable_commercial_pilot() to authenticated;

create view public.commercial_revenue with(security_invoker = true) as
select
  (select count(*) from public.profiles p where p.role <> 'admin' and p.plan = 'pro'
    and p.plan_expires_at > now()) agency_accounts,
  (select coalesce(sum(cp.amount),0) from public.commercial_payments cp join public.profiles p on p.id = cp.user_id
    where p.role <> 'admin' and cp.offer = 'pro_monthly' and cp.refunded_at is null
      and cp.period_start <= now() and cp.period_end > now()) agency_monthly_equivalent,
  count(*) filter(where cp.offer = 'pass_30' and cp.refunded_at is null) particular_sales,
  coalesce(sum(cp.amount) filter(where cp.refunded_at is null),0) confirmed_revenue,
  (select coalesce(sum(r.amount),0) from public.commercial_payments r join public.profiles rp on rp.id = r.user_id
    where rp.role <> 'admin' and r.refunded_at >= date_trunc('month', now() at time zone 'America/Argentina/Buenos_Aires')
      at time zone 'America/Argentina/Buenos_Aires') refunds
from public.commercial_payments cp join public.profiles p on p.id = cp.user_id
where p.role <> 'admin' and cp.paid_at >= date_trunc('month', now() at time zone 'America/Argentina/Buenos_Aires')
  at time zone 'America/Argentina/Buenos_Aires';
revoke all on public.commercial_revenue from anon, authenticated;
grant select on public.commercial_revenue to service_role;

-- Account linking must not restart a consumed trial or erase payment history.
create or replace function public.link_telegram(p_code text, p_telegram_user_id bigint, p_chat_id bigint)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_target uuid;
  v_prev   uuid;
  v_anon   boolean := false;
  v_moved  integer := 0;
begin
  select id into v_target from public.profiles
   where telegram_link_code = p_code for update;
  if v_target is null then
    return null;
  end if;

  select p.id, coalesce(u.is_anonymous, false) into v_prev, v_anon
    from public.profiles p
    join auth.users u on u.id = p.id
   where p.telegram_user_id = p_telegram_user_id and p.id <> v_target;

  if v_prev is not null and v_anon then
    perform 1 from public.profiles where id = v_prev for update;
    -- Preserve the first trial clock when the bot account becomes a web account.
    if exists(select 1 from public.profiles a join public.profiles b on b.id = v_prev
      where a.id = v_target and a.plan <> 'free' and b.plan <> 'free'
        and (a.plan_expires_at is null or a.plan_expires_at > now())
        and (b.plan_expires_at is null or b.plan_expires_at > now())) then
      raise exception 'paid_account_merge_conflict'; end if;
    update public.profiles t set
      free_trial_started_at = least(t.free_trial_started_at, p.free_trial_started_at),
      plan = case when p.plan <> 'free' and (p.plan_expires_at is null or p.plan_expires_at > now()) then p.plan else t.plan end,
      plan_expires_at = case when p.plan <> 'free' and (p.plan_expires_at is null or p.plan_expires_at > now()) then p.plan_expires_at else t.plan_expires_at end
      from public.profiles p where t.id = v_target and p.id = v_prev;
    update public.commercial_payments set user_id = v_target where user_id = v_prev;
    update public.search_profiles set user_id = v_target where user_id = v_prev;
    get diagnostics v_moved = row_count;
    perform public.expire_commercial_access(v_target);
    insert into public.user_listing_interactions (user_id, listing_id, status, saved, rejection_reason, note)
    select v_target, listing_id, status, saved, rejection_reason, note
      from public.user_listing_interactions where user_id = v_prev
    on conflict (user_id, listing_id) do nothing;
    update public.owned_vehicles set user_id = v_target where user_id = v_prev;
    update public.notifications n set user_id = v_target
     where n.user_id = v_prev
       and not exists (select 1 from public.notifications t
                        where t.user_id = v_target and t.channel = n.channel
                          and t.dedupe_key = n.dedupe_key);
    update public.events set user_id = v_target where user_id = v_prev;
    update public.llm_jobs set user_id = v_target where user_id = v_prev;
    -- Whatever didn't move (duplicates) goes with the anonymous user.
    delete from auth.users where id = v_prev;
  elsif v_prev is not null then
    update public.profiles set telegram_user_id = null, telegram_chat_id = null where id = v_prev;
  end if;

  update public.profiles
     set telegram_user_id   = p_telegram_user_id,
         telegram_chat_id   = p_chat_id,
         telegram_link_code = replace(gen_random_uuid()::text, '-', '')
   where id = v_target;

  insert into public.events (user_id, name, props)
  values (v_target, 'telegram_linked',
          jsonb_build_object('merged_telegram_account', v_prev is not null and v_anon,
                             'moved_search_profiles', v_moved));
  return v_target;
end;
$$;
