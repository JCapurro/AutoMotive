-- Agencias: why a car's price is where it is against the market.
--
-- dealer_market_ref() compares a car with every listing of its model, year ±1,
-- whatever the mileage, the trim or who sells it. So «18 % abajo» can be a car
-- with many km, a base trim, or a real gap. dealer_price_context() gives the
-- panel the medians of narrower cuts of THE SAME POOL, so the web can say which
-- of those explains the gap (web/lib/dealer-price-reasons.ts) or that none does.
--
-- Read only, public listings only, members of the dealer only, off with the
-- program. No new table, no change to existing functions.
-- Needs 20261228120000_dealer_program.sql.
--
-- Rollback: drop function public.dealer_price_context();

-- The pool is the twin of dealer_market_ref's and dealer_market_listings':
-- change the three together.
create function public.dealer_price_context()
returns table (item_id bigint, context jsonb)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer bigint := public.dealer_require_member();
begin
  return query
  with base as (
    select i.id as b_item_id, l.id as b_listing_id,
           case when l.id is not null then l.make else i.make end as b_make,
           case when l.id is not null then l.model else i.model end as b_model,
           nullif(lower(btrim(case when l.id is not null then l.trim else i.trim end)), '') as b_trim,
           case when l.id is not null then l.year else i.year end as b_year,
           case when l.id is not null then l.mileage_km else i.mileage_km end as b_km
      from public.dealer_stock_items i
      left join public.listings l on l.id = i.listing_id
     where i.dealer_id = v_dealer and i.status in ('available', 'reserved')
  )
  select b.b_item_id,
         (select jsonb_build_object(
                   'km', b.b_km,
                   'km_n', count(o.mileage_km)::integer,
                   'km_median', round(percentile_cont(0.5) within group (order by o.mileage_km)
                                        filter (where o.mileage_km is not null)::numeric)::integer,
                   'same_year', jsonb_build_object(
                     'n', (count(*) filter (where o.year = b.b_year))::integer,
                     'median', round(percentile_cont(0.5) within group (order by o.price_usd)
                                       filter (where o.year = b.b_year)::numeric, 2)),
                   -- Same use: within 20 % of the car's km, or 15.000 km for a car with few.
                   'similar_km', jsonb_build_object(
                     'n', (count(*) filter (where k.near))::integer,
                     'median', round(percentile_cont(0.5) within group (order by o.price_usd)
                                       filter (where k.near)::numeric, 2)),
                   'closest', jsonb_build_object(
                     'n', (count(*) filter (where k.near and o.year = b.b_year))::integer,
                     'median', round(percentile_cont(0.5) within group (order by o.price_usd)
                                       filter (where k.near and o.year = b.b_year)::numeric, 2)),
                   'same_trim', jsonb_build_object(
                     'n', (count(*) filter (where k.same_trim))::integer,
                     'median', round(percentile_cont(0.5) within group (order by o.price_usd)
                                       filter (where k.same_trim)::numeric, 2)),
                   'dealers', jsonb_build_object(
                     'n', (count(*) filter (where o.seller_type = 'dealer'))::integer,
                     'median', round(percentile_cont(0.5) within group (order by o.price_usd)
                                       filter (where o.seller_type = 'dealer')::numeric, 2)))
            from public.listings o
           cross join lateral (
                  select coalesce(b.b_km is not null and o.mileage_km is not null
                                  and abs(o.mileage_km - b.b_km) <= greatest(15000, b.b_km * 0.2), false) as near,
                         coalesce(b.b_trim is not null and lower(btrim(o.trim)) = b.b_trim, false) as same_trim) k
           where lower(o.make) = lower(b.b_make) and lower(o.model) = lower(b.b_model)
             and o.year between b.b_year - 1 and b.b_year + 1
             and o.status = 'active'
             and o.last_seen_at >= now() - interval '30 days'
             and o.price_usd > 0 and not o.price_partial
             and o.source <> 'directo'
             and o.id is distinct from b.b_listing_id
             and not (o.attributes ? '_not_vehicle'))
    from base b
   order by b.b_item_id;
end $$;

revoke all on function public.dealer_price_context() from public, anon;
grant execute on function public.dealer_price_context() to authenticated, service_role;

comment on function public.dealer_price_context() is
  'Per car on sale of my dealer: medians (USD) of narrower cuts of dealer_market_ref''s pool (same year, similar km, '
  'both, same trim, sold by dealers) and the pool''s median km. For the panel''s «por qué» of a price off the market.';
