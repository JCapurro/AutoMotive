-- F7 · Piloto (docs/TECHNICAL_PLAN.md, F7): what a public pilot needs from the
-- database.
--   punto 7: email unsubscribe (one link per user, no login) and account deletion;
--   punto 10: retention of listings nobody sees any more.

-- ---------------------------------------------------------------------------
-- Unsubscribe from email (punto 7)
-- ---------------------------------------------------------------------------

-- The secret in every email's unsubscribe link (/baja?t=<token>). Only the
-- worker (to build the link) and the owner (RLS on profiles) can read it.
alter table public.profiles
  add column email_unsubscribe_token uuid not null default gen_random_uuid();
create unique index profiles_email_unsubscribe_token_key on public.profiles (email_unsubscribe_token);

-- Takes email out of the user's default channels and of every search, like
-- turning it off in /app/settings. Idempotent: a second call (a mail scanner
-- following the one-click POST, the user clicking twice) changes nothing.
-- Returns the address it applied to, or null for an unknown token.
create function public.unsubscribe_email(p_token uuid)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user  uuid;
  v_email text;
  v_had   boolean;
begin
  select id, email, 'email' = any(default_channels)
         or exists (select 1 from public.search_profiles sp
                     where sp.user_id = p.id and 'email' = any(sp.channels))
    into v_user, v_email, v_had
    from public.profiles p
   where email_unsubscribe_token = p_token;
  if v_user is null then
    return null;
  end if;
  if v_had then
    update public.profiles set default_channels = array_remove(default_channels, 'email') where id = v_user;
    update public.search_profiles set channels = array_remove(channels, 'email') where user_id = v_user;
    insert into public.events (user_id, name, props) values (v_user, 'email_unsubscribed', '{}');
  end if;
  return v_email;
end;
$$;

revoke execute on function public.unsubscribe_email(uuid) from public;
grant execute on function public.unsubscribe_email(uuid) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- Account deletion (punto 7, Ley 25.326)
-- ---------------------------------------------------------------------------

-- Deletes the caller's auth user; profiles, searches, matches, interactions,
-- notifications, events, llm_jobs and the waitlist go with it (on delete
-- cascade). One anonymous event survives, so the admin can count deletions
-- without keeping who it was.
create function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user    uuid := (select auth.uid());
  v_created timestamptz;
begin
  if v_user is null then
    raise exception 'not authenticated';
  end if;
  select created_at into v_created from public.profiles where id = v_user;
  insert into public.events (user_id, name, props)
  values (null, 'account_deleted', jsonb_build_object(
    'days_since_signup', floor(extract(epoch from now() - coalesce(v_created, now())) / 86400)::int,
    'searches', (select count(*) from public.search_profiles where user_id = v_user)));
  delete from auth.users where id = v_user;
end;
$$;

revoke execute on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

-- ---------------------------------------------------------------------------
-- Retention (punto 10, sección 14)
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  ('retention', '{"listing_days": 180}')
on conflict (key) do nothing;

-- Deletes listings not seen for `listing_days` (gone, or simply no longer in
-- any source's results) that no user ever touched: no interaction, no
-- notification, no owned vehicle. Their snapshots and matches go with them
-- (on delete cascade); a newer repost pointing at one is set to null.
-- Returns how many listings were deleted. Worker only (nightly loop).
create function public.purge_stale_listings(p_days integer default null)
returns integer
language plpgsql
set search_path = ''
as $$
declare
  v_days integer := coalesce(
    p_days,
    (select (value ->> 'listing_days')::integer from public.app_config where key = 'retention'),
    180);
  v_deleted integer;
begin
  if v_days < 30 then
    raise exception 'retention below 30 days (%): refusing', v_days;
  end if;
  with doomed as (
    select l.id
      from public.listings l
     where l.last_seen_at < now() - make_interval(days => v_days)
       and not exists (select 1 from public.user_listing_interactions i where i.listing_id = l.id)
       and not exists (select 1 from public.notifications n where n.listing_id = l.id)
       and not exists (select 1 from public.owned_vehicles o where o.listing_id = l.id)
  ), gone as (
    delete from public.listings l using doomed d where l.id = d.id returning 1
  )
  select count(*) into v_deleted from gone;
  return v_deleted;
end;
$$;

revoke execute on function public.purge_stale_listings(integer) from public, anon, authenticated;
