-- Agencias: the market reference takes the mileage (and the trim) into account.
--
-- Juan, 20/11: «el kilometraje es CENTRAL en el valor del auto». Until now
-- dealer_market_ref() compared a car with every listing of its model, year ±1.
-- Now it uses the narrowest group that has enough listings (comparables.min_n):
--
--   version_km   same trim, year ±1, km within 20 % (or 15.000 km) of the car's
--   km           year ±1, km within 20 % (or 15.000 km)
--   model        year ±1, any km: the car has no km loaded, or too few listings
--                with similar km. The panel says so and asks for the km.
--
-- The JSON keeps its keys (n, median, p25, p75, vs_market_pct, enough...) for
-- the group it used, and adds "basis", "km", "km_tol" and "wide" (n, median and
-- vs_market_pct of the whole model, as before). dealer_stock_insights() and
-- dealer_alert_scan() pass the car's km and trim (bodies otherwise unchanged);
-- dealer_market_listings() marks which listings are the reference (in_ref).
-- The km band is the twin of dealer_price_context()'s: change them together.
-- Needs 20261228120000, 20261229120000 and 20270101120000.
--
-- Rollback: re-create the four functions from those migrations.

drop function public.dealer_market_ref(text, text, integer, numeric, bigint);

create function public.dealer_market_ref(p_make text, p_model text, p_year integer, p_price_usd numeric,
                                         p_exclude_listing bigint, p_km integer default null, p_trim text default null)
returns jsonb
language sql stable security definer set search_path = '' as $$
  with cfg as (
    select coalesce(case when jsonb_typeof(c.value -> 'min_n') = 'number'
                         then public.dealer_json_int(c.value -> 'min_n') end, 5) as min_n,
           nullif(lower(btrim(p_trim)), '') as trim,
           case when p_km > 0 then greatest(15000, round(p_km * 0.2))::integer end as km_tol
      from (select 1) one
      left join public.app_config c on c.key = 'comparables'
  ), pool as (
    select o.price_usd,
           coalesce(o.mileage_km is not null and abs(o.mileage_km - p_km) <= cfg.km_tol, false) as near,
           coalesce(lower(btrim(o.trim)) = cfg.trim, false) as same_trim
      from public.listings o cross join cfg
     where lower(o.make) = lower(p_make) and lower(o.model) = lower(p_model)
       and o.year between p_year - 1 and p_year + 1
       and o.status = 'active'
       and o.last_seen_at >= now() - interval '30 days'
       and o.price_usd > 0 and not o.price_partial
       and o.source <> 'directo'
       and o.id is distinct from p_exclude_listing
       and not (o.attributes ? '_not_vehicle')
  ), pick as (
    select case when (select count(*) from pool p where p.near and p.same_trim) >= cfg.min_n then 'version_km'
                when (select count(*) from pool p where p.near) >= cfg.min_n then 'km'
                else 'model' end as basis
      from cfg
  ), stats as (
    select count(*)::integer as n,
           round(percentile_cont(0.5)  within group (order by p.price_usd)::numeric, 2) as median,
           round(percentile_cont(0.25) within group (order by p.price_usd)::numeric, 2) as p25,
           round(percentile_cont(0.75) within group (order by p.price_usd)::numeric, 2) as p75
      from pool p cross join pick k
     where k.basis = 'model' or (p.near and (k.basis = 'km' or p.same_trim))
  ), wide as (
    select count(*)::integer as n,
           round(percentile_cont(0.5) within group (order by p.price_usd)::numeric, 2) as median
      from pool p
  )
  select jsonb_build_object(
           'n', s.n, 'median', s.median, 'p25', s.p25, 'p75', s.p75,
           'vs_market_pct', case when s.median > 0 and p_price_usd > 0
                                 then round((p_price_usd / s.median - 1) * 100, 1) end,
           'enough', s.n >= cfg.min_n,
           'year_tol', 1, 'days', 30, 'blue', public.dealer_blue_rate(),
           'basis', k.basis, 'km', case when p_km > 0 then p_km end, 'km_tol', cfg.km_tol,
           'wide', jsonb_build_object(
                     'n', w.n, 'median', w.median,
                     'vs_market_pct', case when w.median > 0 and p_price_usd > 0
                                           then round((p_price_usd / w.median - 1) * 100, 1) end))
    from stats s cross join cfg cross join pick k cross join wide w
$$;

revoke all on function public.dealer_market_ref(text, text, integer, numeric, bigint, integer, text) from public, anon, authenticated;
grant execute on function public.dealer_market_ref(text, text, integer, numeric, bigint, integer, text) to service_role;

comment on function public.dealer_market_ref(text, text, integer, numeric, bigint, integer, text) is
  'Published prices (USD) a car is compared against: the narrowest of same trim + similar km, similar km, or the '
  'whole model (year ±1, active, seen in 30 days, never directo) with at least comparables.min_n listings. "basis" '
  'says which; "wide" is the whole model.';

-- The stock page: the same body, passing the car's km and trim.
create or replace function public.dealer_stock_insights()
returns table (item_id bigint, listing_id bigint, origin text, status text, sync_state text,
               make text, model text, "trim" text, year integer, mileage_km integer,
               price numeric, currency text, price_usd numeric,
               confirmed_at timestamptz, confirm_due_at timestamptz,
               hidden_reason text,
               market jsonb, days_in_stock integer, model_days_to_sell jsonb, demand jsonb)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer   bigint := public.dealer_require_member();
  v_prog     jsonb := public.dealer_program();
  v_days     integer := (v_prog ->> 'manual_confirm_days')::integer;
  v_min      integer := (v_prog ->> 'demand_min_count')::integer;
  v_blue     numeric := public.dealer_blue_rate();
  v_d        public.dealers;
  v_members  uuid[];
begin
  select d.* into v_d from public.dealers d where d.id = v_dealer;
  select coalesce(array_agg(m.user_id), '{}'::uuid[]) into v_members
    from public.dealer_members m where m.dealer_id = v_dealer;

  return query
  with base as (
    select i.id as b_item_id, l.id as b_listing_id, i.origin as b_origin, i.status as b_status,
           i.sync_state as b_sync_state, i.created_at as b_created_at,
           case when l.id is not null then l.make else i.make end as b_make,
           case when l.id is not null then l.model else i.model end as b_model,
           case when l.id is not null then l.trim else i.trim end as b_trim,
           case when l.id is not null then l.year else i.year end as b_year,
           case when l.id is not null then l.mileage_km else i.mileage_km end as b_km,
           case when l.id is not null then l.price else i.price end as b_price,
           case when l.id is not null then l.currency else i.currency end as b_currency,
           case when i.origin = 'sync' then l.dealer_confirmed_at else i.confirmed_at end as b_confirmed_at,
           -- No listing yet, or its listing ended (the worker makes it again):
           -- not sent, whatever the gate would say of the ended row.
           case when l.id is null or l.status <> 'active' then 'pending_sync'
                else public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at)
           end as b_hidden,
           coalesce(l.source, 'directo') as b_source,
           coalesce(i.in_stock_since,
                    (l.published_at at time zone 'America/Argentina/Buenos_Aires')::date,
                    (i.created_at at time zone 'America/Argentina/Buenos_Aires')::date) as b_since
      from public.dealer_stock_items i
      left join public.listings l on l.id = i.listing_id
     where i.dealer_id = v_dealer and i.status <> 'archived'
  ), priced as (
    select b.*,
           case when b.b_price is null or b.b_price <= 0 then null
                when b.b_currency = 'USD' then b.b_price
                when b.b_currency = 'ARS' then round(b.b_price / nullif(v_blue, 0), 2)
           end as b_price_usd
      from base b
  )
  select p.b_item_id, p.b_listing_id, p.b_origin, p.b_status, p.b_sync_state,
         p.b_make, p.b_model, p.b_trim, p.b_year, p.b_km,
         p.b_price, p.b_currency, p.b_price_usd,
         p.b_confirmed_at,
         case when p.b_origin in ('manual', 'sheet') and p.b_confirmed_at is not null
              then p.b_confirmed_at + make_interval(days => v_days) end,
         p.b_hidden,
         public.dealer_market_ref(p.b_make, p.b_model, p.b_year, p.b_price_usd, p.b_listing_id, p.b_km, p.b_trim),
         ((now() at time zone 'America/Argentina/Buenos_Aires')::date - p.b_since)::integer,
         public.dealer_model_days_to_sell(p.b_make, p.b_model, p.b_year),
         case when v_d.approved_at is null then '{"approved": false}'::jsonb
              else (select jsonb_build_object(
                             'approved', true, 'window_days', 90, 'min_count', v_min,
                             'levels', jsonb_build_object(
                                         'model', public.dealer_demand_level(r.raw -> 'model', v_min),
                                         'fits', public.dealer_demand_level(r.raw -> 'fits', v_min),
                                         'zone', public.dealer_demand_level(r.raw -> 'zone', v_min),
                                         'active_zone', public.dealer_demand_level(r.raw -> 'active_zone', v_min)))
                      from (select public.dealer_demand(p.b_make, p.b_model, p.b_year, p.b_price, p.b_currency,
                                                        p.b_km, v_d.lat, v_d.lon, v_members, p.b_source) as raw) r)
         end
    from priced p
   order by p.b_created_at, p.b_item_id;
end $$;

-- The alerts scan (fase 1): the same body, passing the car's km and trim.
create or replace function public.dealer_alert_scan(p_dealer_id bigint, p_cheaper_pct numeric default 8,
                                         p_radius_km numeric default 30)
returns table (item_id bigint, listing_id bigint, make text, model text, "trim" text, year integer,
               mileage_km integer, price numeric, currency text, price_usd numeric,
               market jsonb, model_days jsonb, days_in_stock integer, demand jsonb, cheaper jsonb, state jsonb)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_d       public.dealers;
  v_blue    numeric := public.dealer_blue_rate();
  v_members uuid[];
begin
  select d.* into v_d from public.dealers d where d.id = p_dealer_id;
  if v_d.id is null then
    return;
  end if;
  select coalesce(array_agg(m.user_id), '{}'::uuid[]) into v_members
    from public.dealer_members m where m.dealer_id = p_dealer_id;

  return query
  with base as (
    select i.id as b_item_id, l.id as b_listing_id, i.created_at as b_created_at,
           case when l.id is not null then l.make else i.make end as b_make,
           case when l.id is not null then l.model else i.model end as b_model,
           case when l.id is not null then l.trim else i.trim end as b_trim,
           case when l.id is not null then l.year else i.year end as b_year,
           case when l.id is not null then l.mileage_km else i.mileage_km end as b_km,
           case when l.id is not null then l.price else i.price end as b_price,
           case when l.id is not null then l.currency else i.currency end as b_currency,
           coalesce(l.source, 'directo') as b_source,
           coalesce(i.in_stock_since,
                    (l.published_at at time zone 'America/Argentina/Buenos_Aires')::date,
                    (i.created_at at time zone 'America/Argentina/Buenos_Aires')::date) as b_since
      from public.dealer_stock_items i
      left join public.listings l on l.id = i.listing_id
     where i.dealer_id = p_dealer_id and i.status = 'available'
  ), priced as (
    select b.*,
           case when b.b_price is null or b.b_price <= 0 then null
                when b.b_currency = 'USD' then b.b_price
                when b.b_currency = 'ARS' then round(b.b_price / nullif(v_blue, 0), 2)
           end as b_price_usd,
           (select to_jsonb(s) from public.dealer_alert_state s where s.item_id = b.b_item_id) as b_state
      from base b
  )
  select p.b_item_id, p.b_listing_id, p.b_make, p.b_model, p.b_trim, p.b_year, p.b_km,
         p.b_price, p.b_currency, p.b_price_usd,
         public.dealer_market_ref(p.b_make, p.b_model, p.b_year, p.b_price_usd, p.b_listing_id, p.b_km, p.b_trim),
         public.dealer_model_days_to_sell(p.b_make, p.b_model, p.b_year),
         ((now() at time zone 'America/Argentina/Buenos_Aires')::date - p.b_since)::integer,
         case when v_d.approved_at is not null then
           public.dealer_demand(p.b_make, p.b_model, p.b_year, p.b_price, p.b_currency, p.b_km,
                                v_d.lat, v_d.lon, v_members, p.b_source) -> 'zone'
         end,
         (select jsonb_build_object('listing_id', o.id, 'price_usd', o.price_usd, 'year', o.year,
                                    'mileage_km', o.mileage_km, 'source', o.source, 'source_name', s.name,
                                    'distance_km', round(public.haversine_km(v_d.lat, v_d.lon, o.lat, o.lon)::numeric))
            from public.listings o
            left join public.sources s on s.id = o.source
           where p.b_price_usd > 0
             and lower(o.make) = lower(p.b_make) and lower(o.model) = lower(p.b_model)
             and o.year between p.b_year - 1 and p.b_year + 1
             and o.status = 'active'
             and o.last_seen_at >= now() - interval '30 days'
             and o.price_usd > 0 and not o.price_partial
             and o.source <> 'directo'
             and o.id is distinct from p.b_listing_id
             and o.dealer_id is distinct from p_dealer_id
             and not (o.attributes ? '_not_vehicle')
             and o.first_seen_at > coalesce((p.b_state ->> 'cheaper_since')::timestamptz, now())
             and o.price_usd <= p.b_price_usd * (1 - greatest(coalesce(p_cheaper_pct, 8), 1) / 100)
             and (o.mileage_km is null or p.b_km is null or o.mileage_km <= p.b_km * 1.3 + 5000)
             and o.lat is not null and o.lon is not null
             and public.haversine_km(v_d.lat, v_d.lon, o.lat, o.lon) <= coalesce(p_radius_km, 30)
           order by o.price_usd, o.id
           limit 1),
         p.b_state
    from priced p
   order by p.b_created_at, p.b_item_id;
end $$;

-- «Ver el mercado»: the whole model as before, each listing marked when it is
-- part of the reference the car's price is compared against.
drop function public.dealer_market_listings(bigint);

create function public.dealer_market_listings(p_item_id bigint)
returns table (listing_id bigint, source text, url text, title text, "trim" text, year integer,
               mileage_km integer, price numeric, currency text, price_usd numeric,
               location_text text, seller_type text, first_seen_at timestamptz, in_ref boolean)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer bigint := public.dealer_require_member();
  v_make text; v_model text; v_year integer; v_listing bigint; v_km integer; v_trim text;
  v_basis text; v_tol integer;
begin
  select case when l.id is not null then l.make else i.make end,
         case when l.id is not null then l.model else i.model end,
         case when l.id is not null then l.year else i.year end,
         l.id,
         case when l.id is not null then l.mileage_km else i.mileage_km end,
         nullif(lower(btrim(case when l.id is not null then l.trim else i.trim end)), '')
    into v_make, v_model, v_year, v_listing, v_km, v_trim
    from public.dealer_stock_items i
    left join public.listings l on l.id = i.listing_id
   where i.id = p_item_id and i.dealer_id = v_dealer;
  if not found then
    raise exception 'not_found' using errcode = 'P0001';
  end if;
  select r.ref ->> 'basis', (r.ref ->> 'km_tol')::integer into v_basis, v_tol
    from (select public.dealer_market_ref(v_make, v_model, v_year, null, v_listing, v_km, v_trim) as ref) r;

  return query
  select o.id, o.source, o.url, o.title, o.trim, o.year, o.mileage_km, o.price, o.currency, o.price_usd,
         o.location_text, o.seller_type, o.first_seen_at,
         v_basis = 'model'
         or (coalesce(o.mileage_km is not null and abs(o.mileage_km - v_km) <= v_tol, false)
             and (v_basis = 'km' or coalesce(lower(btrim(o.trim)) = v_trim, false)))
    from public.listings o
   where lower(o.make) = lower(v_make) and lower(o.model) = lower(v_model)
     and o.year between v_year - 1 and v_year + 1
     and o.status = 'active'
     and o.last_seen_at >= now() - interval '30 days'
     and o.price_usd > 0 and not o.price_partial
     and o.source <> 'directo'
     and o.id is distinct from v_listing
     and not (o.attributes ? '_not_vehicle')
   order by o.price_usd, o.id
   limit 500;
end $$;

revoke all on function public.dealer_market_listings(bigint) from public, anon;
grant execute on function public.dealer_market_listings(bigint) to authenticated, service_role;
