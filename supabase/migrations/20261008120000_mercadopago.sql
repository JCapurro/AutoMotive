-- Provider resources and verified payments are writable only by the server.
create table public.billing_checkouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  offer text not null check (offer in ('pass_30','pro_monthly')),
  offer_version text not null, amount numeric(12,2) not null check(amount > 0),
  currency text not null default 'ARS' check(currency = 'ARS'),
  billing_email text not null,
  status text not null default 'creating' check(status in ('creating','pending','authorized','paused','cancelled','failed','paid')),
  provider_id text unique, init_point text,
  created_at timestamptz not null default now(),
  last_synced_at timestamptz, sync_error text,
  next_payment_at timestamptz
);
create unique index billing_one_open_checkout on public.billing_checkouts(user_id)
  where status in ('creating','pending','authorized','paused');
alter table public.billing_checkouts enable row level security;
create policy "billing_checkouts: read own" on public.billing_checkouts
  for select to authenticated using(user_id = (select auth.uid()));
revoke all on public.billing_checkouts from anon, authenticated;
grant select on public.billing_checkouts to authenticated;
grant all on public.billing_checkouts to service_role;

alter table public.commercial_payments add column checkout_id uuid references public.billing_checkouts(id);

create function public.begin_billing_checkout(p_user uuid, p_offer text, p_email text, p_version text, p_expected_amount numeric)
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
  if v_profile.plan <> 'free' and (v_profile.plan_expires_at is null or v_profile.plan_expires_at > now()) then
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

-- The caller has fetched the current payment from Mercado Pago and verified its owner.
create function public.apply_mercadopago_payment(p_checkout uuid, p_reference text, p_status text,
  p_amount numeric, p_currency text, p_paid_at timestamptz, p_start timestamptz, p_end timestamptz)
returns bigint language plpgsql security definer set search_path = '' as $$
declare v_checkout public.billing_checkouts; v_old public.commercial_payments; v_id bigint; v_access public.commercial_payments;
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
  select * into v_access from public.commercial_payments where user_id=v_checkout.user_id and refunded_at is null
    and period_start <= now() and period_end > now() order by period_end desc limit 1;
  update public.profiles set plan=case when v_access.offer='pass_30' then 'pass'::public.user_plan
    when v_access.offer='pro_monthly' then 'pro'::public.user_plan else 'free'::public.user_plan end,
    plan_expires_at=v_access.period_end where id=v_checkout.user_id;
  perform public.expire_commercial_access(v_checkout.user_id);
  if p_status in ('refunded','charged_back') and v_old.refunded_at is null then
    insert into public.events(user_id,name,props) values(v_checkout.user_id,'payment_refunded',
      jsonb_build_object('payment_id',v_id,'amount',v_checkout.amount,'currency','ARS','verification','mercadopago_api','status',p_status));
  end if;
  return v_id;
end $$;
revoke all on function public.begin_billing_checkout(uuid,text,text,text,numeric),
  public.apply_mercadopago_payment(uuid,text,text,numeric,text,timestamptz,timestamptz,timestamptz) from public, anon, authenticated;
grant execute on function public.begin_billing_checkout(uuid,text,text,text,numeric),
  public.apply_mercadopago_payment(uuid,text,text,numeric,text,timestamptz,timestamptz,timestamptz) to service_role;

-- Removing account data cannot leave a known subscription charging indefinitely.
create function public.guard_billing_account_delete() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if exists(select 1 from public.billing_checkouts where user_id=old.id and offer='pro_monthly'
    and status in ('creating','pending','authorized','paused')) then raise exception 'cancel_subscription_before_deleting'; end if;
  return old;
end $$;
create trigger profiles_guard_billing_delete before delete on public.profiles
  for each row execute function public.guard_billing_account_delete();
revoke all on function public.guard_billing_account_delete() from public,anon,authenticated;

-- Keep provider ownership when a Telegram-only account merges into its web account.
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
    update public.billing_checkouts set user_id = v_target where user_id = v_prev;
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
