-- PRO-01 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md, decisión 10):
-- 20261115120000's preview_search, plus the strict seller filter. As in
-- intelligence/matching.py it applies only for a plan with
-- plan_feature('seller_filter') (asked once per query, in the f CTE, never per
-- row), reads the effective seller (a «posible agencia», dealer_inferred,
-- counts as a dealer, F-02) and lets an unknown seller through. Without the
-- feature seller_types is a soft preference and filters nothing.
create or replace function public.preview_search(
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
    select nullif(btrim(p_filters->>'make'), '')           as make,
           nullif(btrim(p_filters->>'model'), '')          as model,
           public.search_is_model_less(p_filters)          as model_less,
           public.search_body_types(p_filters)             as body_types,
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
                then array(select lower(jsonb_array_elements_text(p_filters->'trims'))) end as strict_trims,
           case when jsonb_typeof(p_filters->'seller_types') = 'array'
                     and jsonb_array_length(p_filters->'seller_types') > 0
                     and public.plan_feature((select auth.uid()), 'seller_filter')
                then array(select jsonb_array_elements_text(p_filters->'seller_types')) end as seller_types
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  -- The search's own place and the ones it adds (filters->'extra_locations').
  zones as (
    select p_origin_lat as lat, p_origin_lon as lon, p_radius_km as radius
     where p_radius_km is not null and p_origin_lat is not null and p_origin_lon is not null
    union all
    select (e->>'lat')::double precision, (e->>'lon')::double precision, (e->>'radius_km')::double precision
      from jsonb_array_elements(case when jsonb_typeof(p_filters->'extra_locations') = 'array'
                                     then p_filters->'extra_locations' else '[]'::jsonb end) e
  ),
  -- One branch per shape, each with its own index: (lower(make), lower(model),
  -- year) or listings_body_type_active_idx.
  candidates as (
    select l.*
      from f
      join public.listings l on lower(l.make) = lower(f.make)
     where f.make is not null
       and (f.model is null or lower(l.model) = lower(f.model))
       and l.status = 'active'
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
    union all
    select l.*
      from f
      join public.listings l on l.body_type = any (f.body_types)
     where f.model_less
       and f.body_types is not null
       and l.status = 'active'
       and l.body_type is not null
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
  ),
  priced as (
    select l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from candidates l
     cross join f
      left join fx on true
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
       and (f.body_types is null or p.body_type = any (f.body_types)
            or (p.body_type is null and not f.model_less))
       and (f.sources is null or p.source = any (f.sources))
       and (f.seller_types is null
            or (case when p.seller_type = 'dealer' or p.dealer_inferred then 'dealer' else p.seller_type end) is null
            or (case when p.seller_type = 'dealer' or p.dealer_inferred then 'dealer' else p.seller_type end)
               = any (f.seller_types))
       and (f.strict_trims is null or p.trim is null
            or exists (select 1 from unnest(f.strict_trims) t where position(t in lower(p.trim)) > 0))
       and (p.lat is null or p.lon is null
            or not exists (select 1 from zones)
            or exists (select 1 from zones z where public.haversine_km(z.lat, z.lon, p.lat, p.lon) <= z.radius))
  ),
  sample as (
    select h.id, h.title, h.make, h.model, h.trim, h.year, h.price, h.currency, h.mileage_km,
           h.location_text, h.source, h.first_seen_at, h.body_type
      from hits h
     order by h.first_seen_at desc
     limit 3
  )
  select jsonb_build_object(
           'count',  (select count(*) from hits),
           'sample', coalesce((select jsonb_agg(to_jsonb(s) order by s.first_seen_at desc) from sample s),
                              '[]'::jsonb))
$$;

notify pgrst, 'reload schema';
