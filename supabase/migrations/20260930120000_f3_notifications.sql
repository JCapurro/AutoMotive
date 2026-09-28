-- F3: notification engine (docs/TECHNICAL_PLAN.md, sección 7).
--
-- * notifications: one row per (decision, channel). The dedupe key is unique
--   per user *and channel*, so an alert sent by Telegram and email is two rows
--   that share it; the same listing still never alerts twice for the same
--   reason on a channel (§15).
-- * kind 'digest': the daily summary is itself a notification; the rows it
--   carries point to it through digested_in.
-- * track_notification_click(): what /r/<id> does (sección 7.3). The worker's
--   minimal endpoint calls it now and the Next.js route handler will in F4.
-- * notifications join the supabase_realtime publication (web inbox badge).

alter type public.notification_kind add value if not exists 'digest';

alter table public.notifications drop constraint notifications_user_id_dedupe_key_key;
alter table public.notifications
  add constraint notifications_user_channel_dedupe_key unique (user_id, channel, dedupe_key);

alter table public.notifications
  -- The profile whose match carries the alert (the one with the highest level).
  add column search_profile_id bigint references public.search_profiles (id) on delete set null,
  -- Delivery attempts; a transient failure stays queued until the limit.
  add column attempts          smallint not null default 0,
  -- The digest notification that delivered a row with status 'digest'.
  add column digested_in       bigint references public.notifications (id) on delete set null;

create index notifications_digest_pending_idx on public.notifications (user_id, channel)
  where status = 'digest' and digested_in is null;
create index notifications_digested_in_idx on public.notifications (digested_in)
  where digested_in is not null;

comment on column public.notifications.dedupe_key is
  'match:<listing_id> (new_match / opportunity), price_drop:<listing_id>:<snapshot_id>, '
  'listing_gone:<listing_id>, digest:<YYYY-MM-DD>. Unique per (user, channel).';

-- ---------------------------------------------------------------------------
-- Click tracking (sección 7.3)
-- ---------------------------------------------------------------------------

-- Records a click on a notification link and returns where to send the user:
-- the listing (and its URL at the source). "Opened" is the first click
-- (Telegram exposes no reads, §37). Every click is an alert_clicked event.
-- A digest carries many listings: p_listing_id picks one of its items, and
-- the row that item came from is marked clicked too. No rows = unknown id
-- (or a listing that isn't in that notification).
create function public.track_notification_click(
  p_notification_id bigint,
  p_to              text   default 'listing',
  p_listing_id      bigint default null
) returns table (listing_id bigint, url text)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_n       public.notifications;
  v_listing bigint;
begin
  select * into v_n from public.notifications where id = p_notification_id;
  if not found then
    return;
  end if;

  v_listing := coalesce(p_listing_id, v_n.listing_id);
  if v_listing is null then
    return;
  end if;
  if p_listing_id is not null and p_listing_id is distinct from v_n.listing_id
     and not exists (select 1 from jsonb_array_elements(coalesce(v_n.payload->'items', '[]')) as i
                      where (i->>'listing_id')::bigint = p_listing_id) then
    return;
  end if;

  update public.notifications
     set clicked_at = coalesce(clicked_at, now()),
         opened_at  = coalesce(opened_at, now())
   where id = v_n.id
      or (digested_in = v_n.id and notifications.listing_id = v_listing);

  insert into public.events (user_id, name, props)
  values (v_n.user_id, 'alert_clicked', jsonb_build_object(
    'notification_id', v_n.id, 'kind', v_n.kind, 'channel', v_n.channel,
    'listing_id', v_listing, 'to', coalesce(p_to, 'listing')));

  return query select l.id, l.url from public.listings l where l.id = v_listing;
end;
$$;

revoke execute on function public.track_notification_click(bigint, text, bigint)
  from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Web inbox: Realtime pushes new rows to the owner (RLS applies).
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.notifications;
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- app_config
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  -- Top matches of the day in the digest (plus every degraded alert).
  ('digest_top_n', '10')
on conflict (key) do nothing;
