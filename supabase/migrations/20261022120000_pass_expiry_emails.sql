-- Fase 2 de planes, 2.3 (docs/MAILS_DE_PLAN.md): the two emails before a
-- Particular pass ends, now that 2.4 lets it be extended.
--
--   pass_expiring        5 days before the pass ends ("Te quedan 5 días de Ese Auto")
--   pass_expires_today   the Argentine calendar day it ends ("Hoy vence tu acceso a Ese Auto")
--
-- The event key is the pass's end (epoch seconds): an extension moves the
-- end, so the new end gets its own two emails and the old one gets none.

-- When the account's current pass started: the head of its chain of
-- unrefunded passes (an extension starts where the previous pass ends). A pass
-- set by hand without payments started 30 days before its end.
create function public.pass_started_at(p_user uuid) returns timestamptz
language sql stable security definer set search_path = '' as $$
  select coalesce(
    (select max(cp.period_start) from public.commercial_payments cp
      where cp.user_id = p_user and cp.offer = 'pass_30' and cp.refunded_at is null and cp.period_start <= now()
        and not exists (select 1 from public.commercial_payments q
                         where q.user_id = p_user and q.offer = 'pass_30' and q.refunded_at is null
                           and q.period_end = cp.period_start)),
    (select p.plan_expires_at - interval '30 days' from public.profiles p where p.id = p_user))
$$;

-- 2.3: the email is about the account's current pass end (p_event), and that
-- end is 5 days away (pass_expiring) or today in Argentina (pass_expires_today;
-- a pass that ended early that morning still gets it, see the template).
create function public.pass_expiry_eligible(p_user uuid, p_kind text, p_event text) returns boolean
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
             when 'pass_expires_today' then (p.plan_expires_at at time zone 'America/Argentina/Buenos_Aires')::date
                                           = (now() at time zone 'America/Argentina/Buenos_Aires')::date
             else false end
      from public.profiles p where p.id = p_user), false)
$$;

create or replace function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select case e.kind
             when 'trial_no_matches' then public.trial_no_matches_eligible(e.user_id)
             when 'trial_ended' then public.trial_ended_eligible(e.user_id)
             when 'pass_expiring' then public.pass_expiry_eligible(e.user_id, e.kind, e.event_key)
             when 'pass_expires_today' then public.pass_expiry_eligible(e.user_id, e.kind, e.event_key)
             else false end
      from public.lifecycle_emails e where e.id = p_id), false)
$$;

-- 20261020's claim, plus the two pass kinds.
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
  end if;
end $$;

revoke all on function public.pass_started_at(uuid), public.pass_expiry_eligible(uuid, text, text)
  from public, anon, authenticated;

-- Juan approved 2.3 with 2.4 (14/10/2026): both kinds on.
update public.app_config
   set value = jsonb_set(jsonb_set(value, '{kinds,pass_expiring}', 'true'), '{kinds,pass_expires_today}', 'true')
 where key = 'lifecycle_emails' and jsonb_typeof(value->'kinds') = 'object';

notify pgrst, 'reload schema';
