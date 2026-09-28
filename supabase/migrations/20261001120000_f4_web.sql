-- F4: web MVP (docs/TECHNICAL_PLAN.md, sección 9).
--
-- * profiles: default frequency and channels for new searches (/app/settings).
-- * matches.seller_questions: the §25 message the worker composes; the web
--   only copies it.
-- * match_cards: one row per match with its listing and the user's
--   interaction, what every list in the web draws. security_invoker, so RLS
--   decides what each user sees (own matches, any listing).
-- * dashboard_summary(), recent_opportunities(), search_results(),
--   search_result_counts(): the dashboard (§28) and results (§29) reads.
-- * preview_search(): "N publicaciones actuales coinciden" while a search is
--   being written. An approximation of the hard filters in SQL; the worker's
--   rematch (sección 5.7) is what stores the backfill.
-- * record_purchase(): "Compré este vehículo" (§38–39) in one transaction.
-- * link_telegram() / unlink_telegram(): /start <code> from the bot. A
--   Telegram-only account from the old wizard folds into the web account.

-- ---------------------------------------------------------------------------
-- profiles and matches
-- ---------------------------------------------------------------------------

alter table public.profiles
  add column default_notification_frequency public.notify_frequency not null default 'immediate',
  add column default_channels text[] not null default '{telegram,web}'
    check (default_channels <@ array['telegram', 'email', 'web']::text[]);

grant update (default_notification_frequency, default_channels) on public.profiles to authenticated;

alter table public.matches add column seller_questions text;
comment on column public.matches.seller_questions is
  '§25 / sección 6.6: deterministic questions for the seller, ready to copy. Never sent by Automotive.';

-- ---------------------------------------------------------------------------
-- match_cards
-- ---------------------------------------------------------------------------

create view public.match_cards with (security_invoker = true) as
select m.id                              as match_id,
       m.search_profile_id,
       sp.name                           as profile_name,
       sp.user_id,
       m.listing_id,
       m.score,
       m.level,
       m.is_backfill,
       m.generated_at,
       m.price_ref,
       m.red_flags,
       l.title,
       l.make,
       l.model,
       l.trim,
       l.year,
       l.price,
       l.currency,
       l.price_usd,
       l.mileage_km,
       l.transmission,
       l.fuel,
       l.location_text,
       l.source,
       l.images,
       l.published_at,
       l.first_seen_at,
       l.status                          as listing_status,
       l.probable_repost_of,
       coalesce(i.status, 'new')         as status,
       coalesce(i.saved, false)          as saved,
       i.rejection_reason
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

revoke all on public.match_cards from anon;
grant select on public.match_cards to authenticated;

-- ---------------------------------------------------------------------------
-- Dashboard (§28)
-- ---------------------------------------------------------------------------

-- One row per search: "14 nuevos esta semana · 2 oportunidades". Discarded
-- listings don't count; `unseen` are the ones the user hasn't opened.
create function public.dashboard_summary()
returns table (
  profile_id              bigint,
  name                    text,
  enabled                 boolean,
  filters                 jsonb,
  notification_frequency  public.notify_frequency,
  pending                 boolean,
  new_this_week           integer,
  opportunities_this_week integer,
  total                   integer,
  unseen                  integer
)
language sql
stable
security invoker
set search_path = ''
as $$
  select sp.id, sp.name, sp.enabled, sp.filters, sp.notification_frequency,
         sp.bootstrapped_at is null or sp.rematch_requested_at is not null,
         (count(*) filter (where c.status <> 'discarded' and c.generated_at >= now() - interval '7 days'))::integer,
         (count(*) filter (where c.status <> 'discarded' and c.generated_at >= now() - interval '7 days'
                             and c.level = 'high'))::integer,
         (count(*) filter (where c.status <> 'discarded'))::integer,
         (count(*) filter (where c.status = 'new'))::integer
    from public.search_profiles sp
    left join public.match_cards c on c.search_profile_id = sp.id
   where sp.user_id = (select auth.uid())
   group by sp.id
   order by sp.enabled desc, sp.created_at desc
$$;

-- "Oportunidades recientes": the user's best match per listing (🔥 and 🟢)
-- of the last 14 days on enabled searches, by score and then detection date.
create function public.recent_opportunities(p_limit integer default 10)
returns setof public.match_cards
language sql
stable
security invoker
set search_path = ''
as $$
  select * from (
    select distinct on (c.listing_id) c.*
      from public.match_cards c
      join public.search_profiles sp on sp.id = c.search_profile_id
     where c.user_id = (select auth.uid())
       and sp.enabled
       and c.level in ('high', 'good')
       and c.status <> 'discarded'
       and c.listing_status = 'active'
       and c.generated_at >= now() - interval '14 days'
     order by c.listing_id, c.score desc
  ) best
  order by best.score desc, best.first_seen_at desc
  limit greatest(p_limit, 0)
$$;

-- ---------------------------------------------------------------------------
-- Search results (§29)
-- ---------------------------------------------------------------------------

-- p_filter: new | opportunities | all | saved | discarded ("all" hides the
-- discarded ones). p_sort: recent (detection date) | score | price (USD) | km.
create function public.search_results(
  p_profile_id bigint,
  p_filter     text    default 'all',
  p_sort       text    default 'recent',
  p_limit      integer default 50,
  p_offset     integer default 0
) returns setof public.match_cards
language sql
stable
security invoker
set search_path = ''
as $$
  select c.* from public.match_cards c
   where c.search_profile_id = p_profile_id
     and case p_filter
           when 'new'           then c.status = 'new'
           when 'opportunities' then c.level = 'high' and c.status <> 'discarded'
           when 'saved'         then c.saved
           when 'discarded'     then c.status = 'discarded'
           else c.status <> 'discarded'
         end
   order by case when p_sort = 'score' then c.score end desc nulls last,
            case when p_sort = 'price' then c.price_usd end asc nulls last,
            case when p_sort = 'km' then c.mileage_km end asc nulls last,
            c.first_seen_at desc, c.listing_id desc
   limit greatest(p_limit, 0) offset greatest(p_offset, 0)
$$;

create function public.search_result_counts(p_profile_id bigint)
returns table (new_count integer, opportunities_count integer, all_count integer,
               saved_count integer, discarded_count integer)
language sql
stable
security invoker
set search_path = ''
as $$
  select (count(*) filter (where c.status = 'new'))::integer,
         (count(*) filter (where c.level = 'high' and c.status <> 'discarded'))::integer,
         (count(*) filter (where c.status <> 'discarded'))::integer,
         (count(*) filter (where c.saved))::integer,
         (count(*) filter (where c.status = 'discarded'))::integer
    from public.match_cards c
   where c.search_profile_id = p_profile_id
$$;

-- ---------------------------------------------------------------------------
-- Preview of a search being written (sección 9, /app/searches/new)
-- ---------------------------------------------------------------------------

create function public.haversine_km(lat1 double precision, lon1 double precision,
                                    lat2 double precision, lon2 double precision)
returns double precision
language sql
immutable
parallel safe
set search_path = ''
as $$
  select 2 * 6371 * asin(sqrt(
    power(sin(radians(lat2 - lat1) / 2), 2)
    + cos(radians(lat1)) * cos(radians(lat2)) * power(sin(radians(lon2 - lon1) / 2), 2)))
$$;

-- Active listings of the last 30 days (the backfill window) that pass the
-- hard filters of `p_filters` (sección 4.3 shape). As in matching.py a value
-- the listing doesn't inform never discards it, prices are compared after
-- converting currencies (price_usd, or the latest quote) and partial prices
-- are left out. Returns {"count": n, "sample": [up to 3 listings, newest first]}.
-- security definer only to read the latest fx rate; it returns nothing a
-- signed-in user can't already read from listings.
create function public.preview_search(
  p_filters    jsonb,
  p_origin_lat double precision default null,
  p_origin_lon double precision default null,
  p_radius_km  double precision default null
) returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with f as (
    select nullif(p_filters->>'make', '')                  as make,
           nullif(p_filters->>'model', '')                 as model,
           (p_filters->>'year_min')::integer               as year_min,
           (p_filters->>'year_max')::integer               as year_max,
           (p_filters->>'price_min')::numeric              as price_min,
           (p_filters->>'price_max')::numeric              as price_max,
           upper(coalesce(nullif(p_filters->>'currency', ''),
                          case when coalesce((p_filters->>'price_max')::numeric,
                                             (p_filters->>'price_min')::numeric, 0) >= 1000000
                               then 'ARS' else 'USD' end)) as currency,
           (p_filters->>'km_min')::integer                 as km_min,
           (p_filters->>'km_max')::integer                 as km_max,
           nullif(p_filters->>'transmission', '')          as transmission,
           nullif(p_filters->>'fuel', '')                  as fuel,
           case when jsonb_typeof(p_filters->'sources') = 'array'
                     and jsonb_array_length(p_filters->'sources') > 0
                then array(select jsonb_array_elements_text(p_filters->'sources')) end as sources,
           case when coalesce((p_filters->>'trim_strict')::boolean, false)
                     and jsonb_typeof(p_filters->'trims') = 'array'
                     and jsonb_array_length(p_filters->'trims') > 0
                then array(select lower(jsonb_array_elements_text(p_filters->'trims'))) end as strict_trims
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  priced as (
    select l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from public.listings l
     cross join f
      left join fx on true
     where f.make is not null
       and l.status = 'active'
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
       and lower(l.make) = lower(f.make)
       and (f.model is null or lower(l.model) = lower(f.model))
  ),
  hits as (
    select p.*
      from priced p
     cross join f
     where (p.year is null or f.year_min is null or p.year >= f.year_min)
       and (p.year is null or f.year_max is null or p.year <= f.year_max)
       and (p.mileage_km is null or f.km_min is null or p.mileage_km >= f.km_min)
       and (p.mileage_km is null or f.km_max is null or p.mileage_km <= f.km_max)
       and (p.price_in_filter is null or f.price_min is null or p.price_in_filter >= f.price_min)
       and (p.price_in_filter is null or f.price_max is null or p.price_in_filter <= f.price_max)
       and (f.transmission is null or p.transmission is null or p.transmission = f.transmission)
       and (f.fuel is null or p.fuel is null or position(lower(f.fuel) in lower(p.fuel)) > 0)
       and (f.sources is null or p.source = any (f.sources))
       and (f.strict_trims is null or p.trim is null
            or exists (select 1 from unnest(f.strict_trims) t where position(t in lower(p.trim)) > 0))
       and (p_radius_km is null or p_origin_lat is null or p_origin_lon is null
            or p.lat is null or p.lon is null
            or public.haversine_km(p_origin_lat, p_origin_lon, p.lat, p.lon) <= p_radius_km)
  ),
  sample as (
    select h.id, h.title, h.make, h.model, h.trim, h.year, h.price, h.currency, h.mileage_km,
           h.location_text, h.source, h.first_seen_at
      from hits h
     order by h.first_seen_at desc
     limit 3
  )
  select jsonb_build_object(
           'count',  (select count(*) from hits),
           'sample', coalesce((select jsonb_agg(to_jsonb(s) order by s.first_seen_at desc) from sample s),
                              '[]'::jsonb))
$$;

revoke execute on function public.preview_search(jsonb, double precision, double precision, double precision)
  from public, anon;
grant execute on function public.preview_search(jsonb, double precision, double precision, double precision)
  to authenticated;

-- ---------------------------------------------------------------------------
-- "Compré este vehículo" (§38, §39)
-- ---------------------------------------------------------------------------

-- Stores the OwnedVehicle with a snapshot of the listing (it survives the
-- listing), marks the listing 'purchased' and records vehicle_purchased with
-- the time using Automotive. Buying the same listing again updates the row.
-- security invoker: RLS applies, so it only ever writes the caller's rows.
create function public.record_purchase(
  p_listing_id        bigint,
  p_search_profile_id bigint  default null,
  p_price             numeric default null,
  p_currency          text    default null,
  p_date              date    default null
) returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user     uuid := auth.uid();
  v_listing  public.listings;
  v_profile  bigint;
  v_id       bigint;
  v_date     date := coalesce(p_date, (now() at time zone 'America/Argentina/Buenos_Aires')::date);
  v_vehicle  jsonb;
  v_signup   timestamptz;
  v_search   timestamptz;
begin
  if v_user is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  select * into v_listing from public.listings where id = p_listing_id;
  if not found then
    raise exception 'listing % not found', p_listing_id using errcode = 'P0002';
  end if;
  -- Another user's search (invisible through RLS) is dropped, not trusted.
  select id, created_at into v_profile, v_search
    from public.search_profiles where id = p_search_profile_id;

  v_vehicle := jsonb_build_object(
    'title', v_listing.title, 'make', v_listing.make, 'model', v_listing.model,
    'trim', v_listing.trim, 'year', v_listing.year, 'mileage_km', v_listing.mileage_km,
    'transmission', v_listing.transmission, 'fuel', v_listing.fuel,
    'price', v_listing.price, 'currency', v_listing.currency, 'price_usd', v_listing.price_usd,
    'source', v_listing.source, 'url', v_listing.url, 'location_text', v_listing.location_text,
    'image', v_listing.images->0);

  select id into v_id from public.owned_vehicles
   where user_id = v_user and listing_id = p_listing_id
   order by id limit 1;
  if v_id is null then
    insert into public.owned_vehicles (user_id, listing_id, search_profile_id, vehicle,
                                       purchase_price, purchase_currency, purchase_date)
    values (v_user, p_listing_id, v_profile, v_vehicle, p_price, p_currency, v_date)
    returning id into v_id;
  else
    update public.owned_vehicles
       set search_profile_id = coalesce(v_profile, search_profile_id), vehicle = v_vehicle,
           purchase_price = p_price, purchase_currency = p_currency, purchase_date = v_date
     where id = v_id;
  end if;

  insert into public.user_listing_interactions (user_id, listing_id, status)
  values (v_user, p_listing_id, 'purchased')
  on conflict (user_id, listing_id)
    do update set status = 'purchased', rejection_reason = null;

  select created_at into v_signup from public.profiles where id = v_user;
  insert into public.events (user_id, name, props) values
    (v_user, 'listing_status_changed',
     jsonb_build_object('listing_id', p_listing_id, 'status', 'purchased', 'via', 'web')),
    (v_user, 'vehicle_purchased', jsonb_build_object(
       'listing_id', p_listing_id, 'search_profile_id', v_profile, 'owned_vehicle_id', v_id,
       'price', p_price, 'currency', p_currency, 'date', v_date,
       'days_using_automotive', floor(extract(epoch from now() - v_signup) / 86400),
       'days_since_search_created',
         case when v_search is not null then floor(extract(epoch from now() - v_search) / 86400) end));
  return v_id;
end;
$$;

revoke execute on function public.record_purchase(bigint, bigint, numeric, text, date) from public, anon;
grant execute on function public.record_purchase(bigint, bigint, numeric, text, date) to authenticated;

-- ---------------------------------------------------------------------------
-- Telegram linking (sección 9: /start <telegram_link_code>)
-- ---------------------------------------------------------------------------

-- Called by the bot with the code of the deep link. Links the Telegram user
-- and chat to the web account and rotates the code. If that Telegram user
-- already had an account:
--   * a Telegram-only one (anonymous, created by the old wizard) folds in:
--     its searches, interactions, purchases, alerts and events move to the
--     web account, which keeps its own rows when both have one;
--   * another web account just loses the link.
-- Returns the web account's id, or null for an unknown or used code.
create function public.link_telegram(p_code text, p_telegram_user_id bigint, p_chat_id bigint)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_target uuid;
  v_prev   uuid;
  v_anon   boolean := false;
  v_moved  integer := 0;
begin
  select id into v_target from public.profiles
   where telegram_link_code = p_code for update;
  if v_target is null then
    return null;
  end if;

  select p.id, coalesce(u.is_anonymous, false) into v_prev, v_anon
    from public.profiles p
    join auth.users u on u.id = p.id
   where p.telegram_user_id = p_telegram_user_id and p.id <> v_target;

  if v_prev is not null and v_anon then
    update public.search_profiles set user_id = v_target where user_id = v_prev;
    get diagnostics v_moved = row_count;
    insert into public.user_listing_interactions (user_id, listing_id, status, saved, rejection_reason, note)
    select v_target, listing_id, status, saved, rejection_reason, note
      from public.user_listing_interactions where user_id = v_prev
    on conflict (user_id, listing_id) do nothing;
    update public.owned_vehicles set user_id = v_target where user_id = v_prev;
    update public.notifications n set user_id = v_target
     where n.user_id = v_prev
       and not exists (select 1 from public.notifications t
                        where t.user_id = v_target and t.channel = n.channel
                          and t.dedupe_key = n.dedupe_key);
    update public.events set user_id = v_target where user_id = v_prev;
    update public.llm_jobs set user_id = v_target where user_id = v_prev;
    -- Whatever didn't move (duplicates) goes with the anonymous user.
    delete from auth.users where id = v_prev;
  elsif v_prev is not null then
    update public.profiles set telegram_user_id = null, telegram_chat_id = null where id = v_prev;
  end if;

  update public.profiles
     set telegram_user_id   = p_telegram_user_id,
         telegram_chat_id   = p_chat_id,
         telegram_link_code = replace(gen_random_uuid()::text, '-', '')
   where id = v_target;

  insert into public.events (user_id, name, props)
  values (v_target, 'telegram_linked',
          jsonb_build_object('merged_telegram_account', v_prev is not null and v_anon,
                             'moved_search_profiles', v_moved));
  return v_target;
end;
$$;

revoke execute on function public.link_telegram(text, bigint, bigint) from public, anon, authenticated;

-- The web's "Desvincular": drops the link and rotates the code, so an old
-- deep link can't re-link the account.
create function public.unlink_telegram()
returns void
language sql
security definer
set search_path = ''
as $$
  update public.profiles
     set telegram_user_id = null, telegram_chat_id = null,
         telegram_link_code = replace(gen_random_uuid()::text, '-', '')
   where id = (select auth.uid());
$$;

revoke execute on function public.unlink_telegram() from public, anon;
grant execute on function public.unlink_telegram() to authenticated;
