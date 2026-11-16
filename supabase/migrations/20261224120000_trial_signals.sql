-- Señales de la prueba gratis (docs/AUTENTICACION.md, «Una prueba por
-- persona»). Juan, 16/11/2026: guardar con cada prueba nueva un ID de
-- dispositivo y el hash de la IP, y tratar como el mismo mail las formas que
-- llegan a la misma casilla (alias +, puntos de Gmail).
--
-- * email_canonical(): la forma única de un mail. Gmail ignora los puntos y lo
--   que va después de +; Outlook/Hotmail/Live, iCloud, Proton y Fastmail
--   ignoran lo que va después de +. El resto solo pasa a minúsculas: en un
--   dominio desconocido, `a+b@` puede ser otra casilla.
-- * auth_account_for_canonical_email(): la cuenta de OTRA forma del mismo mail.
--   Recorre auth.users (no se puede indexar ahí); con miles de usuarios son
--   milisegundos. Devuelve el mail guardado: el que lo escribió es dueño de la
--   misma casilla.
-- * trial_signals: una fila por cuenta nueva sin contraseña, con el mail
--   canónico, el hash de la IP (lib/email-only.ts clientIpKey, el mismo de
--   auth_throttle) y el hash del ID de dispositivo (cookie am_dev). Hoy solo se
--   guarda: medir antes de frenar (ops/abuso_prueba.sql).
-- * Todo es solo service role, como el resto de email_only_accounts.

create function public.email_canonical(p_email text) returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  with e as (
    select split_part(lower(btrim(p_email)), '@', 1) l, split_part(lower(btrim(p_email)), '@', 2) d
  ), n as (
    select l, case when d = 'googlemail.com' then 'gmail.com' else d end d from e
  )
  select case
           when p_email is null or position('@' in p_email) = 0 then lower(btrim(p_email))
           when d = 'gmail.com' then replace(split_part(l, '+', 1), '.', '') || '@' || d
           when d ~ '^(outlook|hotmail|live|msn|icloud|me|mac|protonmail|proton|pm|fastmail)\.'
             then split_part(l, '+', 1) || '@' || d
           else l || '@' || d
         end
    from n
$$;

-- The account behind another spelling of the same inbox (not the exact email:
-- auth_account_for_email answers that one). SSO and soft-deleted users own no
-- address here, like there.
create function public.auth_account_for_canonical_email(p_email text)
returns table (user_id uuid, email text, email_only boolean, confirmed boolean)
language sql
stable
security definer
set search_path = ''
as $$
  select u.id, lower(u.email), coalesce(p.email_only, false), u.email_confirmed_at is not null
    from auth.users u
    left join public.profiles p on p.id = u.id
   where public.email_canonical(u.email) = public.email_canonical(p_email)
     and lower(u.email) <> lower(btrim(p_email))
     and not u.is_sso_user
     and u.deleted_at is null
   order by u.created_at
   limit 1
$$;

create table public.trial_signals (
  user_id         uuid primary key references public.profiles (id) on delete cascade,
  email_canonical text not null,
  ip_key          text,
  device_key      text,
  created_at      timestamptz not null default now()
);
create index trial_signals_email_idx on public.trial_signals (email_canonical);
create index trial_signals_ip_idx on public.trial_signals (ip_key, created_at) where ip_key is not null;
create index trial_signals_device_idx on public.trial_signals (device_key, created_at) where device_key is not null;
alter table public.trial_signals enable row level security;
revoke all on public.trial_signals from anon, authenticated;
grant all on public.trial_signals to service_role;
comment on table public.trial_signals is
  'Una fila por cuenta nueva sin contraseña: mail canónico, hash de IP y de dispositivo. Solo service role (20261224120000_trial_signals).';

-- Right after the account is created. Keys that aren't 32-64 hex chars are
-- dropped ('unknown' IPs included): a junk value would match everyone.
create function public.record_trial_signals(p_user uuid, p_email text, p_ip_key text, p_device_key text)
returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.trial_signals (user_id, email_canonical, ip_key, device_key)
  select p_user, public.email_canonical(p_email),
         case when p_ip_key ~ '^[0-9a-f]{32,64}$' then p_ip_key end,
         case when p_device_key ~ '^[0-9a-f]{32,64}$' then p_device_key end
   where exists (select 1 from public.profiles where id = p_user)
  on conflict (user_id) do update
     set ip_key = coalesce(public.trial_signals.ip_key, excluded.ip_key),
         device_key = coalesce(public.trial_signals.device_key, excluded.device_key)
$$;

revoke all on function public.email_canonical(text) from public, anon, authenticated;
revoke all on function public.auth_account_for_canonical_email(text) from public, anon, authenticated;
revoke all on function public.record_trial_signals(uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.email_canonical(text) to service_role;
grant execute on function public.auth_account_for_canonical_email(text) to service_role;
grant execute on function public.record_trial_signals(uuid, text, text, text) to service_role;
