-- Alta con recarga (launch QA, 19/10/2026): a reload while the free search's
-- pop-up creates the account left the account created but this browser
-- without its session, and the retry sent the person to their inbox.
--
-- The browser now sends a random code with the signup (kept in its own
-- storage). The server stores the code's sha256 with the new account; a retry
-- for that email from the same browser, within 30 minutes and while the
-- account is still email-only, gets the session again. Typing the email alone
-- never does (docs/AUTENTICACION.md): only the browser that started it has
-- the code. Each code works once.

create table public.email_only_resume (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  code_hash  text not null check (length(code_hash) = 64),
  created_at timestamptz not null default now()
);
alter table public.email_only_resume enable row level security;
revoke all on public.email_only_resume from anon, authenticated;

-- A signup that went fine leaves its row (the browser just forgets the code);
-- each new one clears what is past any window.
create function public.save_email_only_resume(p_user uuid, p_code_hash text) returns void
language sql
security definer
set search_path = ''
as $$
  delete from public.email_only_resume where created_at < now() - interval '1 day';
  insert into public.email_only_resume (user_id, code_hash) values (p_user, p_code_hash)
  on conflict (user_id) do update set code_hash = excluded.code_hash, created_at = now();
$$;

-- True once, for the matching code inside the window, while the account is
-- still email-only (an inbox proof or a password ends it).
create function public.claim_email_only_resume(p_user uuid, p_code_hash text, p_window_seconds integer)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.email_only_resume r
   using public.profiles p
   where r.user_id = p_user
     and p.id = r.user_id
     and p.email_only
     and r.code_hash = p_code_hash
     and r.created_at > now() - make_interval(secs => p_window_seconds);
  return found;
end;
$$;

revoke all on function public.save_email_only_resume(uuid, text),
  public.claim_email_only_resume(uuid, text, integer) from public, anon, authenticated;
grant execute on function public.save_email_only_resume(uuid, text),
  public.claim_email_only_resume(uuid, text, integer) to service_role;
