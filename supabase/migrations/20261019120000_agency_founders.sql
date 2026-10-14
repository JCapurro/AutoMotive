-- Planes 2026-10, 1.6 (precio fundador): the first Agencia subscriptions keep
-- the price they started with for a fixed time, also once Agencia becomes Pro.
--
--   first approved payment of a pro_monthly checkout
--     └─ a founder slot is free ──> founder_number, founder_price_until
--   every payment of the subscription refunded ──> the slot is free again
--
-- This only records who is a founder and until when. It changes no charge:
-- the price is the subscription's own billing_checkouts.amount, and phase 3
-- must read founder_price_until before raising a subscription's amount.

--   slots   subscriptions that are founders
--   months  how long their price stays fixed, from the first approved payment
insert into public.app_config(key, value) values ('agency_founders', '{"slots": 10, "months": 6}')
on conflict (key) do nothing;

alter table public.billing_checkouts
  add column founder_number smallint unique check (founder_number > 0),
  add column founder_price_until timestamptz,
  add constraint billing_checkouts_founder_complete
    check ((founder_number is null) = (founder_price_until is null)),
  add constraint billing_checkouts_founder_subscription
    check (founder_number is null or offer = 'pro_monthly');

-- A whole number within [p_min, p_max] from app_config, or null: a typo in
-- /admin/config must never raise inside a payment.
create function public.config_whole_number(p_value jsonb, p_min integer, p_max integer) returns integer
language sql immutable set search_path = '' as $$
  select case when jsonb_typeof(p_value) = 'number' and (p_value #>> '{}')::numeric between p_min and p_max
               and (p_value #>> '{}')::numeric % 1 = 0
    then (p_value #>> '{}')::numeric::integer end
$$;

-- Runs inside the transaction that records a payment, so it never raises:
-- a failure here leaves the subscription unmarked, with a warning, and the
-- payment goes through.
create function public.mark_agency_founder() returns trigger
language plpgsql security definer set search_path = '' as $$
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
end $$;
create trigger commercial_payments_mark_founder after insert on public.commercial_payments
  for each row execute function public.mark_agency_founder();

-- A subscription whose payments were all refunded never started: its slot
-- goes back. Same rule as above: it never raises inside a refund.
create function public.release_agency_founder() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_number integer;
begin
  if new.refunded_at is null or old.refunded_at is not null
     or new.offer <> 'pro_monthly' or new.checkout_id is null then
    return new;
  end if;
  begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('agency_founders', 0));
    select founder_number into v_number from public.billing_checkouts
     where id = new.checkout_id and founder_number is not null
       and not exists(select 1 from public.commercial_payments p
                       where p.checkout_id = new.checkout_id and p.refunded_at is null);
    if v_number is not null then
      update public.billing_checkouts set founder_number = null, founder_price_until = null
       where id = new.checkout_id;
      insert into public.events(user_id, name, props) values (new.user_id, 'agency_founder_released',
        jsonb_build_object('checkout_id', new.checkout_id, 'founder_number', v_number));
    end if;
  exception when others then
    raise warning 'release_agency_founder: % (checkout %)', sqlerrm, new.checkout_id;
  end;
  return new;
end $$;
create trigger commercial_payments_release_founder after update of refunded_at on public.commercial_payments
  for each row execute function public.release_agency_founder();

revoke all on function public.config_whole_number(jsonb, integer, integer), public.mark_agency_founder(),
  public.release_agency_founder() from public, anon, authenticated;

-- Subscriptions that already paid take the first slots, oldest first.
with cfg as (
  select public.config_whole_number(value->'slots', 0, 1000) slots, public.config_whole_number(value->'months', 1, 120) months
    from public.app_config where key = 'agency_founders'
), started as (
  select c.id, min(p.paid_at) as started_at
    from public.billing_checkouts c
    join public.commercial_payments p on p.checkout_id = c.id and p.refunded_at is null
   where c.offer = 'pro_monthly'
   group by c.id
), ranked as (
  select id, started_at, row_number() over (order by started_at, id) as n from started
)
update public.billing_checkouts c
   set founder_number = r.n, founder_price_until = r.started_at + make_interval(months => cfg.months)
  from ranked r cross join cfg
 where c.id = r.id and r.n <= cfg.slots;

notify pgrst, 'reload schema';
