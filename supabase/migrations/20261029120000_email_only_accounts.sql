-- Free search with only an email (docs/AUTENTICACION.md). Juan asked for it on
-- 15/10/2026: the 72 h trial asks for an email and nothing else (no code, no
-- password, no confirmation). Paying still needs a real account: the email
-- proven through its inbox (or Google) and a password.
--
-- * profiles.email_only: the single source of truth. The server sets it right
--   after admin.createUser (mark_email_only_account) and clears it only after
--   an inbox proof (complete_email_only_account). Users can't write it: their
--   profiles UPDATE grant is per column.
-- * While email_only, GoTrue can't give the account a password or a new
--   email: whoever typed someone else's address gets a working session, but
--   must not leave a credential behind for when the owner shows up.
-- * Buying is refused in the database too (billing_checkouts).
-- * auth_throttle: the brakes on account creation and on every email the app
--   sends for these accounts (Resend's daily quota is shared with Auth).
-- * Every function here is service role only: anon and authenticated get
--   EXECUTE on new public functions by default, and with it a lite session
--   could promote itself and the anon key could enumerate emails.

-- ---------------------------------------------------------------------------
-- profiles.email_only
-- ---------------------------------------------------------------------------

alter table public.profiles add column email_only boolean not null default false;

-- Right after admin.createUser, before any session exists. Only a profile
-- born minutes ago with nothing in it: the call can never downgrade an
-- account someone already uses. False means "don't mint a session".
create function public.mark_email_only_account(p_user uuid) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.profiles p
     set email_only = true
   where p.id = p_user
     and p.created_at > now() - interval '10 minutes'
     and not exists (select 1 from public.search_profiles sp where sp.user_id = p.id)
     and not exists (select 1 from public.billing_checkouts bc where bc.user_id = p.id)
     and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id);
  return found;
end;
$$;

-- The account behind an email, in any case: none, email-only or a full one.
-- SSO and soft-deleted users don't own an address here.
create function public.auth_account_for_email(p_email text)
returns table (user_id uuid, email_only boolean, confirmed boolean)
language sql
stable
security definer
set search_path = ''
as $$
  select u.id, coalesce(p.email_only, false), u.email_confirmed_at is not null
    from auth.users u
    left join public.profiles p on p.id = u.id
   where lower(u.email) = lower(btrim(p_email))
     and not u.is_sso_user
     and u.deleted_at is null
$$;

-- ---------------------------------------------------------------------------
-- Throttle: attempts per (kind, key) inside a window
-- ---------------------------------------------------------------------------

-- kind: what is limited (signup_ip, signup_global, entry_link_user…); key: an
-- IP hash, a user id or 'global'. Rows older than the longest window go away
-- on the next claim, so there is no cron.
create table public.auth_throttle (
  id         bigint generated always as identity primary key,
  kind       text not null,
  key        text not null,
  created_at timestamptz not null default now()
);
create index auth_throttle_kind_key_idx on public.auth_throttle (kind, key, created_at);
alter table public.auth_throttle enable row level security;
revoke all on public.auth_throttle from anon, authenticated;
grant all on public.auth_throttle to service_role;

-- True and counted while below p_limit attempts in the last p_window_seconds;
-- false (and not counted) past it. The lock serializes count and insert per
-- bucket, so two requests can't both take the last slot.
create function public.claim_auth_throttle(p_kind text, p_key text, p_limit integer, p_window_seconds integer)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_count integer;
begin
  if p_kind is null or p_key is null or p_limit is null
     or p_window_seconds is null or p_window_seconds not between 1 and 172800 then
    raise exception 'invalid_throttle' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('auth_throttle:' || p_kind || ':' || p_key, 0));
  delete from public.auth_throttle where created_at < now() - interval '2 days';
  select count(*) into v_count
    from public.auth_throttle
   where kind = p_kind and key = p_key
     and created_at > now() - make_interval(secs => p_window_seconds);
  if v_count >= p_limit then
    return false;
  end if;
  insert into public.auth_throttle (kind, key) values (p_kind, p_key);
  return true;
end;
$$;

-- ---------------------------------------------------------------------------
-- Inbox proof and promotion to a full account
-- ---------------------------------------------------------------------------

-- One row per session that proved the inbox (recovery link, /auth/confirm) or
-- Google (callback), written by the web with the service role. The JWT's amr
-- can't tell: GoTrue issues 'otp' for every token_hash verify, including the
-- session the server mints for a typed email. session_id survives refreshes.
create table public.account_proofs (
  session_id uuid primary key,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  method     text not null check (method in ('email_link', 'google')),
  created_at timestamptz not null default now()
);
create index account_proofs_user_id_idx on public.account_proofs (user_id);
alter table public.account_proofs enable row level security;
revoke all on public.account_proofs from anon, authenticated;
grant all on public.account_proofs to service_role;

-- Before the web sets the password (p_method 'password') or right after a
-- Google proof ('google'). Needs a proof for this very session from the last
-- hour, and the session still alive: a revoked one may keep a valid access
-- token for up to an hour. Calling it again changes nothing.
create function public.complete_email_only_account(p_user uuid, p_session uuid, p_method text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_method is null or p_method not in ('password', 'google') then
    raise exception 'invalid_method' using errcode = '22023';
  end if;
  if not exists (select 1 from public.account_proofs ap
                  where ap.session_id = p_session and ap.user_id = p_user
                    and ap.created_at > now() - interval '1 hour')
     or not exists (select 1 from auth.sessions s
                     where s.id = p_session and s.user_id = p_user
                       and (s.not_after is null or s.not_after > now())) then
    raise exception 'proof_required' using errcode = '42501';
  end if;
  update public.profiles set email_only = false where id = p_user and email_only;
  if found then
    -- In the same transaction: no other session may be alive the moment the
    -- account can take a password (the web also signs them out first).
    delete from auth.sessions where user_id = p_user and id <> p_session;
    insert into public.events (user_id, name, props)
    values (p_user, 'account_completed', jsonb_build_object('method', p_method));
  end if;
  return true;
end;
$$;

-- At the first inbox or Google proof, before anything else: whoever typed the
-- address may have left footholds that a password reset doesn't touch. An
-- MFA factor enrolled from the lite session, and the Telegram link (alerts to
-- their chat; the code is readable by the account). Only email-only accounts.
create function public.secure_email_only_account(p_user uuid) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (select 1 from public.profiles where id = p_user and email_only) then
    return false;
  end if;
  delete from auth.mfa_factors where user_id = p_user;
  update public.profiles
     set telegram_chat_id = null, telegram_user_id = null, telegram_link_code = gen_random_uuid()
   where id = p_user;
  return true;
end;
$$;

revoke all on function public.mark_email_only_account(uuid), public.auth_account_for_email(text),
  public.claim_auth_throttle(text, text, integer, integer),
  public.complete_email_only_account(uuid, uuid, text), public.secure_email_only_account(uuid)
  from public, anon, authenticated;
grant execute on function public.mark_email_only_account(uuid), public.auth_account_for_email(text),
  public.claim_auth_throttle(text, text, integer, integer),
  public.complete_email_only_account(uuid, uuid, text), public.secure_email_only_account(uuid) to service_role;

-- ---------------------------------------------------------------------------
-- delete_my_account: only from a live session (20261004, otherwise unchanged)
-- ---------------------------------------------------------------------------

-- Revoking a session (signOut others, a new password) doesn't kill its access
-- token, which stays valid for up to an hour: once the owner proves the inbox,
-- the session of whoever typed their email must not be able to delete the
-- account. Tokens without session_id (service tooling, tests) keep working.
create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user    uuid := (select auth.uid());
  v_session uuid := nullif((select auth.jwt()) ->> 'session_id', '')::uuid;
  v_created timestamptz;
begin
  if v_user is null then
    raise exception 'not authenticated';
  end if;
  if v_session is not null and not exists (select 1 from auth.sessions s where s.id = v_session and s.user_id = v_user) then
    raise exception 'session_revoked' using errcode = '42501';
  end if;
  select created_at into v_created from public.profiles where id = v_user;
  insert into public.events (user_id, name, props)
  values (null, 'account_deleted', jsonb_build_object(
    'days_since_signup', floor(extract(epoch from now() - coalesce(v_created, now())) / 86400)::int,
    'searches', (select count(*) from public.search_profiles where user_id = v_user)));
  delete from auth.users where id = v_user;
end;
$$;

-- ---------------------------------------------------------------------------
-- No credentials while email_only
-- ---------------------------------------------------------------------------

-- A lite session can call GoTrue's updateUser directly (no reauthentication):
-- a password set there would survive the owner's later proof. GoTrue
-- sometimes writes every column, so only real changes count; clearing
-- email_change is fine. createUser and verifyOtp never get here with the flag
-- on: the profile is marked after createUser, and verifies touch none of these.
create function public.guard_email_only_credentials() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (new.encrypted_password is distinct from old.encrypted_password
      or new.email is distinct from old.email
      or (coalesce(new.email_change, '') <> '' and new.email_change is distinct from old.email_change))
     and exists (select 1 from public.profiles p where p.id = new.id and p.email_only) then
    raise exception 'account_required' using errcode = '42501';
  end if;
  return new;
end;
$$;
create trigger auth_users_guard_email_only
  before update of encrypted_password, email, email_change on auth.users
  for each row execute function public.guard_email_only_credentials();

-- startPayment refuses email-only accounts first; this is the backstop, also
-- for link_telegram moving checkouts to another account.
create function public.guard_billing_account() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (select 1 from public.profiles p where p.id = new.user_id and p.email_only) then
    raise exception 'account_required' using errcode = '42501';
  end if;
  return new;
end;
$$;
create trigger billing_checkouts_guard_account
  before insert or update of user_id on public.billing_checkouts
  for each row execute function public.guard_billing_account();

revoke execute on function public.guard_email_only_credentials(), public.guard_billing_account()
  from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- LLM: a lower hourly cap for email-only accounts (20261002, otherwise unchanged)
-- ---------------------------------------------------------------------------

-- A new email is cheap now, and each one used to bring its own 30 jobs an hour.
create or replace function public.enforce_llm_rate_limit() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_limits jsonb;
  v_max    integer;
  v_count  integer;
begin
  select value into v_limits from public.app_config where key = 'llm_limits';
  v_max := (v_limits ->> 'per_user_hour')::integer;
  if exists (select 1 from public.profiles where id = new.user_id and email_only) then
    v_max := coalesce((v_limits ->> 'email_only_per_user_hour')::integer, 5);
  end if;
  if v_max is null then
    return new;
  end if;

  select count(*) into v_count
    from public.llm_jobs
   where user_id = new.user_id and created_at > now() - interval '1 hour';
  if v_count >= v_max then
    raise exception 'llm_rate_limited'
      using errcode = 'P0001',
            detail  = format('%s LLM jobs in the last hour (max %s)', v_count, v_max);
  end if;
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- app_config (editable from /admin/config)
-- ---------------------------------------------------------------------------

-- enabled=false sends the landing back to the normal sign-up. per_ip_hour and
-- per_day cap new accounts; the links_* and lookups_* keys cap the emails and
-- the account lookups each IP or account can trigger.
insert into public.app_config (key, value) values
  ('email_only_signup', '{"enabled": true, "per_ip_hour": 10, "per_day": 100, "links_per_user_hour": 3,
                          "links_per_ip_hour": 20, "lookups_per_ip_hour": 30}')
on conflict (key) do nothing;

update public.app_config
   set value = value || '{"email_only_per_user_hour": 5}'
 where key = 'llm_limits' and jsonb_typeof(value) = 'object' and not value ? 'email_only_per_user_hour';

-- ---------------------------------------------------------------------------
-- admin_users: the "Solo email" pill (20261003, same columns plus email_only)
-- ---------------------------------------------------------------------------

-- CREATE OR REPLACE drops reloptions unless they are repeated; the revoke from
-- anon and authenticated (20261003) is kept.
create or replace view public.admin_users with (security_invoker = true) as
select p.id,
       p.email,
       p.plan,
       p.plan_expires_at,
       p.role,
       p.created_at,
       p.telegram_chat_id is not null                       as telegram_linked,
       p.email is null                                      as telegram_only,
       (select count(*) from public.search_profiles sp where sp.user_id = p.id)                  as searches,
       (select count(*) from public.search_profiles sp where sp.user_id = p.id and sp.enabled)   as enabled_searches,
       (select count(distinct n.dedupe_key) from public.notifications n
         where n.user_id = p.id and n.kind <> 'digest' and n.status = 'sent'
           and n.sent_at > now() - interval '7 days')       as alerts_7d,
       (select max(e.created_at) from public.events e
         where e.user_id = p.id and e.name <> 'alert_sent') as last_activity_at,
       w.plan                                               as waitlist_plan,
       p.email_only
  from public.profiles p
  left join public.pro_waitlist w on w.user_id = p.id;
revoke all on public.admin_users from anon, authenticated;

notify pgrst, 'reload schema';
