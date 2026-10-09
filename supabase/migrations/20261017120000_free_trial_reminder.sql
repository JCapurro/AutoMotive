-- Free-trial reminder (docs/RECORDATORIO_PRUEBA.md): one email per account,
-- ever, to accounts whose 72 h free trial ended without buying a plan,
-- inviting them to pick Particular or Agencia. The worker
-- (worker/notifications/trial_reminder.py) claims due accounts into a ledger
-- and sends them through Resend inside the Argentine send hours.
--
--   trial ends ──(delay_hours)──> due ──(window_hours)──> too old, never sent
--                                  │
--                  claim_trial_reminders: trial_reminders row 'pending'
--                                  │
--                  worker sends ──> 'sent' | 'failed' | 'skipped'

-- ---------------------------------------------------------------------------
-- The send ledger
-- ---------------------------------------------------------------------------

-- One row per account, ever: the primary key is what makes it a single email.
-- Not a notifications row: guard_notification_access drops inserts for
-- expired users, prepare_notification_delivery and expire_commercial_access
-- skip them, and the alert metrics count every notification as an alert.
create table public.trial_reminders (
  user_id          uuid primary key references public.profiles(id) on delete cascade,
  trial_expires_at timestamptz not null,
  status           text not null default 'pending'
    check (status in ('pending', 'sent', 'failed', 'skipped')),
  attempts         smallint not null default 0,
  error            text,
  provider_id      text,
  created_at       timestamptz not null default now(),
  sent_at          timestamptz
);
-- The daily cap counts the rows claimed since the start of the Argentine day.
create index trial_reminders_created_at_idx on public.trial_reminders (created_at);
comment on table public.trial_reminders is
  'Send ledger of the free-trial reminder email (docs/RECORDATORIO_PRUEBA.md): one row per account, ever. '
  'Kept out of notifications because its guards drop rows of expired users and its metrics would count it as an alert.';

alter table public.trial_reminders enable row level security;
revoke all on public.trial_reminders from public, anon, authenticated, service_role;
grant select, insert, update on public.trial_reminders to service_role;

-- ---------------------------------------------------------------------------
-- Configuration (editable from /admin/config, which only edits existing keys)
-- ---------------------------------------------------------------------------

--   enabled       false stops claiming and sending
--   delay_hours   hours after the trial ends before the account is due
--   window_hours  a due account is still sendable this long; older ones are
--                 never sent (a rollout or re-enabling plan_limits.enforced
--                 must not mail long-expired trials). Must exceed the night gap.
--   send_from / send_until   send hours, Argentina (UTC-3), [from, until)
--   max_per_day   reminders claimed per Argentine calendar day (Resend's free
--                 tier is 100 emails a day, shared with the alerts)
insert into public.app_config (key, value) values ('trial_reminder',
  '{"enabled": true, "delay_hours": 0, "window_hours": 48, "send_from": "09:00", "send_until": "21:00", "max_per_day": 30}')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Audience
-- ---------------------------------------------------------------------------

-- The static part of the audience: an account that started the free trial,
-- whose trial ended, that never bought a plan, can buy one now and still
-- takes email. Checked when claiming and again just before sending.
create function public.trial_reminder_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select p.role <> 'admin'
       and p.email is not null
       and 'email' = any(p.default_channels)
       and p.plan = 'free'
       and p.free_trial_started_at is not null
       -- 'expired' implies plan_limits.enforced, the trial over and nothing paid now.
       and public.plan_limits_for(p.id)->>'state' = 'expired'
       -- Never bought: a refunded payment still counts as having bought.
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
      from public.profiles p
     where p.id = p_user), false)
$$;
revoke all on function public.trial_reminder_eligible(uuid) from public, anon, authenticated;
grant execute on function public.trial_reminder_eligible(uuid) to service_role;

-- Claims up to p_limit due accounts, oldest trial end first: inserts their
-- ledger rows ('pending') and returns them. An account already in the ledger
-- is never claimed again. The database clock decides what is due.
create function public.claim_trial_reminders(p_delay interval, p_window interval, p_limit integer)
returns setof public.trial_reminders
language plpgsql security definer set search_path = '' as $$
begin
  if p_delay is null or p_window is null or coalesce(p_limit, 0) <= 0 then
    return;
  end if;
  return query
  with candidates as materialized (
    -- Cheap scan first: free accounts whose trial (72 h, plan_limits_for)
    -- could have ended inside the window and that were never claimed.
    select p.id, (public.plan_limits_for(p.id)->>'trial_expires_at')::timestamptz as expires_at
      from public.profiles p
     where p.plan = 'free'
       and p.free_trial_started_at is not null
       and p.free_trial_started_at > now() - p_delay - p_window - interval '72 hours'
       and not exists (select 1 from public.trial_reminders r where r.user_id = p.id)
  ), due as materialized (
    select c.id, c.expires_at from candidates c
     where c.expires_at + p_delay <= now()
       and c.expires_at + p_delay > now() - p_window
  )
  insert into public.trial_reminders (user_id, trial_expires_at)
  select d.id, d.expires_at from due d
   where public.trial_reminder_eligible(d.id)
   order by d.expires_at, d.id
   limit greatest(p_limit, 0)
  on conflict (user_id) do nothing
  returning *;
end $$;
revoke all on function public.claim_trial_reminders(interval, interval, integer) from public, anon, authenticated;
grant execute on function public.claim_trial_reminders(interval, interval, integer) to service_role;
