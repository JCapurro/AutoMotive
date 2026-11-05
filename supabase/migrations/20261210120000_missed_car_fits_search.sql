-- El auto del mail 2.5 tiene que ser el que la persona pidió.
--
-- El conteo de expired_search_matches usa el motor de las alertas: un dato
-- que falta (año, km, precio) pasa como «desconocido», y la versión pedida
-- solo suma puntaje salvo con trim_strict. Para el número está bien. Pero el
-- auto que el mail muestra como «la oportunidad que te perdiste» salía de esa
-- misma lista sin más control: el 4/11/2026, de 40 búsquedas con auto, una de
-- cada dos mostraba un auto sin año, con más km o más caro que el tope, de
-- otra versión o con un «% debajo» imposible (un Civic «Hotwheels» un 44 %
-- abajo, un Ka 2012 un 50 % abajo).
--
-- missed_car ahora vuelve a mirar la búsqueda tal como está y elige solo un
-- auto que la cumple con datos confirmados:
-- * marca y modelo de la búsqueda (si se editó después, vale la edición);
-- * con año, km o precio en la búsqueda, el dato tiene que estar y caer en el
--   rango (filters.years incluido). El precio se compara en la moneda de la
--   búsqueda, como preview_search;
-- * el aviso tiene que tener año, haya o no rango en la búsqueda;
-- * con versiones en la búsqueda (filters.trims, estrictas o no), la del aviso
--   tiene que contener todas las palabras de alguna. Si el aviso no tiene
--   versión cargada, se buscan en el título;
-- * caja, combustible y carrocería: si el aviso los tiene, tienen que coincidir;
-- * zona: la propia (radio > 0) y las de filters.extra_locations, con
--   coordenadas del aviso. Antes solo miraba la propia;
-- * precio creíble: diferencia con los comparables entre 5 % y 35 %, o sin
--   diferencia calculada pero con nivel «high». Más de 35 % suele ser un dato
--   mal cargado, un repuesto o un auto de otro año. Un auto más caro que los
--   comparables tampoco es una oportunidad.
-- Sin ninguno, el payload no lleva `car` y el mail sale con el conteo, como
-- hasta ahora. El conteo (found, below) no cambia.

create or replace function public.missed_car(p_search bigint, p_ended timestamptz) returns jsonb
language sql stable security definer set search_path = '' as $$
  with sp as (
    select s.origin_lat, s.origin_lon, s.radius_km, coalesce(s.filters, '{}'::jsonb) as f
      from public.search_profiles s
     where s.id = p_search
  ),
  f as (
    select nullif(btrim(sp.f->>'make'), '')  as make,
           nullif(btrim(sp.f->>'model'), '') as model,
           case when sp.f->>'year_min' ~ '^\d+$' then (sp.f->>'year_min')::int end as year_min,
           case when sp.f->>'year_max' ~ '^\d+$' then (sp.f->>'year_max')::int end as year_max,
           case when jsonb_typeof(sp.f->'years') = 'array' and jsonb_array_length(sp.f->'years') > 0
                then array(select (y)::int from jsonb_array_elements_text(sp.f->'years') y where y ~ '^\d+$') end as years,
           case when sp.f->>'km_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'km_min')::numeric end as km_min,
           case when sp.f->>'km_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'km_max')::numeric end as km_max,
           case when sp.f->>'price_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_min')::numeric end as price_min,
           case when sp.f->>'price_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_max')::numeric end as price_max,
           upper(coalesce(nullif(sp.f->>'currency', ''),
                          case when coalesce(case when sp.f->>'price_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_max')::numeric end,
                                             case when sp.f->>'price_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_min')::numeric end,
                                             0) >= 1000000
                               then 'ARS' else 'USD' end)) as currency,
           nullif(sp.f->>'transmission', '') as transmission,
           nullif(sp.f->>'fuel', '')         as fuel,
           public.search_body_types(sp.f)    as body_types,
           case when jsonb_typeof(sp.f->'trims') = 'array'
                then array(select lower(btrim(t)) from jsonb_array_elements_text(sp.f->'trims') t
                            where btrim(t) <> '') end as trims
      from sp
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  -- The search's own place and the ones it adds, as matching's search_zones.
  zones as (
    select sp.origin_lat as lat, sp.origin_lon as lon, sp.radius_km::double precision as radius
      from sp
     where sp.radius_km > 0 and sp.origin_lat is not null and sp.origin_lon is not null
    union all
    select (e->>'lat')::double precision, (e->>'lon')::double precision, (e->>'radius_km')::double precision
      from sp, jsonb_array_elements(case when jsonb_typeof(sp.f->'extra_locations') = 'array'
                                         then sp.f->'extra_locations' else '[]'::jsonb end) e
     where e->>'lat' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' and e->>'lon' ~ '^\s*[-+]?\d+(\.\d+)?\s*$'
       and e->>'radius_km' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' and (e->>'radius_km')::double precision > 0
  ),
  cand as (
    select m.level, m.diff_pct, m.score, m.created_at, l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from public.expired_search_matches m
      join public.listings l on l.id = m.listing_id
     cross join f
      left join fx on true
     where m.search_profile_id = p_search and m.access_ended_at = p_ended
       and l.price is not null and not l.price_partial
  )
  select jsonb_strip_nulls(jsonb_build_object(
           'listing_id', c.id, 'title', c.title, 'make', c.make, 'model', c.model, 'trim', c.trim,
           'year', c.year, 'price', c.price, 'currency', c.currency, 'km', c.mileage_km,
           'location', c.location_text,
           'images', case when jsonb_typeof(c.images) = 'array'
                          then (select coalesce(jsonb_agg(i.value order by i.ord), '[]'::jsonb)
                                  from jsonb_array_elements(c.images) with ordinality i (value, ord)
                                 where i.ord <= 3) end,
           'below', c.level = 'high',
           'diff_pct', c.diff_pct,
           'gone', c.status = 'gone',
           'days_listed', case when c.status = 'gone' then greatest(1, ceil(extract(epoch from
                            c.last_seen_at - coalesce(c.published_at, c.first_seen_at)) / 86400)::int) end))
    from cand c
   cross join f
   where (f.make is null or lower(c.make) = lower(f.make))
     and (f.model is null or lower(c.model) = lower(f.model))
     -- A bound the search set needs the listing's value, inside it.
     and ((f.year_min is null and f.year_max is null and f.years is null)
          or (c.year is not null
              and (f.year_min is null or c.year >= f.year_min)
              and (f.year_max is null or c.year <= f.year_max)
              and (f.years is null or cardinality(f.years) = 0 or c.year = any (f.years))))
     and ((f.km_min is null and f.km_max is null)
          or (c.mileage_km is not null
              and (f.km_min is null or c.mileage_km >= f.km_min)
              and (f.km_max is null or c.mileage_km <= f.km_max)))
     and ((f.price_min is null and f.price_max is null)
          or (c.price_in_filter is not null
              and (f.price_min is null or c.price_in_filter >= f.price_min)
              and (f.price_max is null or c.price_in_filter <= f.price_max)))
     -- A car without a year can't be told apart from an older one.
     and c.year is not null
     -- Every word of one of the wanted trims, as matching.trim_matches; with no
     -- trim in the listing, the words of its title.
     and (f.trims is null or cardinality(f.trims) = 0
          or exists (select 1 from unnest(f.trims) t
                      where not exists (select 1 from regexp_split_to_table(replace(t, '!', ''), '\s+') w
                                         where w <> ''
                                           and not (w = any (regexp_split_to_array(
                                                     replace(lower(coalesce(c.trim, c.title, '')), '!', ''), '\s+'))))))
     and (f.transmission is null or c.transmission is null or c.transmission = f.transmission)
     and (f.fuel is null or c.fuel is null or position(lower(f.fuel) in lower(c.fuel)) > 0)
     and (f.body_types is null or c.body_type is null or c.body_type = any (f.body_types))
     and (not exists (select 1 from zones)
          or (c.lat is not null and c.lon is not null
              and exists (select 1 from zones z where public.haversine_km(z.lat, z.lon, c.lat, c.lon) <= z.radius)))
     -- A believable opportunity: 5 % to 35 % under comparables, or level high without a number.
     and (c.diff_pct between 5 and 35 or (c.diff_pct is null and c.level = 'high'))
   order by c.level = 'high' desc, c.diff_pct desc nulls last, c.score desc nulls last,
            c.created_at desc, c.id desc
   limit 1
$$;

revoke all on function public.missed_car(bigint, timestamptz) from public, anon, authenticated;
