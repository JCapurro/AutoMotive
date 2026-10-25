-- 7 días más con tu búsqueda (docs/MAILS_DE_PLAN.md, «Prueba extra de 7 días»).
--
-- Al 25/10/2026, las 14 pruebas de 72 h que terminaron no pagaron, y varias
-- habían encontrado cientos de autos sin abrir un solo email: probablemente
-- nunca vieron los resultados. A las que nunca pagaron se les ofrece, una vez,
-- 7 días más con su búsqueda. Se activa solo con un clic de la persona
-- (/app/bonus): reactivar sin pedirlo mandaría alertas a quien no las quiere.
--
--   kind                event key  due
--   bonus_trial_offer   bonus      7 days after the 72 h trial ended, never paid (replaces that day's 2.5 count)
--   bonus_trial_ending  bonus      5 days into the extra trial
--   bonus_trial_ended   bonus      when the extra trial ends without a purchase
--
-- profiles.bonus_trial_started_at marks the extra trial: plan_limits_for
-- answers 'trial' until 7 days later, so searches, alerts and the plan guards
-- work as in the first trial. When it ends, 2.5 counts from the new end.
--
-- Nacen apagados. bonus_trial.backfill_since deja que las pruebas que
-- terminaron antes de prenderlo reciban la oferta una vez.

alter table public.profiles add column bonus_trial_started_at timestamptz;
comment on column public.profiles.bonus_trial_started_at is
  'When the account accepted its one extra 7-day trial (bonus_trial_offer, /app/bonus). Null: never.';

alter table public.lifecycle_emails drop constraint lifecycle_emails_kind_check;
alter table public.lifecycle_emails add constraint lifecycle_emails_kind_check
  check (kind in ('trial_no_matches', 'trial_ended', 'pass_expiring', 'pass_expires_today',
                  'count_after_expiry', 'search_activated',
                  'search_abandoned', 'search_not_started', 'search_feedback',
                  'bonus_trial_offer', 'bonus_trial_ending', 'bonus_trial_ended'));

alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_remarketing;
alter function public.lifecycle_email_eligible(bigint) rename to lifecycle_email_eligible_remarketing;

insert into public.app_config (key, value) values ('bonus_trial', '{"backfill_since": "2026-10-01T00:00:00-03:00"}')
on conflict (key) do nothing;

update public.app_config
   set value = jsonb_set(value, '{kinds}', coalesce(value->'kinds', '{}')
         || '{"bonus_trial_offer": false, "bonus_trial_ending": false, "bonus_trial_ended": false}')
 where key = 'lifecycle_emails';

-- ---------------------------------------------------------------------------
-- Access: the extra trial is a trial
-- ---------------------------------------------------------------------------

-- The end of the free access: the 72 h trial, or the extra 7 days if they came later.
create function public.free_trial_end(p_started timestamptz, p_bonus timestamptz) returns timestamptz
language sql immutable set search_path = '' as $$
  select greatest(p_started + interval '72 hours', p_bonus + interval '7 days')
$$;

-- 20261018's, with trial_end from free_trial_end and the extra trial in the answer.
create or replace function public.plan_limits_for(p_user uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
  with cfg as (
    select coalesce((select value from public.app_config where key = 'plan_limits'), '{}') v
  ), access as (
    select p.*, coalesce((cfg.v->>'enforced')::boolean, false) enforced,
           p.plan <> 'free' and (p.plan_expires_at is null or p.plan_expires_at > now()) paid,
           public.free_trial_end(p.free_trial_started_at, p.bonus_trial_started_at) trial_end
    from public.profiles p cross join cfg where p.id = p_user
  ), resolved as (
    select *, case when role = 'admin' then 'pro' when paid then plan::text else 'free' end effective_plan,
           case when role = 'admin' then 'paid' when not enforced then 'pilot' when paid then 'paid'
                when free_trial_started_at is null then 'available'
                when trial_end > now() then 'trial' else 'expired' end state
    from access
  )
  select coalesce((select jsonb_build_object(
    'plan', r.effective_plan, 'enforced', r.enforced,
    'active', r.state in ('pilot', 'paid', 'trial'), 'state', r.state,
    'trial_started_at', r.free_trial_started_at, 'trial_expires_at', r.trial_end,
    'bonus_trial', r.bonus_trial_started_at is not null and r.state = 'trial'
                   and r.bonus_trial_started_at + interval '7 days' = r.trial_end,
    'expires_at', case when r.role = 'admin' then null when r.paid then r.plan_expires_at else r.trial_end end,
    'limits', case when r.role = 'admin' then '{"immediate_alerts":true}'::jsonb
                   else coalesce(cfg.v->r.effective_plan, '{}') end,
    'active_searches', (select count(*) from public.search_profiles sp where sp.user_id = p_user and sp.enabled))
    from resolved r cross join cfg),
    '{"plan":"free","enforced":true,"active":false,"state":"expired","limits":{"max_profiles":0}}'::jsonb)
$$;

-- 2.5 counts from the end of the free access, extra trial included.
create or replace function public.count_after_expiry_end(p_user uuid) returns timestamptz
language sql stable security definer set search_path = '' as $$
  select case
           when p.plan = 'pass' then greatest(p.plan_expires_at, p.free_trial_started_at + interval '72 hours')
           when p.plan = 'free' and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
             then public.free_trial_end(p.free_trial_started_at, p.bonus_trial_started_at)
         end
    from public.profiles p
   where p.id = p_user
     and public.lifecycle_contact_ok(p.id)
     and not public.commercial_access_active(p.id)
     and coalesce((select (c.value->>'enabled')::boolean from public.app_config c
                    where c.key = 'commercial_pilot'), false)
$$;

-- 20261030's, with the extra trial in the cheap filter.
create or replace function public.count_after_expiry_searches()
returns table (search_profile_id bigint, user_id uuid, ended_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select sp.id, sp.user_id, a.ended_at
    from public.profiles p
    cross join lateral (select public.count_after_expiry_end(p.id) as ended_at) a
    join public.search_profiles sp on sp.user_id = p.id and not sp.enabled
   where public.lifecycle_kind_on('count_after_expiry')
     -- Cheap first: a pass, a trial or an extra trial that ended in the last 22 days.
     and ((p.plan = 'pass' and p.plan_expires_at > now() - interval '22 days')
          or p.free_trial_started_at > now() - interval '22 days' - interval '72 hours'
          or p.bonus_trial_started_at > now() - interval '22 days' - interval '7 days')
     and a.ended_at > now() - interval '22 days'
     and not public.search_is_model_less(sp.filters)
     and exists (select 1 from public.events e
                  where e.user_id = p.id and e.name = 'search_paused_by_plan'
                    and e.props->>'search_profile_id' = sp.id::text
                    and e.created_at >= a.ended_at)
$$;

-- ---------------------------------------------------------------------------
-- Audiences
-- ---------------------------------------------------------------------------

-- The offer: a 72 h trial that ended, never paid (a refund counts as paid),
-- never had the extra trial, no checkout in progress, and its searches found something.
create function public.bonus_offer_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'free'
       and p.free_trial_started_at is not null
       and p.bonus_trial_started_at is null
       and public.plan_limits_for(p.id)->>'state' = 'expired'
       and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
       and not public.checkout_in_progress(p.id)
       and (exists (select 1 from public.matches m join public.search_profiles sp on sp.id = m.search_profile_id
                     where sp.user_id = p.id)
         or exists (select 1 from public.expired_search_matches x join public.search_profiles sp on sp.id = x.search_profile_id
                     where sp.user_id = p.id))
      from public.profiles p where p.id = p_user), false)
$$;

-- Days 5 to 7 of the extra trial, still in it.
create function public.bonus_ending_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.bonus_trial_started_at + interval '5 days' <= now()
       and public.plan_limits_for(p.id)->>'bonus_trial' = 'true'
      from public.profiles p where p.id = p_user), false)
$$;

-- The extra trial ended without a purchase and checkout is open (as 2.2).
create function public.bonus_ended_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'free'
       and p.bonus_trial_started_at is not null
       and public.plan_limits_for(p.id)->>'state' = 'expired'
       and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
       and not public.checkout_in_progress(p.id)
       and coalesce((select (c.value->>'enabled')::boolean from public.app_config c
                      where c.key = 'commercial_pilot'), false)
      from public.profiles p where p.id = p_user), false)
$$;

-- The offer goes out on day 7 instead of that day's count; a count claimed
-- while an offer is fresh is skipped.
create function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select case e.kind
           when 'bonus_trial_offer' then public.bonus_offer_eligible(e.user_id)
           when 'bonus_trial_ending' then public.bonus_ending_eligible(e.user_id)
           when 'bonus_trial_ended' then public.bonus_ended_eligible(e.user_id)
           when 'count_after_expiry' then public.lifecycle_email_eligible_remarketing(p_id)
             and not exists (select 1 from public.lifecycle_emails o
                              where o.user_id = e.user_id and o.kind = 'bonus_trial_offer'
                                and o.status in ('pending', 'sent') and o.created_at > now() - interval '5 days')
           else public.lifecycle_email_eligible_remarketing(p_id) end
    from public.lifecycle_emails e where e.id = p_id
$$;

-- ---------------------------------------------------------------------------
-- Claim
-- ---------------------------------------------------------------------------

-- Up to 3 cars the account's search found, opportunities first, newest next,
-- still published: what the offer shows so the email itself makes the case.
create function public.bonus_offer_cars(p_search bigint) returns jsonb
language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
           'title', c.title, 'year', c.year, 'price', c.price, 'currency', c.currency,
           'km', c.mileage_km, 'below', c.level = 'high')) order by c.rank), '[]'::jsonb)
    from (
      select l.title, l.year, l.price, l.currency, l.mileage_km, f.level,
             row_number() over (order by f.level = 'high' desc, f.seen_at desc, l.id desc) as rank
        from (select x.listing_id, x.level, x.created_at as seen_at
                from public.expired_search_matches x where x.search_profile_id = p_search
              union all
              select m.listing_id, m.level, m.generated_at
                from public.matches m where m.search_profile_id = p_search) f
        join public.listings l on l.id = f.listing_id
       where l.status = 'active' and not l.price_partial
       order by f.level = 'high' desc, f.seen_at desc, l.id desc
       limit 3) c
$$;

create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  v_since timestamptz;
  v_from timestamptz;
begin
  if p_kind not in ('bonus_trial_offer', 'bonus_trial_ending', 'bonus_trial_ended') then
    -- A count claimed while an offer is fresh is skipped at send time (lifecycle_email_eligible).
    return query select * from public.claim_lifecycle_emails_remarketing(p_kind, p_window, p_limit);
    return;
  end if;
  if p_window is null or coalesce(p_limit, 0) <= 0 then
    return;
  end if;

  if p_kind = 'bonus_trial_offer' then
    begin
      v_since := (select (c.value->>'backfill_since')::timestamptz from public.app_config c where c.key = 'bonus_trial');
    exception when others then
      v_since := null;
    end;
    v_from := least(now() - p_window, coalesce(v_since, now() - p_window));
    return query
    with due as materialized (
      select p.id as user_id, p.free_trial_started_at + interval '72 hours' as ended_at
        from public.profiles p
       where p.plan = 'free' and p.bonus_trial_started_at is null
         and p.free_trial_started_at + interval '72 hours' + interval '7 days' <= now()
         and p.free_trial_started_at + interval '72 hours' + interval '7 days' > v_from
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = p.id and e.kind = p_kind)
    ), picked as (
      -- The search that found the most, in the trial and since it ended.
      select d.user_id, d.ended_at, s.id as search_id, s.model, s.found_n, s.new_n, s.below_n
        from due d
        cross join lateral (
          select * from (
            select sp.id,
                   coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''), sp.name) as model,
                   (select count(*) from public.matches m where m.search_profile_id = sp.id) as found_n,
                   (select count(*) from public.expired_search_matches x where x.search_profile_id = sp.id) as new_n,
                   (select count(*) from public.expired_search_matches x
                     where x.search_profile_id = sp.id and x.level = 'high') as below_n
              from public.search_profiles sp
             where sp.user_id = d.user_id) c
           order by c.found_n + c.new_n desc, c.id desc
           limit 1) s
       where public.bonus_offer_eligible(d.user_id)
       order by d.ended_at, d.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
    select user_id, p_kind, 'bonus', search_id,
           jsonb_build_object('model', model, 'found', found_n, 'new', new_n, 'below', below_n,
                              'cars', public.bonus_offer_cars(search_id)),
           '/app/bonus'
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  else
    -- bonus_trial_ending (day 5) and bonus_trial_ended (day 7): what the extra trial found.
    return query
    with due as materialized (
      select p.id as user_id, p.bonus_trial_started_at as started_at,
             p.bonus_trial_started_at + case when p_kind = 'bonus_trial_ending' then interval '5 days'
                                             else interval '7 days' end as due_at
        from public.profiles p
       where p.bonus_trial_started_at is not null
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = p.id and e.kind = p_kind)
    ), picked as (
      select d.user_id, d.due_at, s.id as search_id, s.model, s.found_n, s.below_n
        from due d
        left join lateral (
          select sp.id,
                 coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''), sp.name) as model,
                 count(m.id) as found_n,
                 count(m.id) filter (where m.level = 'high') as below_n
            from public.search_profiles sp
            left join public.matches m on m.search_profile_id = sp.id and m.generated_at >= d.started_at
                                      and m.generated_at <= d.started_at + interval '7 days' and not m.is_backfill
           where sp.user_id = d.user_id
           group by sp.id
           order by count(m.id) desc, sp.id desc
           limit 1) s on true
       where d.due_at <= now() and d.due_at > now() - p_window
         and case when p_kind = 'bonus_trial_ending' then public.bonus_ending_eligible(d.user_id)
                  else public.bonus_ended_eligible(d.user_id) end
       order by d.due_at, d.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
    select user_id, p_kind, 'bonus', search_id,
           jsonb_build_object('model', model, 'found', coalesce(found_n, 0), 'below', coalesce(below_n, 0),
                              'ends_at', due_at + case when p_kind = 'bonus_trial_ending' then interval '2 days'
                                                       else interval '0' end),
           case when p_kind = 'bonus_trial_ending' and search_id is not null then '/app/searches/' || search_id
                when p_kind = 'bonus_trial_ending' then '/app'
                else '/app/pro?plan=pass_30' end
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Accepting it (/app/bonus) and measuring
-- ---------------------------------------------------------------------------

-- What /app/bonus shows the signed-in account: 'active' (with its end),
-- 'available' (an offer went out and it can take it), or 'unavailable'.
create function public.my_bonus_trial() returns jsonb
language sql stable security definer set search_path = '' as $$
  select case
           when public.plan_limits_for(p.id)->>'bonus_trial' = 'true'
             then jsonb_build_object('state', 'active', 'ends_at', p.bonus_trial_started_at + interval '7 days')
           when public.bonus_offer_eligible(p.id)
            and exists (select 1 from public.lifecycle_emails e
                         where e.user_id = p.id and e.kind = 'bonus_trial_offer' and e.status = 'sent')
             then jsonb_build_object('state', 'available', 'days', 7)
           else jsonb_build_object('state', 'unavailable')
         end
    from public.profiles p where p.id = (select auth.uid())
$$;

-- The button of /app/bonus: starts the extra trial, brings back the searches
-- the end paused (within the free plan's room) and records
-- bonus_trial_started. Once per account.
create function public.start_my_bonus_trial() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_user uuid := (select auth.uid());
  v_offer bigint;
  v_back integer;
  v_end timestamptz;
begin
  if v_user is null then
    raise exception 'authentication_required' using errcode = '42501';
  end if;
  perform 1 from public.profiles where id = v_user for update;
  if (select public.my_bonus_trial()->>'state') <> 'available' then
    return public.my_bonus_trial() || jsonb_build_object('started', false);
  end if;
  select e.id into v_offer from public.lifecycle_emails e
   where e.user_id = v_user and e.kind = 'bonus_trial_offer' and e.status = 'sent' order by e.sent_at desc limit 1;
  update public.profiles set bonus_trial_started_at = now() where id = v_user returning now() + interval '7 days' into v_end;
  -- reactivate_paused_searches' selection, without its purchase events: the
  -- searches the end paused, newest first, as many as the free plan holds.
  with room as (
    select greatest(coalesce((a.v->'limits'->>'max_profiles')::integer, 0)
                    - coalesce((a.v->>'active_searches')::integer, 0), 0) as n
      from (select public.plan_limits_for(v_user) v) a
  ), paused as (
    select sp.id
      from public.search_profiles sp
      join public.events e on e.user_id = sp.user_id and e.name = 'search_paused_by_plan'
                          and e.props->>'search_profile_id' = sp.id::text
     where sp.user_id = v_user and not sp.enabled
       and public.model_less_search_problem(v_user, sp.filters) is null
     group by sp.id
     order by max(e.created_at) desc, sp.id desc
     limit (select n from room)
  )
  update public.search_profiles sp set enabled = true from paused where sp.id = paused.id;
  get diagnostics v_back = row_count;
  insert into public.events (user_id, name, props) values (v_user, 'bonus_trial_started',
    jsonb_build_object('email_id', v_offer, 'searches_reactivated', v_back, 'ends_at', v_end));
  return jsonb_build_object('state', 'active', 'ends_at', v_end, 'started', true, 'searches_reactivated', v_back);
end $$;

-- bonus_trial_ended, once per account when its extra trial is over: what it
-- found, the alerts it got and opened, and whether it paid before the end.
create function public.record_bonus_trial_ends() returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_count integer;
begin
  with ended as (
    select p.id, p.bonus_trial_started_at as started_at, p.bonus_trial_started_at + interval '7 days' as ended_at
      from public.profiles p
     where p.role <> 'admin'
       and p.bonus_trial_started_at + interval '7 days' <= now()
       and not exists (select 1 from public.events e where e.user_id = p.id and e.name = 'bonus_trial_ended')
     limit 500
  )
  insert into public.events (user_id, name, props)
  select e.id, 'bonus_trial_ended', jsonb_build_object(
           'ended_at', e.ended_at,
           'results', (select count(*) from public.matches m
                         join public.search_profiles sp on sp.id = m.search_profile_id
                        where sp.user_id = e.id and m.generated_at between e.started_at and e.ended_at),
           'opportunities', (select count(*) from public.matches m
                               join public.search_profiles sp on sp.id = m.search_profile_id
                              where sp.user_id = e.id and m.generated_at between e.started_at and e.ended_at
                                and m.level = 'high'),
           'alerts_sent', (select count(*) from public.notifications n
                            where n.user_id = e.id and n.status = 'sent'
                              and n.created_at between e.started_at and e.ended_at),
           'alerts_clicked', (select count(*) from public.notifications n
                               where n.user_id = e.id and n.clicked_at is not null
                                 and n.created_at between e.started_at and e.ended_at),
           'converted', exists (select 1 from public.commercial_payments cp
                                 where cp.user_id = e.id and cp.refunded_at is null and cp.paid_at <= e.ended_at))
    from ended e;
  get diagnostics v_count = row_count;
  return v_count;
end $$;

revoke all on function public.claim_lifecycle_emails_remarketing(text, interval, integer),
  public.lifecycle_email_eligible_remarketing(bigint), public.bonus_offer_eligible(uuid),
  public.bonus_ending_eligible(uuid), public.bonus_ended_eligible(uuid), public.bonus_offer_cars(bigint),
  public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer),
  public.my_bonus_trial(), public.start_my_bonus_trial(), public.record_bonus_trial_ends()
  from public, anon, authenticated;
grant execute on function public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer),
  public.record_bonus_trial_ends() to service_role;
grant execute on function public.my_bonus_trial(), public.start_my_bonus_trial() to authenticated;

notify pgrst, 'reload schema';
