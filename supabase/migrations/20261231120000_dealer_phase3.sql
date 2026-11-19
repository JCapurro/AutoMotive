-- Agencias, fase 3: «Qué comprar» y vendedores que aceptan contacto de agencias
-- (docs/PLAN_AGENCIAS_STOCK_Y_CANAL.md §5, fase 3; builds on 20261228120000_dealer_program.sql,
-- which it does not change). Cobro: only a proposal (docs/AGENCIAS_COBRO_PROPUESTA.md); nothing
-- here reads or writes plans, prices, plan_limits, plan_feature() or Mercado Pago.
--
-- No FK to listings and no new column on an existing table: it can be applied with the
-- worker running. Aplicar a mano según la memoria de migraciones de producción, con OK de
-- Juan, después de 20261228120000. Nada de esto se aplica en esta rama.
--
-- What it adds (all of it off by default):
-- * dealer_sellers_config(): new keys of app_config.dealer_program, sanitized:
--   sellers_enabled (boolean, default false; effective only with enabled) and
--   seller_requests_per_day (integer 1..50, default 5). The existing keys and
--   dealer_program() are untouched, so its twins (web, worker) don't change.
-- * dealer_buy_opportunities(): «Qué comprar» for an approved dealer. The models people
--   look for in the dealer's zone (each search's radius around the dealer's location; a
--   search without a zone counts, as in dealer_demand) and the dealer doesn't have in
--   stock, by demand. Saved searches active or created in the last 90 days, never admins
--   or the dealer's members, never «solo particulares» (they won't buy from a dealer).
--   A model shows only with demand_min_count (>= 3) distinct people behind it; the year
--   range and the budget only when that many people gave them; budgets rounded. No date,
--   no place, no person: only aggregates.
-- * dealer_buy_market_listings(): the public listings behind a row's supply count.
-- * sell_intent_vehicles: the car a seller («Sí» in sell_intent) says they sell. Today
--   nothing asks for it (the form is a follow-up that needs Juan's OK on its text); the
--   seller writes it with save_my_sell_vehicle().
-- * dealer_seller_requests: an approved dealer asks to contact a seller who ticked
--   «También me interesa que agencias me contacten para comprarlo». That consent does not
--   name an agency nor what data it gets, so the request never hands over any contact: it
--   stays «pending» until the seller answers (answer_dealer_seller_request, with its own
--   consent text naming the agency). Capped per dealer and day, and per seller and week.
--   No client reads the table: only the RPCs below.
--
-- Rollback: drop the functions of this file, `drop table public.dealer_seller_requests,
-- public.sell_intent_vehicles`; the keys sellers_enabled / seller_requests_per_day in
-- app_config.dealer_program are harmless (nothing else reads them).

set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 1. Switch
-- ---------------------------------------------------------------------------

-- The sellers part of app_config.dealer_program, sanitized. «sellers» is the
-- effective switch: enabled and sellers_enabled. per_seller_week is fixed (it
-- protects the seller, it's not a knob).
create function public.dealer_sellers_config() returns jsonb
language sql stable security definer set search_path = '' as $$
  with raw as (
    select coalesce((select c.value from public.app_config c
                      where c.key = 'dealer_program' and jsonb_typeof(c.value) = 'object'), '{}'::jsonb) as v
  ), typed as (
    select case when jsonb_typeof(raw.v -> 'sellers_enabled') = 'boolean' then (raw.v ->> 'sellers_enabled')::boolean
                else false end as sellers_enabled,
           case when jsonb_typeof(raw.v -> 'seller_requests_per_day') = 'number'
                then public.dealer_json_int(raw.v -> 'seller_requests_per_day') end as per_day
      from raw
  )
  select jsonb_build_object(
           'sellers_enabled', t.sellers_enabled,
           'sellers', t.sellers_enabled and (public.dealer_program() ->> 'enabled')::boolean,
           'seller_requests_per_day', case when t.per_day between 1 and 50 then t.per_day else 5 end,
           'seller_requests_per_seller_week', 3,
           'request_days', 14)
    from typed t
$$;

-- An approved, active dealer of the signed-in user (dealer_require_member's
-- errors, then not_approved).
create function public.dealer_require_approved() returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare
  v_id bigint := public.dealer_require_member();
begin
  if not exists (select 1 from public.dealers d
                  where d.id = v_id and d.approved_at is not null and d.status = 'active') then
    raise exception 'not_approved' using errcode = 'P0001';
  end if;
  return v_id;
end $$;

-- ---------------------------------------------------------------------------
-- 2. «Qué comprar»
-- ---------------------------------------------------------------------------

create function public.dealer_buy_opportunities()
returns table (make text, model text, searches integer, active_searches jsonb,
               year_from integer, year_to integer, budget numeric, budget_currency text,
               supply_total integer, supply_near integer)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer bigint := public.dealer_require_approved();
  v_min    integer := (public.dealer_program() ->> 'demand_min_count')::integer;
  v_blue   numeric := public.dealer_blue_rate();
  v_d      public.dealers;
begin
  select d.* into v_d from public.dealers d where d.id = v_dealer;

  return query
  with base as (
    select sp.user_id, sp.enabled, sp.filters as f, sp.origin_lat, sp.origin_lon, sp.radius_km,
           btrim(sp.filters ->> 'model') as s_model,
           case when jsonb_typeof(sp.filters -> 'make') = 'string' then nullif(btrim(sp.filters ->> 'make'), '') end
             as s_make
      from public.search_profiles sp
      join public.profiles pr on pr.id = sp.user_id
     where (sp.enabled or sp.created_at >= now() - interval '90 days')
       and jsonb_typeof(sp.filters -> 'model') = 'string'
       and btrim(sp.filters ->> 'model') <> ''
       and pr.role <> 'admin'
       and not exists (select 1 from public.dealer_members m
                        where m.dealer_id = v_dealer and m.user_id = sp.user_id)
  ), parsed as (
    select b.*,
           -- Same readings as dealer_demand: guarded, never a failing cast.
           coalesce(public.dealer_json_int(b.f -> 'year_min'),
                    case when jsonb_typeof(b.f -> 'years') = 'array'
                         then (select min(public.dealer_json_int(y)) from jsonb_array_elements(b.f -> 'years') y) end)
             as year_lo,
           coalesce(public.dealer_json_int(b.f -> 'year_max'),
                    case when jsonb_typeof(b.f -> 'years') = 'array'
                         then (select max(public.dealer_json_int(y)) from jsonb_array_elements(b.f -> 'years') y) end)
             as year_hi,
           public.dealer_json_number(b.f -> 'price_max') as price_max,
           case when jsonb_typeof(b.f -> 'currency') = 'string' and upper(b.f ->> 'currency') in ('ARS', 'USD')
                then upper(b.f ->> 'currency') end as s_currency,
           case when jsonb_typeof(b.f -> 'seller_types') = 'array'
                then (b.f -> 'seller_types' ? 'private') and not (b.f -> 'seller_types' ? 'dealer')
                else false end as private_only
      from base b
  ), zoned as (
    select p.*,
           coalesce(p.s_currency, case when p.price_max >= 1000000 then 'ARS' else 'USD' end) as cur,
           z.zones, z.hits
      from parsed p
     cross join lateral (
       select count(*) as zones,
              count(*) filter (where public.haversine_km(zz.lat, zz.lon, v_d.lat, v_d.lon) <= zz.radius) as hits
         from (select p.origin_lat as lat, p.origin_lon as lon, p.radius_km::double precision as radius
                where p.radius_km > 0 and p.origin_lat is not null and p.origin_lon is not null
               union all
               select public.dealer_json_number(e -> 'lat')::double precision,
                      public.dealer_json_number(e -> 'lon')::double precision,
                      public.dealer_json_number(e -> 'radius_km')::double precision
                 from jsonb_array_elements(case when jsonb_typeof(p.f -> 'extra_locations') = 'array'
                                                then p.f -> 'extra_locations' else '[]'::jsonb end) e
                where public.dealer_json_number(e -> 'lat') is not null
                  and public.dealer_json_number(e -> 'lon') is not null
                  and public.dealer_json_number(e -> 'radius_km') > 0) zz
     ) z
  ), kept as (
    select k.*,
           case when k.price_max is null or k.price_max <= 0 then null
                when k.cur = 'USD' then k.price_max
                else k.price_max / nullif(v_blue, 0) end as max_usd
      from zoned k
     where (k.zones = 0 or k.hits > 0) and not k.private_only
  ), grouped as (
    select lower(k.s_model) as g_model,
           mode() within group (order by k.s_model) as d_model,
           mode() within group (order by k.s_make) as d_make,
           count(*)::integer as n_searches,
           count(distinct k.user_id)::integer as n_people,
           count(*) filter (where k.enabled)::integer as n_active,
           count(distinct k.user_id) filter (where k.enabled)::integer as p_active,
           count(distinct k.user_id) filter (where k.year_lo is not null) as p_lo,
           percentile_disc(0.5) within group (order by k.year_lo) as med_lo,
           count(distinct k.user_id) filter (where k.year_hi is not null) as p_hi,
           percentile_disc(0.5) within group (order by k.year_hi) as med_hi,
           count(distinct k.user_id) filter (where k.max_usd is not null) as p_budget,
           (percentile_cont(0.5) within group (order by k.max_usd))::numeric as med_usd,
           mode() within group (order by k.cur) filter (where k.max_usd is not null) as g_cur
      from kept k
     group by lower(k.s_model)
  ), shown as (
    select g.*,
           case when g.p_lo >= v_min then g.med_lo end as y_from,
           case when g.p_hi >= v_min then g.med_hi end as y_to,
           case when g.p_budget >= v_min and g.med_usd is not null then
             case when g.g_cur = 'ARS' and v_blue is not null then round(g.med_usd * v_blue / 500000) * 500000
                  else round(g.med_usd / 500) * 500 end end as b_amount,
           case when g.p_budget >= v_min and g.med_usd is not null then
             case when g.g_cur = 'ARS' and v_blue is not null then 'ARS' else 'USD' end end as b_cur
      from grouped g
     where g.n_people >= v_min
       -- Not in my stock (available or reserved), by model.
       and not exists (select 1 from public.dealer_stock_items i
                        left join public.listings l on l.id = i.listing_id
                        where i.dealer_id = v_dealer and i.status in ('available', 'reserved')
                          and lower(btrim(coalesce(l.model, i.model))) = g.g_model)
  )
  select s.d_make, s.d_model, s.n_searches,
         public.dealer_demand_level(jsonb_build_object('searches', s.n_active, 'people', s.p_active), v_min),
         s.y_from, s.y_to, s.b_amount, s.b_cur,
         sup.total, sup.near
    from shown s
   cross join lateral (
     select count(*)::integer as total,
            count(*) filter (where o.lat is not null and o.lon is not null
                               and public.haversine_km(o.lat, o.lon, v_d.lat, v_d.lon) <= 50)::integer as near
       from public.listings o
      where lower(o.model) = s.g_model
        and (s.d_make is null or lower(o.make) = lower(s.d_make))
        and (s.y_from is null or o.year >= s.y_from)
        and (s.y_to is null or o.year <= s.y_to)
        and o.status = 'active'
        and o.last_seen_at >= now() - interval '30 days'
        and o.source <> 'directo'
        and not (o.attributes ? '_not_vehicle')
   ) sup
   order by s.n_searches desc, s.n_people desc, sup.total, s.d_model
   limit 30;
end $$;

-- The listings behind a «Qué comprar» row: same model (and make), years in the
-- range, active, seen in 30 days, never 'directo'; cheapest first. Public
-- listings only; any member of a dealer (the panel's market pages need no approval).
create function public.dealer_buy_market_listings(p_make text, p_model text, p_year_from integer, p_year_to integer)
returns table (listing_id bigint, source text, url text, title text, "trim" text, year integer,
               mileage_km integer, price numeric, currency text, price_usd numeric,
               location_text text, seller_type text, first_seen_at timestamptz, near boolean)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer bigint := public.dealer_require_member();
  v_d      public.dealers;
begin
  if p_model is null or btrim(p_model) = '' or char_length(p_model) > 60 then
    raise exception 'invalid_model' using errcode = 'P0001';
  end if;
  if (p_year_from is not null and p_year_from not between 1950 and 2100)
     or (p_year_to is not null and p_year_to not between 1950 and 2100) then
    raise exception 'invalid_year' using errcode = 'P0001';
  end if;
  select d.* into v_d from public.dealers d where d.id = v_dealer;

  return query
  select o.id, o.source, o.url, o.title, o.trim, o.year, o.mileage_km, o.price, o.currency, o.price_usd,
         o.location_text, o.seller_type, o.first_seen_at,
         coalesce(o.lat is not null and o.lon is not null
                  and public.haversine_km(o.lat, o.lon, v_d.lat, v_d.lon) <= 50, false)
    from public.listings o
   where lower(o.model) = lower(btrim(p_model))
     and (p_make is null or btrim(p_make) = '' or lower(o.make) = lower(btrim(p_make)))
     and (p_year_from is null or o.year >= p_year_from)
     and (p_year_to is null or o.year <= p_year_to)
     and o.status = 'active'
     and o.last_seen_at >= now() - interval '30 days'
     and o.source <> 'directo'
     and not (o.attributes ? '_not_vehicle')
   order by o.price_usd nulls last, o.id
   limit 300;
end $$;

-- ---------------------------------------------------------------------------
-- 3. Sellers: the car they sell, and the dealers' requests
-- ---------------------------------------------------------------------------

create table public.sell_intent_vehicles (
  user_id    uuid primary key references public.sell_intent (user_id) on delete cascade,
  make       text not null check (char_length(btrim(make)) between 1 and 40),
  model      text not null check (char_length(btrim(model)) between 1 and 60),
  year       integer check (year between 1950 and 2100),
  mileage_km integer check (mileage_km between 0 and 2000000),
  updated_at timestamptz not null default now()
);
create trigger sell_intent_vehicles_set_updated_at before update on public.sell_intent_vehicles
  for each row execute function public.set_updated_at();

create table public.dealer_seller_requests (
  id                 bigint generated always as identity primary key,
  dealer_id          bigint not null references public.dealers (id) on delete cascade,
  seller_user_id     uuid not null references public.profiles (id) on delete cascade,
  requested_by       uuid references public.profiles (id) on delete set null,
  message            text check (message is null or char_length(message) <= 300),
  status             text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  -- For the worker's notice to the seller (not built yet: the seller's page and its text need Juan's OK).
  seller_notified_at timestamptz,
  answered_at        timestamptz,
  -- Only after the seller accepts, and only what they chose to share.
  shared_name        text check (shared_name is null or char_length(shared_name) between 2 and 80),
  shared_phone       text check (shared_phone is null or shared_phone ~ '^[0-9]{8,15}$'),
  shared_email       text,
  consent_text       text check (consent_text is null or char_length(consent_text) between 20 and 300),
  consent_at         timestamptz,
  created_at         timestamptz not null default now(),
  unique (dealer_id, seller_user_id),
  check (status = 'accepted' or (shared_name is null and shared_phone is null and shared_email is null)),
  check (status <> 'accepted' or (consent_text is not null and consent_at is not null and shared_name is not null
                                  and (shared_phone is not null or shared_email is not null)))
);
create index dealer_seller_requests_dealer_idx on public.dealer_seller_requests (dealer_id, created_at desc);
create index dealer_seller_requests_seller_idx on public.dealer_seller_requests (seller_user_id, created_at desc);
create index dealer_seller_requests_unnotified_idx on public.dealer_seller_requests (id)
  where seller_notified_at is null and status = 'pending';

alter table public.sell_intent_vehicles enable row level security;
alter table public.dealer_seller_requests enable row level security;
revoke all on public.sell_intent_vehicles, public.dealer_seller_requests from public, anon, authenticated;
grant all on public.sell_intent_vehicles, public.dealer_seller_requests to service_role;
-- The seller reads their own car; writes go through save_my_sell_vehicle. Nobody
-- reads dealer_seller_requests directly: dealer_sellers() / my_dealer_seller_requests().
grant select on public.sell_intent_vehicles to authenticated;
create policy "sell_intent_vehicles: own read" on public.sell_intent_vehicles
  for select to authenticated using (user_id = (select auth.uid()));

-- The seller's own car. Only after «Sí» in sell_intent, never an anonymous session.
create function public.save_my_sell_vehicle(p_make text, p_model text, p_year integer, p_mileage_km integer)
returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_uid uuid := (select auth.uid());
begin
  if v_uid is null or coalesce(((select auth.jwt()) ->> 'is_anonymous')::boolean, false) then
    raise exception 'not_signed_in' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.sell_intent s where s.user_id = v_uid and s.answer = 'yes') then
    raise exception 'sell_intent_required' using errcode = 'P0001';
  end if;
  if p_make is null or char_length(btrim(p_make)) not between 1 and 40 then
    raise exception 'invalid_vehicle:make' using errcode = 'P0001';
  end if;
  if p_model is null or char_length(btrim(p_model)) not between 1 and 60 then
    raise exception 'invalid_vehicle:model' using errcode = 'P0001';
  end if;
  if p_year is not null and p_year not between 1950
                                    and extract(year from now() at time zone 'America/Argentina/Buenos_Aires')::integer + 1 then
    raise exception 'invalid_vehicle:year' using errcode = 'P0001';
  end if;
  if p_mileage_km is not null and p_mileage_km not between 0 and 2000000 then
    raise exception 'invalid_vehicle:mileage_km' using errcode = 'P0001';
  end if;
  insert into public.sell_intent_vehicles (user_id, make, model, year, mileage_km)
  values (v_uid, btrim(p_make), btrim(p_model), p_year, p_mileage_km)
  on conflict (user_id) do update
    set make = excluded.make, model = excluded.model, year = excluded.year, mileage_km = excluded.mileage_km;
end $$;

-- The sellers a dealer may see (internal): «Sí» + agencies_contact_ok, not an
-- admin, not a member of that dealer, within 100 km of the dealer (their saved
-- searches' points or their default location) or without any location. ref is
-- opaque and different for every dealer: no user id ever leaves the database,
-- and two dealers can't match their lists.
create function public.dealer_eligible_sellers(p_dealer bigint)
returns table (seller_user_id uuid, ref text, make text, model text, year integer, mileage_km integer,
               distance_km double precision, answered_at timestamptz)
language sql stable security definer set search_path = '' as $$
  with d as (select d.id, d.lat, d.lon from public.dealers d where d.id = p_dealer),
  sellers as (
    select s.user_id, s.agencies_contact_at, s.answered_at
      from public.sell_intent s
      join public.profiles pr on pr.id = s.user_id
     where s.answer = 'yes' and s.agencies_contact_ok
       and pr.role <> 'admin'
       and not exists (select 1 from public.dealer_members m where m.dealer_id = p_dealer and m.user_id = s.user_id)
  ), points as (
    select sp.user_id, sp.origin_lat as lat, sp.origin_lon as lon
      from public.search_profiles sp join sellers s on s.user_id = sp.user_id
     where sp.origin_lat is not null and sp.origin_lon is not null
    union all
    select pr.id, pr.default_origin_lat, pr.default_origin_lon
      from public.profiles pr join sellers s on s.user_id = pr.id
     where pr.default_origin_lat is not null and pr.default_origin_lon is not null
  ), dist as (
    select p.user_id, min(public.haversine_km(p.lat, p.lon, d.lat, d.lon)) as km
      from points p cross join d group by p.user_id
  )
  select s.user_id,
         md5('dealer-seller:' || d.id::text || ':' || s.user_id::text),
         v.make, v.model, v.year, v.mileage_km,
         dist.km,
         coalesce(s.agencies_contact_at, s.answered_at)
    from sellers s
    cross join d
    left join dist on dist.user_id = s.user_id
    left join public.sell_intent_vehicles v on v.user_id = s.user_id
   where dist.km is null or dist.km <= 100
$$;

-- The «Vendedores» page: one row per seller the dealer may see, with only coarse
-- data (distance band, km rounded to 5.000, «este mes» / «antes»), and the state of
-- this dealer's own request. The contact shows only after the seller accepted.
create function public.dealer_sellers()
returns table (ref text, make text, model text, year integer, mileage_km_rounded integer,
               distance_band text, recent boolean, request_id bigint, request_status text,
               requested_on date, shared_name text, shared_phone text, shared_email text, can_request boolean)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer bigint := public.dealer_require_member();
  v_cfg    jsonb := public.dealer_sellers_config();
  v_days   integer := (v_cfg ->> 'request_days')::integer;
  v_week   integer := (v_cfg ->> 'seller_requests_per_seller_week')::integer;
begin
  if not (v_cfg ->> 'sellers')::boolean then
    raise exception 'sellers_off' using errcode = 'P0001';
  end if;
  perform public.dealer_require_approved();

  return query
  select e.ref, e.make, e.model, e.year,
         case when e.mileage_km is not null then (round(e.mileage_km / 5000.0) * 5000)::integer end,
         case when e.distance_km is null then 'unknown'
              when e.distance_km < 10 then 'lt10'
              when e.distance_km < 25 then '10_25'
              when e.distance_km < 50 then '25_50'
              else '50_100' end,
         e.answered_at >= now() - interval '30 days',
         r.id,
         case when r.id is null then null
              when r.status = 'pending' and r.created_at < now() - make_interval(days => v_days) then 'expired'
              else r.status end,
         (r.created_at at time zone 'America/Argentina/Buenos_Aires')::date,
         case when r.status = 'accepted' then r.shared_name end,
         case when r.status = 'accepted' then r.shared_phone end,
         case when r.status = 'accepted' then r.shared_email end,
         r.id is null
           and (select count(*) from public.dealer_seller_requests x
                 where x.seller_user_id = e.seller_user_id and x.created_at >= now() - interval '7 days') < v_week
    from public.dealer_eligible_sellers(v_dealer) e
    left join public.dealer_seller_requests r on r.dealer_id = v_dealer and r.seller_user_id = e.seller_user_id
   order by (r.id is not null), coalesce(e.distance_km, 1e9), e.answered_at desc, e.ref
   limit 200;
end $$;

-- An approved dealer asks to contact a seller. Never hands over any contact: the
-- seller decides (answer_dealer_seller_request). One request per dealer and seller;
-- at most seller_requests_per_day new ones per dealer in 24 h and 3 per seller in 7 days.
create function public.dealer_request_seller(p_ref text, p_message text default null) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_cfg    jsonb := public.dealer_sellers_config();
  v_uid    uuid := (select auth.uid());
  v_seller uuid;
  v_msg    text := nullif(btrim(coalesce(p_message, '')), '');
  v_req    public.dealer_seller_requests;
begin
  if not (v_cfg ->> 'sellers')::boolean then
    raise exception 'sellers_off' using errcode = 'P0001';
  end if;
  perform public.dealer_require_approved();
  if v_msg is not null and char_length(v_msg) > 300 then
    raise exception 'invalid_message' using errcode = 'P0001';
  end if;
  select e.seller_user_id into v_seller
    from public.dealer_eligible_sellers(v_dealer) e where e.ref = p_ref;
  if v_seller is null then
    raise exception 'seller_not_found' using errcode = 'P0001';
  end if;

  -- One request at a time per dealer: the caps below can't be raced.
  perform 1 from public.dealers d where d.id = v_dealer for update;

  select r.* into v_req from public.dealer_seller_requests r
   where r.dealer_id = v_dealer and r.seller_user_id = v_seller;
  if found then
    return jsonb_build_object('request_id', v_req.id, 'created', false, 'status', v_req.status);
  end if;
  if (select count(*) from public.dealer_seller_requests r
       where r.dealer_id = v_dealer and r.created_at >= now() - interval '24 hours')
     >= (v_cfg ->> 'seller_requests_per_day')::integer then
    raise exception 'rate_limited' using errcode = 'P0001';
  end if;
  if (select count(*) from public.dealer_seller_requests r
       where r.seller_user_id = v_seller and r.created_at >= now() - interval '7 days')
     >= (v_cfg ->> 'seller_requests_per_seller_week')::integer then
    raise exception 'seller_busy' using errcode = 'P0001';
  end if;

  insert into public.dealer_seller_requests (dealer_id, seller_user_id, requested_by, message)
  values (v_dealer, v_seller, v_uid, v_msg)
  returning * into v_req;
  -- The dealer's event: no seller id, no message.
  insert into public.events (user_id, name, props)
  values (v_uid, 'dealer_seller_requested', jsonb_build_object('request_id', v_req.id, 'dealer_id', v_dealer));
  return jsonb_build_object('request_id', v_req.id, 'created', true, 'status', v_req.status);
end $$;

-- The seller's side: the requests waiting for them (and the ones they answered).
-- For the seller's page, a follow-up (its text needs Juan's OK).
create function public.my_dealer_seller_requests()
returns table (id bigint, dealer_name text, dealer_locality text, message text, status text,
               created_at timestamptz, answered_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_uid  uuid := (select auth.uid());
  v_days integer := (public.dealer_sellers_config() ->> 'request_days')::integer;
begin
  if v_uid is null then
    raise exception 'not_signed_in' using errcode = 'P0001';
  end if;
  return query
  select r.id, d.name, d.locality_label, r.message,
         case when r.status = 'pending' and r.created_at < now() - make_interval(days => v_days) then 'expired'
              else r.status end,
         r.created_at, r.answered_at
    from public.dealer_seller_requests r
    join public.dealers d on d.id = r.dealer_id
   where r.seller_user_id = v_uid
   order by r.created_at desc
   limit 50;
end $$;

-- The seller answers. Accepting needs their own consent text (naming the agency),
-- a name and at least a phone or the account's email; only that goes to the dealer.
create function public.answer_dealer_seller_request(p_request_id bigint, p_accept boolean, p_name text default null,
                                                    p_phone text default null, p_share_email boolean default false,
                                                    p_consent_text text default null)
returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_uid   uuid := (select auth.uid());
  v_cfg   jsonb := public.dealer_sellers_config();
  v_req   public.dealer_seller_requests;
  v_name  text := btrim(coalesce(p_name, ''));
  v_phone text := nullif(regexp_replace(coalesce(p_phone, ''), '[^0-9]', '', 'g'), '');
  v_email text;
begin
  if v_uid is null or coalesce(((select auth.jwt()) ->> 'is_anonymous')::boolean, false) then
    raise exception 'not_signed_in' using errcode = 'P0001';
  end if;
  if not (v_cfg ->> 'sellers')::boolean then
    raise exception 'sellers_off' using errcode = 'P0001';
  end if;
  select r.* into v_req from public.dealer_seller_requests r
   where r.id = p_request_id and r.seller_user_id = v_uid and r.status = 'pending'
     and r.created_at >= now() - make_interval(days => (v_cfg ->> 'request_days')::integer)
   for update;
  if not found then
    raise exception 'request_not_found' using errcode = 'P0001';
  end if;

  if p_accept is not true then
    update public.dealer_seller_requests set status = 'declined', answered_at = now() where id = v_req.id;
    insert into public.events (user_id, name, props)
    values (v_uid, 'dealer_seller_answered', jsonb_build_object('request_id', v_req.id, 'accepted', false));
    return;
  end if;

  -- The consent behind the request still stands.
  if not exists (select 1 from public.sell_intent s where s.user_id = v_uid and s.answer = 'yes' and s.agencies_contact_ok) then
    raise exception 'request_not_found' using errcode = 'P0001';
  end if;
  if p_consent_text is null or char_length(btrim(p_consent_text)) not between 20 and 300 then
    raise exception 'consent_required' using errcode = 'P0001';
  end if;
  if char_length(v_name) not between 2 and 80 then
    raise exception 'invalid_contact:name' using errcode = 'P0001';
  end if;
  if v_phone is not null and char_length(v_phone) not between 8 and 15 then
    raise exception 'invalid_contact:phone' using errcode = 'P0001';
  end if;
  if p_share_email then
    select nullif(btrim(pr.email), '') into v_email from public.profiles pr where pr.id = v_uid;
  end if;
  if v_phone is null and v_email is null then
    raise exception 'invalid_contact:phone' using errcode = 'P0001';
  end if;

  update public.dealer_seller_requests
     set status = 'accepted', answered_at = now(), shared_name = v_name, shared_phone = v_phone,
         shared_email = v_email, consent_text = btrim(p_consent_text), consent_at = now()
   where id = v_req.id;
  insert into public.events (user_id, name, props)
  values (v_uid, 'dealer_seller_answered', jsonb_build_object('request_id', v_req.id, 'accepted', true));
end $$;

-- ---------------------------------------------------------------------------
-- 4. Grants
-- ---------------------------------------------------------------------------

revoke all on function
  public.dealer_sellers_config(),
  public.dealer_require_approved(),
  public.dealer_buy_opportunities(),
  public.dealer_buy_market_listings(text, text, integer, integer),
  public.save_my_sell_vehicle(text, text, integer, integer),
  public.dealer_eligible_sellers(bigint),
  public.dealer_sellers(),
  public.dealer_request_seller(text, text),
  public.my_dealer_seller_requests(),
  public.answer_dealer_seller_request(bigint, boolean, text, text, boolean, text)
from public, anon, authenticated;

grant execute on function public.dealer_sellers_config() to anon, authenticated, service_role;
grant execute on function
  public.dealer_buy_opportunities(),
  public.dealer_buy_market_listings(text, text, integer, integer),
  public.save_my_sell_vehicle(text, text, integer, integer),
  public.dealer_sellers(),
  public.dealer_request_seller(text, text),
  public.my_dealer_seller_requests(),
  public.answer_dealer_seller_request(bigint, boolean, text, text, boolean, text)
to authenticated, service_role;
-- Internal: only the functions above (security definer) and the service role.
grant execute on function public.dealer_require_approved(), public.dealer_eligible_sellers(bigint) to service_role;

notify pgrst, 'reload schema';
