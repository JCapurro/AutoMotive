-- Camino al pago con código (docs/PAGO_CON_CODIGO.md): an email-only account
-- that proved its inbox with the code may be completed without choosing a
-- password, on its way to Mercado Pago. complete_email_only_account is the one
-- from 20261029120000_email_only_accounts.sql with a third method, 'code', and
-- for that method only, in the same transaction, the mark that tells /login
-- not to ask for a password nobody chose: auth.users.raw_app_meta_data
-- .passwordless = true (the account keeps the random bcrypt hash GoTrue gave
-- it and an `email` identity, so nothing else can tell). The web clears the
-- mark when the person chooses a password (/auth/reset-password).
--
-- Compatible both ways: the old web never sends 'code', and the new web reads
-- 'invalid_method' from a database without this as "ask for the password".

create or replace function public.complete_email_only_account(p_user uuid, p_session uuid, p_method text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_method is null or p_method not in ('password', 'google', 'code') then
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
    if p_method = 'code' then
      -- No password chosen: /login sends the code (web/lib/email-only.ts hasPassword).
      update auth.users
         set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"passwordless": true}'::jsonb
       where id = p_user;
    end if;
    insert into public.events (user_id, name, props)
    values (p_user, 'account_completed', jsonb_build_object('method', p_method));
  end if;
  return true;
end;
$$;

-- create or replace keeps the grants; restated so this file stands on its own.
revoke all on function public.complete_email_only_account(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.complete_email_only_account(uuid, uuid, text) to service_role;
