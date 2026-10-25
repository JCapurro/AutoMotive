-- Remarketing a cuentas sin búsqueda (docs/MAILS_DE_PLAN.md, «Remarketing»).
--
-- Al 25/10/2026, 12 de 36 cuentas no tenían ninguna búsqueda: 9 habían
-- escrito qué auto buscaban en el modo asistido y no la activaron, 3 nunca
-- escribieron nada. Ninguna había recibido un email.
--
--   kind                  event key  due
--   search_abandoned      first      24 h after the account's last parse_search, still no search (1A)
--   search_not_started    first      24 h after signing up, no parse_search and no search (1B)
--   search_feedback       first      4 days after one of those two was sent, still no search and no answer
--
-- Los tres van a nombre de una persona (remarketing.sender_name), en texto
-- casi plano y con Reply-To (remarketing.reply_to). Debajo del botón van
-- links de motivo: /f/<id>?r=<motivo> abre una página que confirma el motivo
-- y deja escribir un comentario (record_email_feedback).
--
-- Nacen apagados en lifecycle_emails.kinds. remarketing.backfill_since deja
-- que, al prenderlos, las cuentas desde esa fecha reciban el suyo aunque su
-- evento sea más viejo que window_hours (una sola vez: la clave es 'first').
--
-- claim_lifecycle_emails y lifecycle_email_eligible se renombran a
-- *_welcome (las de 20261109130000) y las nuevas atienden estos tres tipos y
-- delegan el resto.

alter table public.lifecycle_emails drop constraint lifecycle_emails_kind_check;
alter table public.lifecycle_emails add constraint lifecycle_emails_kind_check
  check (kind in ('trial_no_matches', 'trial_ended', 'pass_expiring', 'pass_expires_today',
                  'count_after_expiry', 'search_activated',
                  'search_abandoned', 'search_not_started', 'search_feedback'));

alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_welcome;
alter function public.lifecycle_email_eligible(bigint) rename to lifecycle_email_eligible_welcome;

insert into public.app_config (key, value) values ('remarketing', '{
  "backfill_since": "2026-10-01T00:00:00-03:00", "sender_name": "Juan de Ese Auto", "reply_to": null}')
on conflict (key) do nothing;

update public.app_config
   set value = jsonb_set(value, '{kinds}', coalesce(value->'kinds', '{}')
         || '{"search_abandoned": false, "search_not_started": false, "search_feedback": false}')
 where key = 'lifecycle_emails';

-- ---------------------------------------------------------------------------
-- Feedback: one answer per email; a second one replaces it
-- ---------------------------------------------------------------------------

create table public.email_feedback (
  id                 bigint generated always as identity primary key,
  lifecycle_email_id bigint not null unique references public.lifecycle_emails(id) on delete cascade,
  user_id            uuid not null references public.profiles(id) on delete cascade,
  reason             text not null check (reason in ('browsing', 'missing_model', 'unclear', 'wrong_search',
                                                     'bought', 'other')),
  comment            text check (char_length(comment) <= 2000),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index email_feedback_user_idx on public.email_feedback (user_id);
comment on table public.email_feedback is
  'Why an account without searches did not start one: the reason links of the remarketing emails (/f/<id>).';

alter table public.email_feedback enable row level security;
revoke all on public.email_feedback from public, anon, authenticated, service_role;
grant select, insert, update on public.email_feedback to service_role;

-- The page /f/<id> calls it with the service role, once the link's signature
-- checked out. Only for a sent remarketing email; null otherwise. An event
-- email_feedback per answer (the first and every change).
create function public.record_email_feedback(p_email bigint, p_reason text, p_comment text)
returns bigint
language plpgsql security definer set search_path = '' as $$
declare
  v public.lifecycle_emails;
  v_id bigint;
  v_comment text := nullif(left(trim(coalesce(p_comment, '')), 2000), '');
begin
  select * into v from public.lifecycle_emails
   where id = p_email and status = 'sent'
     and kind in ('search_abandoned', 'search_not_started', 'search_feedback');
  if v.id is null then
    return null;
  end if;
  insert into public.email_feedback (lifecycle_email_id, user_id, reason, comment)
  values (v.id, v.user_id, p_reason, v_comment)
  on conflict (lifecycle_email_id) do update
    set reason = excluded.reason, comment = coalesce(excluded.comment, public.email_feedback.comment),
        updated_at = now()
  returning id into v_id;
  insert into public.events (user_id, name, props) values (v.user_id, 'email_feedback',
    jsonb_build_object('email_id', v.id, 'kind', v.kind, 'reason', p_reason, 'comment', v_comment is not null));
  return v_id;
end $$;

-- ---------------------------------------------------------------------------
-- Audiences
-- ---------------------------------------------------------------------------

-- Percent-encodes a query value (RFC 3986 unreserved characters stay).
create function public.url_encode(p text) returns text
language sql immutable set search_path = '' as $$
  select coalesce(string_agg(
           case when b between 48 and 57 or b between 65 and 90 or b between 97 and 122 or b in (45, 46, 95, 126)
                then chr(b) else '%' || upper(lpad(to_hex(b), 2, '0')) end, '' order by i), '')
    from (select i, get_byte(convert_to(coalesce(p, ''), 'UTF8'), i) as b
            from generate_series(0, octet_length(convert_to(coalesce(p, ''), 'UTF8')) - 1) i) s
$$;

-- Takes emails, never had a search (paused ones count: they are someone else's audience).
create function public.no_search_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.lifecycle_contact_ok(p_user)
     and not exists (select 1 from public.search_profiles sp where sp.user_id = p_user)
$$;

-- The second email: still no search, and no answer to the first one.
create function public.search_feedback_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.no_search_eligible(p_user)
     and not exists (select 1 from public.email_feedback f where f.user_id = p_user)
$$;

create function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select case when e.kind in ('search_abandoned', 'search_not_started') then public.no_search_eligible(e.user_id)
              when e.kind = 'search_feedback' then public.search_feedback_eligible(e.user_id)
              else public.lifecycle_email_eligible_welcome(p_id) end
    from public.lifecycle_emails e where e.id = p_id
$$;

-- ---------------------------------------------------------------------------
-- Claim
-- ---------------------------------------------------------------------------

create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  v_since timestamptz;
  v_from timestamptz;
begin
  if p_kind not in ('search_abandoned', 'search_not_started', 'search_feedback') then
    return query select * from public.claim_lifecycle_emails_welcome(p_kind, p_window, p_limit);
    return;
  end if;
  if p_window is null or coalesce(p_limit, 0) <= 0 then
    return;
  end if;
  begin
    v_since := (select (c.value->>'backfill_since')::timestamptz from public.app_config c where c.key = 'remarketing');
  exception when others then
    v_since := null;
  end;
  -- The oldest event still worth mailing: the window, or the backfill date if it is earlier.
  v_from := least(now() - p_window, coalesce(v_since, now() - p_window));

  if p_kind = 'search_abandoned' then
    return query
    with last_jobs as materialized (
      select distinct on (j.user_id) j.user_id, j.id as job_id, j.created_at, j.input->>'text' as asked,
             nullif(trim(concat_ws(' ', j.output->'drafts'->0->'values'->>'make',
                                        j.output->'drafts'->0->'values'->>'model')), '') as model
        from public.llm_jobs j
       where j.kind = 'parse_search' and j.status = 'done' and nullif(trim(j.input->>'text'), '') is not null
       order by j.user_id, j.created_at desc, j.id desc
    ), picked as (
      select l.*, l.created_at + interval '24 hours' as due_at
        from last_jobs l
       where l.created_at + interval '24 hours' <= now()
         and l.created_at + interval '24 hours' > v_from
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = l.user_id and e.kind = p_kind)
         and public.no_search_eligible(l.user_id)
       order by l.created_at, l.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, payload, target)
    select user_id, p_kind, 'first',
           jsonb_build_object('text', left(trim(asked), 300), 'model', model, 'asked_at', created_at, 'job_id', job_id),
           '/app/searches/new?prompt=' || public.url_encode(left(trim(asked), 300))
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  elsif p_kind = 'search_not_started' then
    return query
    with picked as (
      select p.id as user_id, p.created_at
        from public.profiles p
       where p.created_at + interval '24 hours' <= now()
         and p.created_at + interval '24 hours' > v_from
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = p.id and e.kind = p_kind)
         and not exists (select 1 from public.llm_jobs j where j.user_id = p.id and j.kind = 'parse_search')
         and public.no_search_eligible(p.id)
       order by p.created_at, p.id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, payload, target)
    select user_id, p_kind, 'first', '{}'::jsonb, '/app/searches/new'
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  else
    -- search_feedback: 4 days after the first email went out. Its window
    -- starts at that send, so the backfill does not apply.
    return query
    with firsts as materialized (
      select distinct on (e.user_id) e.user_id, e.kind as first_kind, e.payload, e.target, e.sent_at
        from public.lifecycle_emails e
       where e.kind in ('search_abandoned', 'search_not_started') and e.status = 'sent'
       order by e.user_id, e.sent_at
    ), picked as (
      select f.*
        from firsts f
       where f.sent_at + interval '4 days' <= now()
         and f.sent_at + interval '4 days' > now() - p_window
         and not exists (select 1 from public.lifecycle_emails e where e.user_id = f.user_id and e.kind = p_kind)
         and public.search_feedback_eligible(f.user_id)
       order by f.sent_at, f.user_id
       limit p_limit
    )
    insert into public.lifecycle_emails (user_id, kind, event_key, payload, target)
    select user_id, p_kind, 'first', jsonb_strip_nulls(jsonb_build_object('model', payload->>'model', 'after', first_kind)), target
      from picked
    on conflict (user_id, kind, event_key) do nothing
    returning *;
  end if;
end $$;

revoke all on function public.claim_lifecycle_emails_welcome(text, interval, integer),
  public.lifecycle_email_eligible_welcome(bigint), public.no_search_eligible(uuid),
  public.search_feedback_eligible(uuid), public.lifecycle_email_eligible(bigint),
  public.claim_lifecycle_emails(text, interval, integer), public.record_email_feedback(bigint, text, text)
  from public, anon, authenticated;
grant execute on function public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer),
  public.record_email_feedback(bigint, text, text) to service_role;

notify pgrst, 'reload schema';
