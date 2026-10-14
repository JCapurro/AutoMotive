-- Fase 2 de planes, 2.4 (docs/PLANES_2026-10.md): extending Particular.
--
--   pass_30 bought with a pass running   → its 30 days start when that pass ends
--   pass_30 bought after access ended    → 30 days from the approval, and the searches
--                                           the expiry paused come back, up to the plan's room
--
-- Amounts don't change and Agencia doesn't change. Approved by Juan on 2026-10-14.

-- When the account's running pass ends, if after p_at: the latest unrefunded
-- pass period, or a pass set by hand on the profile. Null without a running pass.
create function public.pass_extension_start(p_user uuid, p_at timestamptz) returns timestamptz
language sql stable security definer set search_path = '' as $$
  select greatest(
    (select max(cp.period_end) from public.commercial_payments cp
      where cp.user_id = p_user and cp.offer = 'pass_30' and cp.refunded_at is null and cp.period_end > p_at),
    (select p.plan_expires_at from public.profiles p
      where p.id = p_user and p.plan = 'pass' and p.plan_expires_at > p_at))
$$;

-- profiles.plan and plan_expires_at from the unrefunded payments that end in
-- the future: the plan of the latest one, until the end of its chain. A
-- period that has not started yet counts: if the running one is refunded and
-- its extension isn't, access lasts until the extension ends.
create function public.refresh_paid_access(p_user uuid) returns void
language sql security definer set search_path = '' as $$
  with latest as (
    select cp.offer from public.commercial_payments cp
     where cp.user_id = p_user and cp.refunded_at is null and cp.period_end > now()
     order by cp.period_end desc limit 1
  )
  update public.profiles p
     set plan = case l.offer when 'pass_30' then 'pass'::public.user_plan
                             when 'pro_monthly' then 'pro'::public.user_plan
                             else 'free'::public.user_plan end,
         plan_expires_at = (select max(cp.period_end) from public.commercial_payments cp
                             where cp.user_id = p_user and cp.refunded_at is null and cp.period_end > now()
                               and cp.offer = l.offer)
    from (select (select offer from latest) as offer) l
   where p.id = p_user
$$;

-- A purchase after access ended brings back the searches the expiry paused
-- (search_paused_by_plan), most recently paused first, up to the plan's room.
-- Runs inside the payment, so it never raises: a failure leaves the searches
-- paused, with a warning, and the payment goes through.
create function public.reactivate_paused_searches(p_user uuid) returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_room integer;
  v_count integer := 0;
begin
  begin
    select coalesce((a.v->'limits'->>'max_profiles')::integer, 0) - coalesce((a.v->>'active_searches')::integer, 0)
      into v_room from (select public.plan_limits_for(p_user) v) a;
    if coalesce(v_room, 0) <= 0 then
      return 0;
    end if;
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
  exception when others then
    raise warning 'reactivate_paused_searches: % (user %)', sqlerrm, p_user;
    return 0;
  end;
  return v_count;
end $$;

revoke all on function public.pass_extension_start(uuid, timestamptz), public.refresh_paid_access(uuid),
  public.reactivate_paused_searches(uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Checkout: a running pass can be extended (20261008, otherwise unchanged)
-- ---------------------------------------------------------------------------

create or replace function public.begin_billing_checkout(p_user uuid, p_offer text, p_email text, p_version text, p_expected_amount numeric)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_profile public.profiles; v_checkout public.billing_checkouts; v_config jsonb; v_price jsonb;
begin
  select * into v_profile from public.profiles where id=p_user for update;
  if v_profile.id is null then raise exception 'unknown_account'; end if;
  if not coalesce((select (value->>'enabled')::boolean from public.app_config where key='commercial_pilot'),false) then
    raise exception 'commercial_pilot_disabled'; end if;
  if p_offer is null or p_offer not in ('pass_30','pro_monthly') or p_email is null
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
    and not (p_offer = 'pass_30' and v_profile.plan = 'pass' and v_profile.plan_expires_at is not null) then
    raise exception 'paid_plan_already_active'; end if;
  select value into v_config from public.app_config where key='pro_offer';
  v_price := v_config->p_offer;
  if not coalesce(v_price->>'currency' = 'ARS' and (v_price->>'amount')::numeric > 0
    and (v_price->>'amount')::numeric = trunc((v_price->>'amount')::numeric)
    and (v_price->>'days')::int = 30 and length(v_config->>'version') > 0,false) then raise exception 'invalid_offer'; end if;
  if v_config->>'version' is distinct from p_version or (v_price->>'amount')::numeric is distinct from p_expected_amount then raise exception 'offer_changed'; end if;
  insert into public.billing_checkouts(user_id,offer,offer_version,amount,billing_email)
    values(p_user,p_offer,v_config->>'version',(v_price->>'amount')::numeric,p_email) returning * into v_checkout;
  insert into public.events(user_id,name,props) values(p_user,'checkout_started',jsonb_build_object('checkout_id',v_checkout.id,'offer',p_offer));
  return to_jsonb(v_checkout) || jsonb_build_object('new',true);
end $$;

-- ---------------------------------------------------------------------------
-- Mercado Pago payments (20261008): the period of a pass, access, reactivation
-- ---------------------------------------------------------------------------

create or replace function public.apply_mercadopago_payment(p_checkout uuid, p_reference text, p_status text,
  p_amount numeric, p_currency text, p_paid_at timestamptz, p_start timestamptz, p_end timestamptz)
returns bigint language plpgsql security definer set search_path = '' as $$
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
      or (v_checkout.offer='pass_30' and p_end <> p_start + interval '30 days') then raise exception 'invalid_payment_period'; end if;
    -- 2.4: a pass bought while another one runs starts when that one ends.
    if v_checkout.offer = 'pass_30' then
      v_had_pass := exists (select 1 from public.commercial_payments cp
                             where cp.user_id = v_checkout.user_id and cp.offer = 'pass_30')
                    or exists (select 1 from public.profiles p where p.id = v_checkout.user_id and p.plan = 'pass');
      v_until := public.pass_extension_start(v_checkout.user_id, p_paid_at);
      if v_until is not null then
        p_start := v_until;
        p_end := v_until + interval '30 days';
      end if;
    end if;
    insert into public.commercial_payments(user_id,offer,offer_version,amount,currency,provider,reference,
      paid_at,period_start,period_end,verified_by,note,checkout_id)
    values(v_checkout.user_id,v_checkout.offer,v_checkout.offer_version,v_checkout.amount,v_checkout.currency,
      'Mercado Pago',p_reference,p_paid_at,p_start,p_end,null,'Verificado por API de Mercado Pago',p_checkout) returning id into v_id;
    if v_checkout.offer='pass_30' then update public.billing_checkouts set status='paid' where id=p_checkout; end if;
    delete from public.pro_waitlist where user_id=v_checkout.user_id;
    insert into public.events(user_id,name,props) values(v_checkout.user_id,'payment_confirmed',
      jsonb_build_object('payment_id',v_id,'offer',v_checkout.offer,'amount',v_checkout.amount,'currency','ARS','verification','mercadopago_api'));
  else
    return v_id; -- Pending/rejected/authorized are never paid access.
  end if;
  perform public.refresh_paid_access(v_checkout.user_id);
  perform public.expire_commercial_access(v_checkout.user_id);
  if p_status = 'approved' and v_checkout.offer = 'pass_30' then
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
end $$;

-- ---------------------------------------------------------------------------
-- Payments recorded by an admin (20261007): the same extension and reactivation
-- ---------------------------------------------------------------------------

create or replace function public.record_commercial_payment(
  p_user uuid, p_offer text, p_provider text, p_reference text,
  p_paid_at timestamptz default now(), p_note text default null
) returns bigint language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := (select auth.uid()); v_id bigint; v_old public.commercial_payments;
  v_profile public.profiles; v_offer jsonb; v_cfg jsonb; v_start timestamptz; v_end timestamptz;
  v_renewal boolean; v_had_pass boolean;
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
  -- Agencia renews ahead and, since 2.4, a running pass extends; nothing else stacks.
  v_renewal := v_profile.plan_expires_at is not null
    and ((v_profile.plan = 'pro' and p_offer = 'pro_monthly') or (v_profile.plan = 'pass' and p_offer = 'pass_30'));
  if v_profile.plan <> 'free' and (v_profile.plan_expires_at is null or v_profile.plan_expires_at > now())
    and not v_renewal then
    raise exception 'paid_plan_already_active';
  end if;
  select value into v_cfg from public.app_config where key = 'pro_offer';
  v_offer := v_cfg->p_offer;
  if not coalesce(v_offer->>'currency' = 'ARS' and (v_offer->>'amount')::numeric > 0
    and (v_offer->>'days')::int = 30 and length(v_cfg->>'version') > 0, false) then raise exception 'invalid_offer'; end if;
  v_had_pass := p_offer = 'pass_30' and (v_profile.plan = 'pass'
    or exists (select 1 from public.commercial_payments cp where cp.user_id = p_user and cp.offer = 'pass_30'));
  v_start := case when v_renewal then greatest(v_profile.plan_expires_at, p_paid_at) else p_paid_at end;
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
  if p_offer = 'pass_30' then
    if v_start = p_paid_at then
      perform public.reactivate_paused_searches(p_user);
    end if;
    if v_had_pass then
      insert into public.events(user_id, name, props) values(p_user, 'pass_extended',
        jsonb_build_object('payment_id', v_id, 'before_expiry', v_start > p_paid_at, 'new_expires_at', v_end));
    end if;
  end if;
  return v_id;
end $$;

notify pgrst, 'reload schema';
