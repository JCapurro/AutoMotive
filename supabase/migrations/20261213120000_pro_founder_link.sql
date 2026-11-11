-- Precio fundador de Pro por link privado (decisión de Juan, 11/11/2026).
--
--   /fundador/<code>  →  /app/pro?fundador=<code>  →  begin_billing_checkout(..., p_founder_code)
--     └─ el código coincide y hay lugar ──> checkout pro_monthly a agency_founders.amount ($50.000)
--   primer pago aprobado de ese checkout ──> founder_number + founder_price_until (6 meses)
--
-- Pro sigue a $100.000 en /planes: el precio fundador solo existe para quien
-- entra con el link. Solo los checkouts del link toman un lugar de fundador;
-- antes cualquier pro_monthly lo tomaba mientras hubiera lugares.
--
-- Pasados los 6 meses la suscripción sigue cobrando $50.000 hasta que se suba
-- a mano (Mercado Pago guarda el monto de cada preapproval), con aviso 30 días
-- antes: ver docs/PLANES_2026-10.md.
--
-- agency_founders: slots (lugares), months (meses de precio fijo), amount
-- (precio fundador, ARS por mes) y code (el del link; cambiarlo desde
-- /admin/config invalida el link anterior; null lo cierra).

update public.app_config
   set value = value || jsonb_build_object('slots', 10, 'months', 6, 'amount', 50000,
                                           'code', substr(md5(random()::text || clock_timestamp()::text), 1, 12))
 where key = 'agency_founders';

alter table public.billing_checkouts
  add column founder_offer boolean not null default false,
  add constraint billing_checkouts_founder_offer_subscription
    check (not founder_offer or offer = 'pro_monthly');

-- The founder offer while the code matches and there are places, or null.
-- Places: founders already marked, plus founder checkouts still waiting for
-- their first payment (two days at most, the same as a stale checkout).
create function public.founder_offer(p_code text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  v_cfg jsonb;
  v_slots integer;
  v_months integer;
  v_amount integer;
  v_taken integer;
begin
  select value into v_cfg from public.app_config where key = 'agency_founders';
  v_slots := public.config_whole_number(v_cfg->'slots', 0, 1000);
  v_months := public.config_whole_number(v_cfg->'months', 1, 120);
  v_amount := public.config_whole_number(v_cfg->'amount', 1, 10000000);
  if p_code is null or length(p_code) < 8 or v_cfg->>'code' is null or v_cfg->>'code' <> p_code
     or coalesce(v_slots, 0) = 0 or v_months is null or v_amount is null then
    return null;
  end if;
  select count(*) into v_taken from public.billing_checkouts c
   where c.founder_number is not null
      or (c.founder_offer and c.founder_number is null and c.status in ('creating', 'pending')
          and c.created_at > now() - interval '2 days'
          and not exists(select 1 from public.commercial_payments p where p.checkout_id = c.id));
  return jsonb_build_object('amount', v_amount, 'months', v_months, 'slots', v_slots,
    'left', greatest(v_slots - v_taken, 0),
    'regular', (select (value->'pro_monthly'->>'amount')::numeric from public.app_config where key = 'pro_offer'));
end $$;
revoke all on function public.founder_offer(text) from public, anon, authenticated;
grant execute on function public.founder_offer(text) to service_role;

-- Same as 20261211120000_pass_7, plus p_founder_code. Dropped and created
-- again: an overload with a default would make the 5-argument call ambiguous.
-- Callers that pass 5 named arguments keep working through the default.
drop function public.begin_billing_checkout(uuid, text, text, text, numeric);
create function public.begin_billing_checkout(p_user uuid, p_offer text, p_email text, p_version text,
  p_expected_amount numeric, p_founder_code text default null)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_profile public.profiles; v_checkout public.billing_checkouts; v_config jsonb; v_price jsonb; v_founder jsonb;
  v_amount numeric;
begin
  select * into v_profile from public.profiles where id=p_user for update;
  if v_profile.id is null then raise exception 'unknown_account'; end if;
  if not coalesce((select (value->>'enabled')::boolean from public.app_config where key='commercial_pilot'),false) then
    raise exception 'commercial_pilot_disabled'; end if;
  if p_offer is null or p_offer not in ('pass_30','pass_7','pro_monthly') or p_email is null
    or length(p_email) not between 3 and 254 or p_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
    or (p_founder_code is not null and p_offer <> 'pro_monthly') then
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
  v_amount := (v_price->>'amount')::numeric;
  if p_founder_code is not null then
    -- One founder checkout at a time takes a place (mark_agency_founder uses the same lock).
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('agency_founders', 0));
    v_founder := public.founder_offer(p_founder_code);
    if v_founder is null then raise exception 'founder_invalid'; end if;
    if (v_founder->>'left')::int <= 0 then raise exception 'founder_full'; end if;
    v_amount := (v_founder->>'amount')::numeric;
  end if;
  if v_config->>'version' is distinct from p_version or v_amount is distinct from p_expected_amount then raise exception 'offer_changed'; end if;
  insert into public.billing_checkouts(user_id,offer,offer_version,amount,billing_email,founder_offer)
    values(p_user,p_offer,v_config->>'version',v_amount,p_email,p_founder_code is not null) returning * into v_checkout;
  insert into public.events(user_id,name,props) values(p_user,'checkout_started',jsonb_build_object('checkout_id',v_checkout.id,'offer',p_offer)
    || case when p_founder_code is not null then jsonb_build_object('founder', true, 'amount', v_amount) else '{}'::jsonb end);
  return to_jsonb(v_checkout) || jsonb_build_object('new',true);
end $function$;
revoke all on function public.begin_billing_checkout(uuid,text,text,text,numeric,text) from public, anon, authenticated;
grant execute on function public.begin_billing_checkout(uuid,text,text,text,numeric,text) to service_role;

-- Same as 20261019120000_agency_founders, but only a checkout started from
-- the founder link takes a place.
CREATE OR REPLACE FUNCTION public.mark_agency_founder()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_cfg jsonb;
  v_slots integer;
  v_months integer;
  v_number integer;
begin
  if new.offer <> 'pro_monthly' or new.checkout_id is null or new.refunded_at is not null then
    return new;
  end if;
  begin
    if not exists(select 1 from public.billing_checkouts c where c.id = new.checkout_id and c.founder_offer) then
      return new;
    end if;
    select value into v_cfg from public.app_config where key = 'agency_founders';
    v_slots := public.config_whole_number(v_cfg->'slots', 0, 1000);
    v_months := public.config_whole_number(v_cfg->'months', 1, 120);
    if v_slots is null or v_slots = 0 or v_months is null then
      return new;
    end if;
    -- One subscription at a time takes a slot.
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('agency_founders', 0));
    -- Only a subscription's first payment can make it a founder.
    if exists(select 1 from public.commercial_payments p where p.checkout_id = new.checkout_id and p.id <> new.id)
       or exists(select 1 from public.billing_checkouts c where c.id = new.checkout_id and c.founder_number is not null) then
      return new;
    end if;
    select min(n) into v_number from generate_series(1, v_slots) n
     where not exists(select 1 from public.billing_checkouts c where c.founder_number = n);
    if v_number is null then
      return new;
    end if;
    update public.billing_checkouts
       set founder_number = v_number, founder_price_until = new.paid_at + make_interval(months => v_months)
     where id = new.checkout_id and offer = 'pro_monthly';
    if found then
      insert into public.events(user_id, name, props) values (new.user_id, 'agency_founder_marked',
        jsonb_build_object('checkout_id', new.checkout_id, 'founder_number', v_number, 'amount', new.amount,
          'price_until', new.paid_at + make_interval(months => v_months)));
    end if;
  exception when others then
    raise warning 'mark_agency_founder: % (checkout %)', sqlerrm, new.checkout_id;
  end;
  return new;
end $function$;
