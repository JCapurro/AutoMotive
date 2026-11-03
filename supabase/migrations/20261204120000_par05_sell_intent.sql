-- PAR-05 · Prueba B: «¿Tenés que vender tu auto actual para comprar?»
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PAR-05). Approved by Juan.
--
-- A small experiment before building «¿A cuánto publicarlo?»: ask the
-- question in the welcome email (search_activated) and as one line in the
-- listing page, and measure how many answer «Sí», ask to be told when the
-- reference of published prices exists, and (only once Juan approves the
-- Privacy line) tick «También me interesa que agencias me contacten». Nothing
-- is shared with anyone: this only stores the account's own answer.
--
-- * public.sell_intent: one row per account, its latest answer. RLS: each
--   account reads and writes only its own row (never an anonymous session);
--   the timestamps are set by a trigger, never by the client. The email
--   links (no session) write with the service role after checking the
--   link's signature (web/lib/sell-intent-server.ts).
-- * app_config.sell_intent: ask (the question is shown), agencies_contact
--   (the agencies checkbox and its Privacy line; OFF until Juan approves the
--   line) and since (when the experiment started, for the metrics; the time
--   this migration ran). An existing row is left alone.
-- * public.admin_sell_intent_metrics(p_since): the aggregate for /admin,
--   service role only, like admin_decision_metrics.
--
-- Applies on an empty base after the earlier migrations; the web of main does
-- not read any of it.

insert into public.app_config(key, value)
values ('sell_intent', jsonb_build_object('ask', true, 'agencies_contact', false, 'since', now()))
on conflict (key) do nothing;

create table public.sell_intent (
  user_id             uuid primary key references public.profiles(id) on delete cascade,
  answer              text not null check (answer in ('yes', 'no')),
  -- Where the latest answer came from: the welcome email's links or the listing page.
  source              text not null check (source in ('email', 'ficha')),
  answered_at         timestamptz not null default now(),
  wants_notice        boolean not null default false,
  wants_notice_at     timestamptz,
  agencies_contact_ok boolean not null default false,
  agencies_contact_at timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  -- The notice and the agencies preference only mean something after «Sí».
  constraint sell_intent_yes_only check (answer = 'yes' or (not wants_notice and not agencies_contact_ok))
);
create index sell_intent_answered_idx on public.sell_intent(answered_at);

-- Timestamps come from the database; agencies_contact_ok needs the flag on.
create function public.sell_intent_stamp()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_agencies boolean;
begin
  new.updated_at := now();
  if tg_op = 'INSERT' then
    new.created_at := now();
    new.answered_at := now();
  else
    new.created_at := old.created_at;
    new.answered_at := case when new.answer is distinct from old.answer or new.source is distinct from old.source
                            then now() else old.answered_at end;
  end if;
  new.wants_notice_at := case when not new.wants_notice then null
                              when tg_op = 'UPDATE' and old.wants_notice then old.wants_notice_at
                              else now() end;
  new.agencies_contact_at := case when not new.agencies_contact_ok then null
                                  when tg_op = 'UPDATE' and old.agencies_contact_ok then old.agencies_contact_at
                                  else now() end;
  if new.agencies_contact_ok and (tg_op = 'INSERT' or not old.agencies_contact_ok) then
    select (c.value->>'agencies_contact') = 'true' into v_agencies
      from public.app_config c where c.key = 'sell_intent' and jsonb_typeof(c.value) = 'object';
    if v_agencies is not true then
      raise exception 'sell_intent_agencies_off' using errcode = '42501';
    end if;
  end if;
  return new;
end $$;
revoke all on function public.sell_intent_stamp() from public, anon, authenticated;

create trigger sell_intent_stamp before insert or update on public.sell_intent
  for each row execute function public.sell_intent_stamp();

alter table public.sell_intent enable row level security;
revoke all on public.sell_intent from public, anon, authenticated;
grant select on public.sell_intent to authenticated;
grant insert (user_id, answer, source, wants_notice, agencies_contact_ok) on public.sell_intent to authenticated;
-- user_id too: PostgREST's upsert sets every column it sends; the policy keeps it the caller's own.
grant update (user_id, answer, source, wants_notice, agencies_contact_ok) on public.sell_intent to authenticated;
grant all on public.sell_intent to service_role;

create policy "sell_intent: own read" on public.sell_intent for select to authenticated
  using (user_id = (select auth.uid()));
create policy "sell_intent: own insert" on public.sell_intent for insert to authenticated
  with check (user_id = (select auth.uid())
              and coalesce(((select auth.jwt())->>'is_anonymous')::boolean, false) = false);
create policy "sell_intent: own update" on public.sell_intent for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid())
              and coalesce(((select auth.jwt())->>'is_anonymous')::boolean, false) = false);

-- The experiment's numbers for /admin. Admins are left out, as in every metric.
-- «Asked»: welcome emails sent since p_since (the question goes in every one
-- while app_config.sell_intent.ask is on) and accounts that opened a listing
-- page since then (the line shows to every account that hasn't answered: an
-- approximation, the page doesn't log each time it shows the line).
create function public.admin_sell_intent_metrics(p_since timestamptz default null)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare v_config timestamptz; v_since timestamptz; v_result jsonb;
begin
  begin
    select (c.value->>'since')::timestamptz into v_config from public.app_config c where c.key = 'sell_intent';
  exception when others then v_config := null;
  end;
  -- Without a usable start (no row, a bad value), every answer counts.
  v_since := coalesce(p_since, v_config, '-infinity'::timestamptz);

  with
  users as materialized (select p.id, p.created_at from public.profiles p where p.role <> 'admin'),
  answers as materialized (
    select s.* from public.sell_intent s join users u on u.id = s.user_id where s.answered_at >= v_since
  ),
  by_source as (
    select src.source, jsonb_build_object(
      'answered', count(a.user_id),
      'yes', count(a.user_id) filter (where a.answer = 'yes'),
      'no', count(a.user_id) filter (where a.answer = 'no'),
      'pctYes', round(100.0 * count(a.user_id) filter (where a.answer = 'yes') / nullif(count(a.user_id), 0), 1),
      'wantsNotice', count(a.user_id) filter (where a.wants_notice),
      'agenciesContactOk', count(a.user_id) filter (where a.agencies_contact_ok)
    ) as metrics
    from (values ('email'), ('ficha')) as src(source)
    left join answers a on a.source = src.source
    group by src.source
  )
  select jsonb_build_object(
    'since', case when isfinite(v_since) then v_since end,
    'newAccounts', (select count(*) from users u where u.created_at >= v_since),
    'askedByEmail', (select count(distinct l.user_id) from public.lifecycle_emails l join users u on u.id = l.user_id
                     where l.kind = 'search_activated' and l.status = 'sent' and l.sent_at >= v_since),
    'listingViewers', (select count(distinct e.user_id) from public.events e join users u on u.id = e.user_id
                       where e.name = 'listing_detail_viewed' and e.created_at >= v_since),
    'answered', (select count(*) from answers),
    'yes', (select count(*) from answers where answer = 'yes'),
    'no', (select count(*) from answers where answer = 'no'),
    'pctYes', (select round(100.0 * count(*) filter (where answer = 'yes') / nullif(count(*), 0), 1) from answers),
    'wantsNotice', (select count(*) from answers where wants_notice),
    'agenciesContactOk', (select count(*) from answers where agencies_contact_ok),
    'bySource', (select jsonb_object_agg(source, metrics) from by_source)
  ) into v_result;
  return v_result;
end $$;

revoke all on function public.admin_sell_intent_metrics(timestamptz) from public, anon, authenticated;
grant execute on function public.admin_sell_intent_metrics(timestamptz) to service_role;

notify pgrst, 'reload schema';
