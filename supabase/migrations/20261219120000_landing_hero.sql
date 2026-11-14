-- Landing hero «para tocar» (design/variants/landing/index.html, Juan 14/11).
--
-- The home gets almost all its visits on a phone, from Instagram's browser,
-- and asked them to type into an empty box. The new hero lets the search be
-- built by tapping (model, budget, zone) and shows what was flagged today
-- instead of a fixed example. It ships behind a switch and a 50/50 split so it
-- can be measured against the hero of today.
--
-- 1. app_config.landing_hero: the switch (off) and the share of anonymous
--    visitors who see the new hero while it is on.
-- 2. landing_feed(): what the new hero shows. Service role only: the web
--    reads it on the server and caches it; nothing new is exposed to anon.
-- 3. log_landing_event(): the three anonymous events the comparison needs
--    (seen, started, email pop-up), with a closed list of names and a cap.
--
-- Depends on: core schema (listings, matches, search_profiles, events,
-- app_config), 20261205120100_par04_guide_events (the pattern of 3).

insert into public.app_config (key, value)
values ('landing_hero', jsonb_build_object('enabled', false, 'share', 50, 'events_per_minute', 300))
on conflict (key) do nothing;

-- Listings first seen in the last 24 h with a «high» match: how many, the four
-- to show and the most searched models.
--   rows: one per model, newest first, only where the comparison is solid
--   enough to print on the home (8+ comparables, asking 8 to 30 % under their
--   median, a whole price, km and year known) and with no flag beyond the
--   routine «no dice» ones. Anything else counts in flagged_24h but is not shown.
--   models: by people who saved a search for it in the last 30 days; a model
--   needs 3 of them to be listed.
create function public.landing_feed()
returns jsonb
language sql stable security definer set search_path = '' as $$
  with flagged as (
    select distinct on (l.id)
           l.id, l.make, l.model, l.trim, l.year, l.mileage_km, l.price_usd, l.price_partial,
           l.source, l.location_text, l.first_seen_at, m.price_ref, m.red_flags
      from public.listings l
      join public.matches m on m.listing_id = l.id
     where l.first_seen_at > now() - interval '24 hours'
       and l.status = 'active'
       and m.level = 'high'
     order by l.id, m.score desc
  ), solid as (
    select distinct on (f.make, f.model) f.*
      from flagged f
     where f.make is not null and f.model is not null and f.year is not null
       and f.mileage_km is not null and f.price_usd is not null
       and f.price_partial is not true
       and jsonb_typeof(f.price_ref -> 'n') = 'number'
       and jsonb_typeof(f.price_ref -> 'median') = 'number'
       and jsonb_typeof(f.price_ref -> 'diff_pct') = 'number'
       and (f.price_ref ->> 'n')::numeric >= 8
       and (f.price_ref ->> 'median')::numeric > f.price_usd
       and (f.price_ref ->> 'diff_pct')::numeric between 8 and 30
       and not exists (
         select 1
           from jsonb_array_elements(case when jsonb_typeof(f.red_flags) = 'array' then f.red_flags else '[]'::jsonb end) flag
          where coalesce(flag ->> 'id', '') not in ('no_service', 'no_owners', 'short_description', 'no_timing_belt')
       )
     order by f.make, f.model, f.first_seen_at desc
  ), shown as (
    select * from solid order by first_seen_at desc limit 4
  ), models as (
    select sp.filters ->> 'make' as make, sp.filters ->> 'model' as model, count(distinct sp.user_id) as people
      from public.search_profiles sp
     where sp.created_at > now() - interval '30 days'
       and coalesce(sp.filters ->> 'make', '') <> ''
       and coalesce(sp.filters ->> 'model', '') <> ''
     group by 1, 2
    having count(distinct sp.user_id) >= 3
     order by people desc, 1, 2
     limit 10
  )
  select jsonb_build_object(
    'flagged_24h', (select count(*) from flagged),
    'rows', coalesce((
      select jsonb_agg(jsonb_build_object(
               'make', s.make, 'model', s.model, 'trim', s.trim, 'year', s.year,
               'km', s.mileage_km, 'usd', round(s.price_usd),
               'median', round((s.price_ref ->> 'median')::numeric),
               'n', (s.price_ref ->> 'n')::numeric,
               'where', s.location_text, 'source', s.source, 'seen_at', s.first_seen_at
             ) order by s.first_seen_at desc)
        from shown s), '[]'::jsonb),
    'models', coalesce((
      select jsonb_agg(jsonb_build_object('make', mo.make, 'model', mo.model) order by mo.people desc, mo.make, mo.model)
        from models mo), '[]'::jsonb)
  );
$$;

comment on function public.landing_feed() is
  'Landing hero: listings flagged «high» in the last 24 h (count and up to four solid ones) and the most searched models. Service role only; the web caches it.';

revoke all on function public.landing_feed() from public, anon, authenticated;
grant execute on function public.landing_feed() to service_role;

-- The home's anonymous events, sent from the browser (signed in or not).
--   landing_viewed: the hero was shown (JavaScript ran: crawlers without it don't count).
--   landing_search_started: the first tap on a chip or the first text typed.
--   landing_dialog_opened: «Crear mi búsqueda» opened the email pop-up.
-- p_variant: 'a' the hero of today, 'b' the new one. p_how: what started the
-- search. No IP, user agent or referrer is stored. Past the cap
-- (app_config.landing_hero.events_per_minute, all three names together)
-- nothing is written.
create function public.log_landing_event(p_name text, p_variant text, p_how text default null)
returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_cap integer;
begin
  if p_name is null or p_name not in ('landing_viewed', 'landing_search_started', 'landing_dialog_opened') then
    raise exception 'invalid_landing_event' using errcode = '22023';
  end if;
  if p_variant is null or p_variant not in ('a', 'b') then
    raise exception 'invalid_landing_variant' using errcode = '22023';
  end if;
  if p_how is not null and p_how not in ('model', 'other', 'typed', 'row', 'budget', 'zone', 'here') then
    raise exception 'invalid_landing_how' using errcode = '22023';
  end if;

  select coalesce((value ->> 'events_per_minute')::integer, 300) into v_cap
    from public.app_config where key = 'landing_hero';
  v_cap := coalesce(v_cap, 300);

  perform pg_advisory_xact_lock(hashtext('public.log_landing_event'));
  if (select count(*) from public.events e
       where e.name in ('landing_viewed', 'landing_search_started', 'landing_dialog_opened')
         and e.created_at > now() - interval '1 minute') >= v_cap then
    return;
  end if;

  insert into public.events (user_id, name, props)
  values ((select auth.uid()), p_name,
          jsonb_strip_nulls(jsonb_build_object('variant', p_variant, 'how', p_how)));
end;
$$;

comment on function public.log_landing_event(text, text, text) is
  'Landing hero: the home''s anonymous events (closed list of names, variant a/b, capped per minute by app_config.landing_hero.events_per_minute).';

revoke all on function public.log_landing_event(text, text, text) from public;
grant execute on function public.log_landing_event(text, text, text) to anon, authenticated, service_role;

notify pgrst, 'reload schema';
