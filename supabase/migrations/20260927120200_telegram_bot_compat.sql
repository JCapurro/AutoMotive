-- Keeps the current Telegram bot working on Postgres during the transition (F0).
--
-- * profiles.telegram_user_id: the bot authorizes /borrar, /pausar… by Telegram user id,
--   and chat ids are not per-user in group chats.
-- * search_profiles.last_scraped_at: per-profile re-scrape cadence
--   (ALERT_RESCRAPE_INTERVAL_SECONDS). F1 moves cadence to crawl_targets and drops it.
-- * ensure_telegram_profile(): the wizard creates alerts for Telegram users who have no
--   web account yet. They get an anonymous auth user so profiles keeps its 1:1 with
--   auth.users; linking to an email account is part of F4.

alter table public.profiles add column telegram_user_id bigint unique;
alter table public.search_profiles add column last_scraped_at timestamptz;

comment on column public.search_profiles.last_scraped_at is
  'F0 only: legacy per-profile scrape cadence. Replaced by crawl_targets in F1.';

create function public.ensure_telegram_profile(p_telegram_user_id bigint, p_chat_id bigint)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  select id into v_id from public.profiles where telegram_user_id = p_telegram_user_id;
  if v_id is null then
    begin
      v_id := gen_random_uuid();
      insert into auth.users (instance_id, id, aud, role, raw_app_meta_data, raw_user_meta_data,
                              is_anonymous, created_at, updated_at)
      values ('00000000-0000-0000-0000-000000000000', v_id, 'authenticated', 'authenticated',
              '{"provider": "telegram", "providers": ["telegram"]}',
              jsonb_build_object('telegram_user_id', p_telegram_user_id),
              true, now(), now());
      -- handle_new_user() already created the profile row.
      update public.profiles set telegram_user_id = p_telegram_user_id where id = v_id;
    exception when unique_violation then
      -- A concurrent call won the race; its user is the one to keep.
      select id into v_id from public.profiles where telegram_user_id = p_telegram_user_id;
    end;
  end if;

  update public.profiles
     set telegram_chat_id = p_chat_id
   where id = v_id and telegram_chat_id is distinct from p_chat_id;
  return v_id;
end;
$$;

revoke execute on function public.ensure_telegram_profile(bigint, bigint) from public, anon, authenticated;
