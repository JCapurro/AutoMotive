-- Fase 2 de planes (docs/MAILS_DE_PLAN.md): the emails that lead to a
-- purchase. One ledger for every kind, one row per (account, kind, event):
-- the event key is what makes each email go out once, even if the worker
-- runs again or restarts. It replaces trial_reminders (20261017): the
-- free-trial reminder becomes kind 'trial_ended', with the phase 2 copy.
--
--   kind                event key             due
--   trial_no_matches    trial                 24 h after the trial started, no new match since (2.1)
--   trial_ended         trial                 when the 72 h trial ends without a purchase (2.2)
--   pass_expiring       <period end, epoch>   5 days before a pass ends (2.3, not yet)
--   pass_expires_today  <period end, epoch>   the day a pass ends (2.3, not yet)
--   count_after_expiry  <end epoch>:<days>    7, 14 and 21 days after access ended (2.5, not yet)
--
-- Not a notifications row: guard_notification_access drops rows of expired
-- accounts, and the alert metrics count every notification as an alert.

create table public.lifecycle_emails (
  id                bigint generated always as identity primary key,
  user_id           uuid not null references public.profiles(id) on delete cascade,
  kind              text not null check (kind in ('trial_no_matches', 'trial_ended',
                      'pass_expiring', 'pass_expires_today', 'count_after_expiry')),
  event_key         text not null,
  search_profile_id bigint references public.search_profiles(id) on delete set null,
  -- What the email says (model, counts), fixed when the row is claimed.
  payload           jsonb not null default '{}',
  -- Where its button leads: an Ese Auto path, reached through /m/<id>.
  target            text not null check (target ~ '^/[^/\\]'),
  status            text not null default 'pending'
    check (status in ('pending', 'sent', 'failed', 'skipped')),
  attempts          smallint not null default 0,
  error             text,
  provider_id       text,
  created_at        timestamptz not null default now(),
  sent_at           timestamptz,
  clicked_at        timestamptz,
  unique (user_id, kind, event_key)
);
-- The daily cap counts the rows claimed since the start of the Argentine day.
create index lifecycle_emails_created_at_idx on public.lifecycle_emails (created_at);
comment on table public.lifecycle_emails is
  'Send ledger of the plan emails (docs/MAILS_DE_PLAN.md): one row per account, kind and event. '
  'Kept out of notifications because its guards drop rows of expired accounts and its metrics would count them as alerts.';

alter table public.lifecycle_emails enable row level security;
revoke all on public.lifecycle_emails from public, anon, authenticated, service_role;
grant select, insert, update on public.lifecycle_emails to service_role;

-- The reminder's ledger moves over, so nobody gets the end of their trial twice.
insert into public.lifecycle_emails (user_id, kind, event_key, target, status, attempts, error,
                                     provider_id, created_at, sent_at)
select user_id, 'trial_ended', 'trial', '/app/pro?plan=pass_30', status, attempts, error,
       provider_id, created_at, sent_at
  from public.trial_reminders
on conflict (user_id, kind, event_key) do nothing;

-- ---------------------------------------------------------------------------
-- Configuration (/admin/config). The worker validates every value.
-- ---------------------------------------------------------------------------

--   enabled                 false stops claiming and sending every kind
--   send_from / send_until  send hours, Argentina, [from, until)
--   window_hours            a claimed email is still sendable this long; a rollout
--                           or a long outage never mails stale events
--   max_per_day             emails claimed per Argentine calendar day, all kinds
--                           (Resend's free tier is 100 a day, shared with alerts)
--   kinds                   each kind on or off
insert into public.app_config (key, value) values ('lifecycle_emails', '{
  "enabled": true, "send_from": "09:00", "send_until": "21:00", "window_hours": 48, "max_per_day": 30,
  "kinds": {"trial_no_matches": true, "trial_ended": true, "pass_expiring": false,
            "pass_expires_today": false, "count_after_expiry": false}}')
on conflict (key) do nothing;
-- Keep what was tuned for the reminder.
update public.app_config l set value = l.value || (r.value - 'delay_hours')
  from public.app_config r
 where l.key = 'lifecycle_emails' and r.key = 'trial_reminder' and jsonb_typeof(r.value) = 'object';
delete from public.app_config where key = 'trial_reminder';

drop function public.claim_trial_reminders(interval, interval, integer);
drop function public.trial_reminder_eligible(uuid);
drop table public.trial_reminders;

-- ---------------------------------------------------------------------------
-- Audiences: checked when claiming and again just before sending
-- ---------------------------------------------------------------------------

-- Anyone a plan email may go to: not an admin, with an email address and the
-- email channel kept (/baja and Ajustes remove it: the opt-out holds).
create function public.lifecycle_contact_ok(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select p.role <> 'admin' and p.email is not null and 'email' = any(p.default_channels)
      from public.profiles p where p.id = p_user), false)
$$;

-- 2.1: still in the trial, 24 h after it started, without a new match since.
create function public.trial_no_matches_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'free'
       and p.free_trial_started_at is not null
       and p.free_trial_started_at + interval '24 hours' <= now()
       and public.plan_limits_for(p.id)->>'state' = 'trial'
       and exists (select 1 from public.search_profiles sp where sp.user_id = p.id and sp.enabled)
       and not exists (select 1 from public.matches m
                         join public.search_profiles sp on sp.id = m.search_profile_id
                        where sp.user_id = p.id and not m.is_backfill
                          and m.generated_at >= p.free_trial_started_at)
      from public.profiles p where p.id = p_user), false)
$$;

-- 2.2: the trial ended and the account never bought (a refunded payment still
-- counts), has no checkout in progress and can buy now.
create function public.trial_ended_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'free'
       and p.free_trial_started_at is not null
       -- 'expired' implies plan_limits.enforced, the trial over and nothing paid now.
       and public.plan_limits_for(p.id)->>'state' = 'expired'
       and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
       -- A checkout in progress; cash tickets accredit late, but a pending
       -- checkout older than 72 h is abandoned and stops blocking.
       and not exists (select 1 from public.billing_checkouts bc where bc.user_id = p.id
             and (bc.status in ('creating', 'authorized', 'paused')
               or (bc.status = 'pending' and bc.created_at > now() - interval '72 hours')
               or (bc.sync_error is not null and bc.status not in ('failed', 'cancelled', 'paid'))))
       -- No point inviting to buy while checkout is closed.
       and coalesce((select (c.value->>'enabled')::boolean from public.app_config c
                      where c.key = 'commercial_pilot'), false)
      from public.profiles p where p.id = p_user), false)
$$;

create function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select case e.kind
             when 'trial_no_matches' then public.trial_no_matches_eligible(e.user_id)
             when 'trial_ended' then public.trial_ended_eligible(e.user_id)
             else false end
      from public.lifecycle_emails e where e.id = p_id), false)
$$;

-- ---------------------------------------------------------------------------
-- Claim: inserts the due rows ('pending') with what their email says
-- ---------------------------------------------------------------------------

-- Up to p_limit due accounts for one kind, oldest event first. An event already
-- in the ledger is never claimed again; the database clock decides what is due.
create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
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
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Measuring (events)
-- ---------------------------------------------------------------------------

-- /m/<id>, the button of a plan email: lifecycle_email_clicked on every click
-- (clicked_at keeps the first) and where to go. Null for an unknown or unsent email.
create function public.track_lifecycle_click(p_id bigint) returns text
language plpgsql security definer set search_path = '' as $$
declare
  v public.lifecycle_emails;
begin
  update public.lifecycle_emails set clicked_at = coalesce(clicked_at, now())
   where id = p_id and status = 'sent'
  returning * into v;
  if v.id is null then
    return null;
  end if;
  insert into public.events (user_id, name, props) values (v.user_id, 'lifecycle_email_clicked',
    jsonb_build_object('email_id', v.id, 'kind', v.kind, 'search_profile_id', v.search_profile_id));
  return v.target;
end $$;

-- trial_ended, once per account when its 72 h trial is over, whatever happened:
-- the results and opportunities its searches got, the immediate alerts it was
-- sent and whether it paid before the end. Older trials get theirs on the
-- first run, with their real end in ended_at.
create function public.record_trial_ends() returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_count integer;
begin
  with ended as (
    select p.id, p.free_trial_started_at as started_at, p.free_trial_started_at + interval '72 hours' as ended_at
      from public.profiles p
     where p.role <> 'admin'
       and p.free_trial_started_at + interval '72 hours' <= now()
       and not exists (select 1 from public.events e where e.user_id = p.id and e.name = 'trial_ended')
     order by p.free_trial_started_at
     limit 500
  )
  insert into public.events (user_id, name, props)
  select e.id, 'trial_ended', jsonb_build_object(
           'ended_at', e.ended_at,
           'results', (select count(*) from public.matches m
                         join public.search_profiles sp on sp.id = m.search_profile_id
                        where sp.user_id = e.id and m.generated_at <= e.ended_at),
           'opportunities', (select count(*) from public.matches m
                               join public.search_profiles sp on sp.id = m.search_profile_id
                              where sp.user_id = e.id and m.generated_at <= e.ended_at and m.level = 'high'),
           'immediate_alerts_sent', (select count(distinct n.dedupe_key) from public.notifications n
                                      where n.user_id = e.id and n.kind <> 'digest' and n.status = 'sent'
                                        and n.created_at between e.started_at and e.ended_at),
           'converted', exists (select 1 from public.commercial_payments cp
                                 where cp.user_id = e.id and cp.refunded_at is null and cp.paid_at <= e.ended_at))
    from ended e;
  get diagnostics v_count = row_count;
  return v_count;
end $$;

revoke all on function public.lifecycle_contact_ok(uuid), public.trial_no_matches_eligible(uuid),
  public.trial_ended_eligible(uuid), public.lifecycle_email_eligible(bigint),
  public.claim_lifecycle_emails(text, interval, integer), public.track_lifecycle_click(bigint),
  public.record_trial_ends() from public, anon, authenticated;
grant execute on function public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer),
  public.track_lifecycle_click(bigint), public.record_trial_ends() to service_role;

notify pgrst, 'reload schema';
