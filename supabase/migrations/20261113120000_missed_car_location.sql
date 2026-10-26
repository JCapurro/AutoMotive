-- El auto del mail 2.5 tiene que estar dentro de la zona de la búsqueda.
--
-- El conteo usa el motor de las alertas: un auto sin coordenadas pasa el
-- filtro de ubicación como «desconocido» y se cuenta. Para el número está
-- bien, pero el auto que el mail muestra como «la oportunidad que te
-- perdiste» tiene que estar confirmado dentro del radio. Si la búsqueda tiene
-- radio, missed_car solo elige autos con coordenadas a esa distancia o menos.
-- Sin ninguno, el payload no lleva `car` y el mail sale con el conteo.

create or replace function public.missed_car(p_search bigint, p_ended timestamptz) returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_strip_nulls(jsonb_build_object(
           'listing_id', l.id, 'title', l.title, 'make', l.make, 'model', l.model, 'trim', l.trim,
           'year', l.year, 'price', l.price, 'currency', l.currency, 'km', l.mileage_km,
           'location', l.location_text,
           'images', case when jsonb_typeof(l.images) = 'array'
                          then (select coalesce(jsonb_agg(i.value order by i.ord), '[]'::jsonb)
                                  from jsonb_array_elements(l.images) with ordinality i (value, ord)
                                 where i.ord <= 3) end,
           'below', m.level = 'high',
           'diff_pct', m.diff_pct,
           'gone', l.status = 'gone',
           'days_listed', case when l.status = 'gone' then greatest(1, ceil(extract(epoch from
                            l.last_seen_at - coalesce(l.published_at, l.first_seen_at)) / 86400)::int) end))
    from public.expired_search_matches m
    join public.listings l on l.id = m.listing_id
    join public.search_profiles sp on sp.id = m.search_profile_id
   where m.search_profile_id = p_search and m.access_ended_at = p_ended
     and l.price is not null and not l.price_partial
     -- Same distance as intelligence/matching.py (haversine, 6371.0088 km).
     and (sp.radius_km is null or sp.radius_km <= 0 or sp.origin_lat is null or sp.origin_lon is null
          or (l.lat is not null and l.lon is not null
              and 2 * 6371.0088 * asin(least(1, sqrt(
                    power(sin(radians(l.lat - sp.origin_lat) / 2), 2)
                    + cos(radians(sp.origin_lat)) * cos(radians(l.lat))
                      * power(sin(radians(l.lon - sp.origin_lon) / 2), 2)))) <= sp.radius_km))
   order by m.level = 'high' desc, m.diff_pct desc nulls last, m.score desc nulls last,
            m.created_at desc, l.id desc
   limit 1
$$;

revoke all on function public.missed_car(bigint, timestamptz) from public, anon, authenticated;
