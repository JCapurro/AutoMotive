-- Pase de 7 días (Juan, 05/11/2026): an entry pass, Particular for 7 days at
-- $5.000, next to the 30-day one at $15.000. It buys the same plan ('pass'),
-- extends a running pass like the 30-day one (2.4) and is refunded the same
-- way. The offers stay in app_config.pro_offer; its version doesn't change,
-- so checkouts already open for pass_30 or pro_monthly keep working.
--
-- Also here, for the expiry screen (docs/PASE_7_Y_PERDIDAS.md):
-- missed_since_expiry(), what the account's paused searches found since its
-- access ended, counted in expired_search_matches (2.5).

-- ---------------------------------------------------------------------------
-- The offer
-- ---------------------------------------------------------------------------

-- The pass family, and how many days each offer buys.
create function public.is_pass_offer(p_offer text) returns boolean
language sql immutable set search_path = '' as $$
  select p_offer in ('pass_30', 'pass_7')
$$;
create function public.offer_days(p_offer text) returns integer
language sql immutable set search_path = '' as $$
  select case p_offer when 'pass_7' then 7 else 30 end
$$;

alter table public.pro_waitlist drop constraint pro_waitlist_plan_check;
alter table public.pro_waitlist add constraint pro_waitlist_plan_check
  check (plan in ('pro_monthly', 'pass_30', 'pass_7', 'pass_90'));
alter table public.commercial_payments drop constraint commercial_payments_offer_check;
alter table public.commercial_payments add constraint commercial_payments_offer_check
  check (offer in ('pass_30', 'pass_7', 'pro_monthly'));
alter table public.billing_checkouts drop constraint billing_checkouts_offer_check;
alter table public.billing_checkouts add constraint billing_checkouts_offer_check
  check (offer in ('pass_30', 'pass_7', 'pro_monthly'));

update public.app_config
   set value = value || '{"pass_7": {"days": 7, "amount": 5000, "currency": "ARS"}}'::jsonb
 where key = 'pro_offer' and not value ? 'pass_7';

-- ---------------------------------------------------------------------------
-- Payments: the bodies in production on 05/11 (20261021120000 and before),
-- with pass_30 read as the pass family and its 30 days as offer_days.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.begin_billing_checkout(p_user uuid, p_offer text, p_email text, p_version text, p_expected_amount numeric)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_profile public.profiles; v_checkout public.billing_checkouts; v_config jsonb; v_price jsonb;
begin
  select * into v_profile from public.profiles where id=p_user for update;
  if v_profile.id is null then raise exception 'unknown_account'; end if;
  if not coalesce((select (value->>'enabled')::boolean from public.app_config where key='commercial_pilot'),false) then
    raise exception 'commercial_pilot_disabled'; end if;
  if p_offer is null or p_offer not in ('pass_30','pass_7','pro_monthly') or p_email is null
    or length(p_email) not between 3 and 254 or p_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
    raise exception 'invalid_checkout'; end if;
  select * into v_checkout from public.billing_checkouts where user_id=p_user
    and status in ('creating','pending','authorized','paused');
  if v_checkout.id is not null then
    if v_checkout.offer <> p_offer then raise exception 'checkout_already_open'; end if;
    if v_checkout.offer_version is distinct from p_version or v_checkout.amount is distinct from p_expected_amount then raise exception 'offer_changed'; end if;
    return to_jsonb(v_checkout) || jsonb_build_object('new',false);
  end if;
  -- 2.4: a running pass can be extended; any other paid plan has to end first.
  if v_profile.plan <> 'free' and (v_profile.plan_expires_at is null or v_profile.plan_expires_at > now())
    and not (public.is_pass_offer(p_offer) and v_profile.plan = 'pass' and v_profile.plan_expires_at is not null) then
    raise exception 'paid_plan_already_active'; end if;
  select value into v_config from public.app_config where key='pro_offer';
  v_price := v_config->p_offer;
  if not coalesce(v_price->>'currency' = 'ARS' and (v_price->>'amount')::numeric > 0
    and (v_price->>'amount')::numeric = trunc((v_price->>'amount')::numeric)
    and (v_price->>'days')::int = public.offer_days(p_offer) and length(v_config->>'version') > 0,false) then raise exception 'invalid_offer'; end if;
  if v_config->>'version' is distinct from p_version or (v_price->>'amount')::numeric is distinct from p_expected_amount then raise exception 'offer_changed'; end if;
  insert into public.billing_checkouts(user_id,offer,offer_version,amount,billing_email)
    values(p_user,p_offer,v_config->>'version',(v_price->>'amount')::numeric,p_email) returning * into v_checkout;
  insert into public.events(user_id,name,props) values(p_user,'checkout_started',jsonb_build_object('checkout_id',v_checkout.id,'offer',p_offer));
  return to_jsonb(v_checkout) || jsonb_build_object('new',true);
end $function$

;

CREATE OR REPLACE FUNCTION public.apply_mercadopago_payment(p_checkout uuid, p_reference text, p_status text, p_amount numeric, p_currency text, p_paid_at timestamp with time zone, p_start timestamp with time zone, p_end timestamp with time zone)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_checkout public.billing_checkouts; v_old public.commercial_payments; v_id bigint;
  v_until timestamptz; v_had_pass boolean := false;
begin
  select * into v_checkout from public.billing_checkouts where id=p_checkout;
  if v_checkout.id is null then raise exception 'unknown_checkout'; end if;
  if p_reference is null or p_reference !~ '^[0-9]+$' or p_currency is distinct from v_checkout.currency
    or p_amount is distinct from v_checkout.amount then raise exception 'payment_mismatch'; end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('Mercado Pago:' || p_reference,0));
  perform 1 from public.profiles where id=v_checkout.user_id for update;
  select * into v_old from public.commercial_payments where provider='Mercado Pago' and reference=p_reference;
  if v_old.id is not null and (v_old.user_id <> v_checkout.user_id or v_old.offer <> v_checkout.offer
    or (v_old.checkout_id is not null and v_old.checkout_id <> p_checkout)) then raise exception 'payment_reference_conflict'; end if;
  v_id := v_old.id;
  if p_status in ('refunded','charged_back') and v_id is null then
    if p_paid_at is null or p_start is null or p_end is null or p_end <= p_start
      or p_end > p_start + interval '32 days' then raise exception 'invalid_payment_period'; end if;
    insert into public.commercial_payments(user_id,offer,offer_version,amount,currency,provider,reference,
      paid_at,period_start,period_end,verified_by,note,checkout_id)
    values(v_checkout.user_id,v_checkout.offer,v_checkout.offer_version,v_checkout.amount,v_checkout.currency,
      'Mercado Pago',p_reference,p_paid_at,p_start,p_end,null,'Verificado por API de Mercado Pago',p_checkout) returning id into v_id;
  end if;
  if p_status in ('refunded','charged_back') then
    update public.commercial_payments set refunded_at=coalesce(refunded_at,now()),refund_reference=p_status || ':' || p_reference where id=v_id;
  elsif p_status = 'approved' then
    if v_id is not null then return v_id; end if; -- Includes refunded rows: a stale approval never restores them.
    if p_paid_at is null or p_paid_at > now() + interval '1 minute' or p_start is null or p_end is null
      or p_start > p_paid_at + interval '1 minute' or p_end <= p_start or p_end > p_start + interval '32 days'
      or (public.is_pass_offer(v_checkout.offer) and p_end <> p_start + make_interval(days => public.offer_days(v_checkout.offer))) then raise exception 'invalid_payment_period'; end if;
    -- 2.4: a pass bought while another one runs starts when that one ends.
    if public.is_pass_offer(v_checkout.offer) then
      v_had_pass := exists (select 1 from public.commercial_payments cp
                             where cp.user_id = v_checkout.user_id and public.is_pass_offer(cp.offer))
                    or exists (select 1 from public.profiles p where p.id = v_checkout.user_id and p.plan = 'pass');
      v_until := public.pass_extension_start(v_checkout.user_id, p_paid_at);
      if v_until is not null then
        p_start := v_until;
        p_end := v_until + make_interval(days => public.offer_days(v_checkout.offer));
      end if;
    end if;
    insert into public.commercial_payments(user_id,offer,offer_version,amount,currency,provider,reference,
      paid_at,period_start,period_end,verified_by,note,checkout_id)
    values(v_checkout.user_id,v_checkout.offer,v_checkout.offer_version,v_checkout.amount,v_checkout.currency,
      'Mercado Pago',p_reference,p_paid_at,p_start,p_end,null,'Verificado por API de Mercado Pago',p_checkout) returning id into v_id;
    if public.is_pass_offer(v_checkout.offer) then update public.billing_checkouts set status='paid' where id=p_checkout; end if;
    delete from public.pro_waitlist where user_id=v_checkout.user_id;
    insert into public.events(user_id,name,props) values(v_checkout.user_id,'payment_confirmed',
      jsonb_build_object('payment_id',v_id,'offer',v_checkout.offer,'amount',v_checkout.amount,'currency','ARS','verification','mercadopago_api'));
  else
    return v_id; -- Pending/rejected/authorized are never paid access.
  end if;
  perform public.refresh_paid_access(v_checkout.user_id);
  perform public.expire_commercial_access(v_checkout.user_id);
  if p_status = 'approved' and public.is_pass_offer(v_checkout.offer) then
    if v_until is null then
      perform public.reactivate_paused_searches(v_checkout.user_id);
    end if;
    if v_had_pass then
      insert into public.events(user_id,name,props) values(v_checkout.user_id,'pass_extended',
        jsonb_build_object('payment_id',v_id,'before_expiry',v_until is not null,
          'new_expires_at',(select plan_expires_at from public.profiles where id=v_checkout.user_id)));
    end if;
  end if;
  if p_status in ('refunded','charged_back') and v_old.refunded_at is null then
    insert into public.events(user_id,name,props) values(v_checkout.user_id,'payment_refunded',
      jsonb_build_object('payment_id',v_id,'amount',v_checkout.amount,'currency','ARS','verification','mercadopago_api','status',p_status));
  end if;
  return v_id;
end $function$

;

CREATE OR REPLACE FUNCTION public.record_commercial_payment(p_user uuid, p_offer text, p_provider text, p_reference text, p_paid_at timestamp with time zone DEFAULT now(), p_note text DEFAULT NULL::text)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_actor uuid := (select auth.uid()); v_id bigint; v_old public.commercial_payments;
  v_profile public.profiles; v_offer jsonb; v_cfg jsonb; v_start timestamptz; v_end timestamptz;
  v_renewal boolean; v_had_pass boolean;
begin
  if not exists(select 1 from public.profiles where id = v_actor and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  if p_offer not in ('pass_30','pass_7','pro_monthly') or p_offer is null
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
  -- Agencia renews ahead and, since 2.4, a running pass extends; nothing else stacks.
  v_renewal := v_profile.plan_expires_at is not null
    and ((v_profile.plan = 'pro' and p_offer = 'pro_monthly') or (v_profile.plan = 'pass' and public.is_pass_offer(p_offer)));
  if v_profile.plan <> 'free' and (v_profile.plan_expires_at is null or v_profile.plan_expires_at > now())
    and not v_renewal then
    raise exception 'paid_plan_already_active';
  end if;
  select value into v_cfg from public.app_config where key = 'pro_offer';
  v_offer := v_cfg->p_offer;
  if not coalesce(v_offer->>'currency' = 'ARS' and (v_offer->>'amount')::numeric > 0
    and (v_offer->>'days')::int = public.offer_days(p_offer) and length(v_cfg->>'version') > 0, false) then raise exception 'invalid_offer'; end if;
  v_had_pass := public.is_pass_offer(p_offer) and (v_profile.plan = 'pass'
    or exists (select 1 from public.commercial_payments cp where cp.user_id = p_user and public.is_pass_offer(cp.offer)));
  v_start := case when v_renewal then greatest(v_profile.plan_expires_at, p_paid_at) else p_paid_at end;
  v_end := v_start + make_interval(days => public.offer_days(p_offer));
  insert into public.commercial_payments(user_id, offer, offer_version, amount, currency, provider,
    reference, paid_at, period_start, period_end, verified_by, note)
  values(p_user, p_offer, v_cfg->>'version', (v_offer->>'amount')::numeric, 'ARS', trim(p_provider),
    trim(p_reference), p_paid_at, v_start, v_end, v_actor, left(p_note, 1000)) returning id into v_id;
  update public.profiles set plan = case when public.is_pass_offer(p_offer) then 'pass'::public.user_plan
    else 'pro'::public.user_plan end, plan_expires_at = v_end where id = p_user;
  delete from public.pro_waitlist where user_id = p_user;
  insert into public.events(user_id, name, props) values(p_user, 'payment_confirmed',
    jsonb_build_object('payment_id', v_id, 'offer', p_offer, 'amount', v_offer->'amount', 'currency','ARS', 'verified_by',v_actor));
  if public.is_pass_offer(p_offer) then
    if v_start = p_paid_at then
      perform public.reactivate_paused_searches(p_user);
    end if;
    if v_had_pass then
      insert into public.events(user_id, name, props) values(p_user, 'pass_extended',
        jsonb_build_object('payment_id', v_id, 'before_expiry', v_start > p_paid_at, 'new_expires_at', v_end));
    end if;
  end if;
  return v_id;
end $function$

;

CREATE OR REPLACE FUNCTION public.pass_extension_start(p_user uuid, p_at timestamp with time zone)
 RETURNS timestamp with time zone
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select greatest(
    (select max(cp.period_end) from public.commercial_payments cp
      where cp.user_id = p_user and public.is_pass_offer(cp.offer) and cp.refunded_at is null and cp.period_end > p_at),
    (select p.plan_expires_at from public.profiles p
      where p.id = p_user and p.plan = 'pass' and p.plan_expires_at > p_at))
$function$

;

CREATE OR REPLACE FUNCTION public.pass_started_at(p_user uuid)
 RETURNS timestamp with time zone
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select coalesce(
    (select max(cp.period_start) from public.commercial_payments cp
      where cp.user_id = p_user and public.is_pass_offer(cp.offer) and cp.refunded_at is null and cp.period_start <= now()
        and not exists (select 1 from public.commercial_payments q
                         where q.user_id = p_user and public.is_pass_offer(q.offer) and q.refunded_at is null
                           and q.period_end = cp.period_start)),
    (select p.plan_expires_at - interval '30 days' from public.profiles p where p.id = p_user))
$function$

;

CREATE OR REPLACE FUNCTION public.refresh_paid_access(p_user uuid)
 RETURNS void
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
  with latest as (
    select cp.offer from public.commercial_payments cp
     where cp.user_id = p_user and cp.refunded_at is null and cp.period_end > now()
     order by cp.period_end desc limit 1
  )
  update public.profiles p
     set plan = case l.offer when 'pass_30' then 'pass'::public.user_plan when 'pass_7' then 'pass'::public.user_plan
                             when 'pro_monthly' then 'pro'::public.user_plan
                             else 'free'::public.user_plan end,
         plan_expires_at = (select max(cp.period_end) from public.commercial_payments cp
                             where cp.user_id = p_user and cp.refunded_at is null and cp.period_end > now()
                               and cp.offer = l.offer)
    from (select (select offer from latest) as offer) l
   where p.id = p_user
$function$

;

CREATE OR REPLACE FUNCTION public.refund_commercial_payment(p_id bigint, p_reference text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
  update public.profiles set plan = case when public.is_pass_offer(v_access.offer) then 'pass'::public.user_plan
    when v_access.offer = 'pro_monthly' then 'pro'::public.user_plan else 'free'::public.user_plan end,
    plan_expires_at = v_access.period_end where id = v_payment.user_id;
  perform public.expire_commercial_access(v_payment.user_id);
  insert into public.events(user_id, name, props) values(v_payment.user_id, 'payment_refunded',
    jsonb_build_object('payment_id', p_id, 'amount', v_payment.amount, 'currency', 'ARS', 'verified_by', v_actor));
end $function$

;

CREATE OR REPLACE FUNCTION public.join_waitlist(p_plan text, p_placement text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_user uuid := (select auth.uid()); v_previous text; v_pilot boolean;
begin
  if v_user is null then raise exception 'authentication_required' using errcode = '42501'; end if;
  if p_plan is null or p_plan not in ('pass_30','pass_7','pro_monthly') then raise exception 'unknown_plan' using errcode = '22023'; end if;
  perform 1 from public.profiles where id = v_user for update;
  select plan into v_previous from public.pro_waitlist where user_id = v_user;
  if v_previous = p_plan then return; end if;
  insert into public.pro_waitlist(user_id, plan, placement) values(v_user,p_plan,left(p_placement,40))
    on conflict(user_id) do update set plan = excluded.plan, placement = excluded.placement;
  select coalesce((value->>'enabled')::boolean,false) into v_pilot from public.app_config where key = 'commercial_pilot';
  insert into public.events(user_id,name,props) values(v_user,
    case when v_pilot then 'purchase_requested' else 'waitlist_joined' end,
    jsonb_build_object('plan',p_plan,'placement',left(p_placement,40),'previous_plan',v_previous));
end $function$

;

-- ---------------------------------------------------------------------------
-- Emails before the end
-- ---------------------------------------------------------------------------

-- 20261022's, and no "te quedan 5 días" on a pass that lasts 10 days or less:
-- for the 7-day pass it would arrive 2 days after buying. It still gets the
-- email on the day it ends.
create or replace function public.pass_expiry_eligible(p_user uuid, p_kind text, p_event text) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'pass'
       and p.plan_expires_at is not null
       and extract(epoch from p.plan_expires_at)::bigint::text = p_event
       and coalesce((select (c.value->>'enabled')::boolean from public.app_config c
                      where c.key = 'commercial_pilot'), false)
       and case p_kind
             when 'pass_expiring' then p.plan_expires_at - interval '5 days' <= now()
                                   and now() < p.plan_expires_at - interval '4 days'
                                   and public.pass_started_at(p.id) < p.plan_expires_at - interval '10 days'
             when 'pass_expires_today' then (p.plan_expires_at at time zone 'America/Argentina/Buenos_Aires')::date
                                           = (now() at time zone 'America/Argentina/Buenos_Aires')::date
             else false end
      from public.profiles p where p.id = p_user), false)
$$;

-- ---------------------------------------------------------------------------
-- Metrics
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.admin_decision_metrics(p_start timestamp with time zone, p_end timestamp with time zone, p_as_of timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
AS $function$
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
        'contact_message_copied','duplicate_link_clicked','guide_viewed','guide_cta_clicked','guide_questions_copied',
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
      'particularSales', (select count(*) from payments p where public.is_pass_offer(p.offer) and p.paid_at >= w.starts and p.paid_at < w.ends),
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
end $function$

;

-- ---------------------------------------------------------------------------
-- The expiry screen: what the paused searches found since access ended
-- ---------------------------------------------------------------------------

-- The signed-in account's latest access end with counted listings, and how
-- many distinct listings its searches found after it (below: level high, as
-- the 2.5 email). Null while access runs or with nothing counted.
create function public.missed_since_expiry() returns jsonb
language sql stable security definer set search_path = '' as $$
  with me as (
    select (select auth.uid()) as uid
  ), ended as (
    select max(m.access_ended_at) as at
      from public.expired_search_matches m
      join public.search_profiles sp on sp.id = m.search_profile_id
      join me on sp.user_id = me.uid
  )
  select jsonb_build_object('ended_at', max(e.at), 'found', count(distinct m.listing_id),
                            'below', count(distinct m.listing_id) filter (where m.level = 'high'))
    from me
    cross join ended e
    join public.search_profiles sp on sp.user_id = me.uid
    join public.expired_search_matches m on m.search_profile_id = sp.id and m.access_ended_at = e.at
   where e.at is not null
     and public.plan_limits_for(me.uid)->>'state' = 'expired'
  having count(*) > 0
$$;
revoke all on function public.missed_since_expiry() from public, anon;
grant execute on function public.missed_since_expiry() to authenticated;
